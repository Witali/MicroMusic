// DS40002198A 5.45/5.119: CP Rd,Rd and SUB Rd,Rd have constant H/S/V/N/Z/C.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AVRCore as GeneratedCore} from '../lib/avr-transpiled.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';
import {rr} from './helpers/avr-test-state.mjs';
import {arithmeticFlags} from './helpers/avr-expectations.mjs';
import {CLKI_PHASE_POLICY} from '../lib/devices/attiny13a-clki-profile.js';

const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false};
const operations=[['CP',0x1400],['SUB',0x1800]];
const flagsAfter=flags=>(flags&0xc0)|2;
function initialize(c,flags){for(let r=0;r<32;r++)c.r[r]=(flags+r*37)&255;c.sreg=flags;}
const snapshot=c=>({data:c.data.slice(),state:c.state(),diagnostics:Array.from(c._state)});

for(const [name,opcode]of operations){
  const image=sequential(Array.from({length:32},(_,r)=>[rr(opcode,r,r)]));
  const modes=[['legacy13',()=>new GeneratedCore(image,null,{target:'attiny13a',fastIdle:false})],
    ['legacy88',()=>new GeneratedCore(image,null,{target:'attiny88',fastIdle:false})],
    ['full',()=>new ATtiny13A(image,null,{fastIdle:false})],
    ...[false,true].map(optimizePhaseLocals=>['resumable-'+optimizePhaseLocals,
      ()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals})])];
  for(const [mode,make]of modes)test(`${name} self ${mode}: every GPR and SREG pattern, one cycle`,()=>{
    const c=make();c.clock(8);
    for(let flags=0;flags<256;flags++)for(let r=0;r<32;r++){
      initialize(c,flags);c.pc=r;
      const expected=c.data.slice(),cycles=c.cyc;
      if(name==='SUB')expected[r]=0;expected[c.profile.system.sreg]=flagsAfter(flags);
      c.step();assert.deepEqual(c.data,expected,`r${r}, SREG ${flags}`);
      assert.equal(c.pc,r+1);assert.equal(c.cyc,cycles+1);
    }
  });

  test(`${name} self: all 65536 independent byte/SREG combinations`,()=>{
    const c=new ATtiny13A(image,null,physical);
    for(let flags=0;flags<256;flags++)for(let value=0;value<256;value++){
      c.pc=31;c.r[31]=value;c.sreg=flags;c.step();
      assert.equal(c.r[31],name==='SUB'?0:value);assert.equal(c.sreg,flagsAfter(flags));
    }
  });

  test(`${name}: distinct operands retain ordinary subtraction semantics`,()=>{
    const c=new ATtiny13A(sequential([[rr(opcode,16,17)]]),null,physical);
    for(const x of [0,1,15,16,127,128,255])for(const y of [0,1,15,16,127,128,255])for(const flags of [0,1,0xc0,255]){
      c.pc=0;c.r[16]=x;c.r[17]=y;c.sreg=flags;c.step();
      assert.equal(c.r[16],name==='SUB'?(x-y)&255:x);assert.equal(c.r[17],y);
      assert.equal(c.sreg,arithmeticFlags(x,y,0,true,flags));
    }
  });

  for(const optimizeFlags of [false,true])for(const optimizePhaseLocals of [false,true])
    test(`${name} self block: partial and dead flags, flags=${optimizeFlags}, locals=${optimizePhaseLocals}`,()=>{
      for(const [tail,mask]of [[[[rr(0x0400,19,19)]],3],[[avr.eor(1,1)],0x21],[[avr.add(19,20)],0]]){
        const c=new ATtiny13A(sequential([[rr(opcode,0,0)],...tail]),null,
          {...physical,optimizeFlags,optimizePhaseLocals});c.clock(8);
        assert.equal(c.transpilation.blocks[0].masks[0],optimizeFlags?mask:63);
        for(let flags=0;flags<256;flags++){
          initialize(c,flags);c.pc=0;
          const expected=c.data.slice();if(name==='SUB')expected[0]=0;
          if(mask===3)expected[c.profile.system.sreg]=flagsAfter(flags);
          else if(mask===0x21){expected[1]=0;expected[c.profile.system.sreg]=flagsAfter(flags);}
          else{
            expected[19]=(c.r[19]+c.r[20])&255;
            expected[c.profile.system.sreg]=arithmeticFlags(c.r[19],c.r[20],0,false,flagsAfter(flags));
          }
          const cycles=c.cyc;assert.equal(c._execute('block',Infinity,2),2);
          assert.deepEqual(c.data,expected);assert.equal(c.pc,2);assert.equal(c.cyc,cycles+2);
        }
      }
    });

  for(const optimizePhaseLocals of [false,true])test(`${name} self cached region preserves register dependencies, locals=${optimizePhaseLocals}`,()=>{
    const binary=flash({instructions:[[rr(opcode,31,31)],avr.add(31,0),[rr(opcode,0,0)],avr.inc(0),avr.rjmp(4,0)]});
    const cores=[true,false].map(boundedRegions=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals,boundedRegions}));
    for(const c of cores)c.clock(8);assert.equal(cores[0].transpilation.regions.length,1);
    for(let flags=0;flags<256;flags++){
      for(const c of cores){initialize(c,flags);c.pc=0;}
      assert.equal(cores[0]._execute('block',Infinity,32),32);for(let n=0;n<32;n++)cores[1].step();
      assert.deepEqual(...cores.map(snapshot));assert.equal(cores[0].state().deviceFault,0);
    }
  });

  for(const optimizePhaseLocals of [false,true])test(`${name} self retirement: public edits, tied IRQ and RESET, locals=${optimizePhaseLocals}`,()=>{
    const make=()=>new ATtiny13A(sequential([[rr(opcode,31,31)]]),null,{...physical,optimizePhaseLocals});
    const c=make();initialize(c,0xff);assert.equal(c.runUntilPs(1n),0);c.r[31]=0xa5;c.sreg=0x65;
    assert.equal(c.runUntilPs(999999n),0);assert.equal(c.r[31],0xa5);assert.equal(c.sreg,0x65);
    assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.r[31],name==='SUB'?0:0xa5);
    assert.equal(c.sreg,flagsAfter(0x65));assert.equal(c.state().cpuPhase.retired,1n);
    const irq=make();initialize(irq,0);irq.writeIO(IO.TCNT0,255);irq.writeIO(IO.TIMSK0,MASK.TOIE0);irq.writeIO(IO.TCCR0B,1);
    assert.equal(irq.runUntilPs(1n),0);irq.sreg=0xe5;
    assert.equal(irq.runUntilPs(1000000n),1);assert.equal(irq.sreg,flagsAfter(0x65));
    assert.equal(irq.state().cpuPhase.active,2);irq.runUntilPs(5000000n);assert.equal(irq.state().irqs,1);
    const reset=make();initialize(reset,0xff);const before=reset.r.slice();assert.equal(reset.runUntilPs(1n),0);
    reset.injectPinsPs({at:500000n,mask:32,levels:0});assert.equal(reset.runUntilPs(1000000n),0);
    assert.deepEqual(reset.r,before);assert.equal(reset.sreg,0);assert.equal(reset.state().cpuPhase.retired,0n);
    assert.equal(reset.state().resetCount,1);assert.equal(reset.state().deviceFault,0);
  });

  for(const optimizePhaseLocals of [false,true])test(`${name} self: held and unequal CLKI phases retain exact retirement, locals=${optimizePhaseLocals}`,()=>{
    const c=new ATtiny13A(sequential([[rr(opcode,31,31)]]),null,{resumable:true,optimizePhaseLocals,
      clkiProfile:{phasePolicy:CLKI_PHASE_POLICY,initialLevel:1},fuseLow:0x70,fastIdle:false});
    initialize(c,0xff);
    c.injectClkiPs({edges:[{timePs:70000n,level:0}],knownUntilPs:1000000n});
    assert.equal(c.runUntilPs(1000000n),0);assert.equal(c.cyc,.5);assert.equal(c.pc,0);
    c.r[31]=0xa5;c.sreg=0x65;
    c.injectClkiPs({edges:[{timePs:1030000n,level:1}],knownUntilPs:1030000n});
    assert.equal(c.runUntilPs(1029999n),0);assert.equal(c.r[31],0xa5);assert.equal(c.sreg,0x65);
    assert.equal(c.runUntilPs(1030000n),1);assert.equal(c.r[31],name==='SUB'?0:0xa5);
    assert.equal(c.sreg,flagsAfter(0x65));assert.equal(c.cyc,1);assert.equal(c.pc,1);
    assert.equal(c.state().cpuPhase.retired,1n);assert.equal(c.state().deviceFault,0);
  });
}
