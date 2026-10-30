// CLR = EOR Rd,Rd: Microchip DS40002198A section 5.39.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AVRCore as GeneratedCore} from '../lib/avr-transpiled.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false};
const image=sequential(Array.from({length:32},(_,r)=>avr.eor(r,r)));
const modes=[['legacy13',()=>new GeneratedCore(image,null,{target:'attiny13a',fastIdle:false})],
  ['legacy88',()=>new GeneratedCore(image,null,{target:'attiny88',fastIdle:false})],
  ['full',()=>new ATtiny13A(image,null,{fastIdle:false})],
  ...[false,true].map(optimizePhaseLocals=>['resumable-'+optimizePhaseLocals,
    ()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals})])];
const flagsAfter=flags=>(flags&0xe1)|2;
function initialize(c,flags){for(let r=0;r<32;r++)c.r[r]=(flags+r*37)&255;c.sreg=flags;}

for(const [name,make]of modes)test(`${name}: CLR covers every GPR, input byte and SREG pattern in one cycle`,()=>{
  const c=make();c.clock(8);
  for(let flags=0;flags<256;flags++)for(let r=0;r<32;r++){
    initialize(c,flags);c.pc=r;
    const expected=c.data.slice(),cycles=c.cyc;expected[r]=0;expected[c.profile.system.sreg]=flagsAfter(flags);
    c.step();assert.deepEqual(c.data,expected,`r${r}, SREG ${flags}`);
    assert.equal(c.pc,r+1);assert.equal(c.cyc,cycles+1);
  }
});

for(const optimizeFlags of [false,true])for(const optimizePhaseLocals of [false,true])
  test(`CLR supplies only chained Z to CPC, flags=${optimizeFlags}, locals=${optimizePhaseLocals}`,()=>{
    const binary=sequential([avr.eor(0,0),[0x0733]]); // CPC r19,r19.
    const c=new ATtiny13A(binary,null,{...physical,optimizeFlags,optimizePhaseLocals});c.clock(8);
    assert.equal(c.transpilation.blocks[0].masks[0],optimizeFlags?2:30);
    for(let flags=0;flags<256;flags++){
      initialize(c,flags);c.pc=0;
      const expected=c.data.slice();expected[0]=0;
      expected[c.profile.system.sreg]=(flags&0xc0)|((flags&1)?0x35:2);
      assert.equal(c._execute('block',Infinity,2),2);assert.deepEqual(c.data,expected);
    }
  });

for(const optimizeFlags of [false,true])for(const optimizePhaseLocals of [false,true])
  test(`CLR block preserves partial flag liveness, flags=${optimizeFlags}, locals=${optimizePhaseLocals}`,()=>{
    // CLR -> INC overwrites Z/N/V/S; ADC consumes C preserved by both. The last
    // CLR must publish its flags even when all earlier CLR flags are dead.
    const binary=sequential([avr.eor(0,0),avr.inc(0),[0x1f11],avr.eor(31,31)]);
    const c=new ATtiny13A(binary,null,{...physical,optimizeFlags,optimizePhaseLocals});c.clock(8);
    assert.equal(c.transpilation.blocks.length,1);
    for(let flags=0;flags<256;flags++){
      initialize(c,flags);c.pc=0;c.r[17]=0x7f;
      const cycles=c.cyc,expected=c.data.slice();expected[0]=1;expected[17]=254+(flags&1);expected[31]=0;
      // ADC 0x7f+0x7f+C sets H and V, clears C; final CLR keeps H only.
      expected[c.profile.system.sreg]=(flags&0xc0)|0x22;
      assert.equal(c._execute('block',Infinity,4),4);
      assert.deepEqual(c.data,expected);assert.equal(c.pc,4);assert.equal(c.cyc,cycles+4);
    }
  });

for(const optimizePhaseLocals of [false,true])test(`cached CLR region keeps dependencies and public entry edits, locals=${optimizePhaseLocals}`,()=>{
  const binary=flash({instructions:[avr.eor(31,31),avr.add(31,0),avr.eor(0,0),avr.inc(0),avr.rjmp(4,0)]});
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals,boundedRegions}));
  for(const c of cores)c.clock(8);
  assert.equal(cores[0].transpilation.regions.length,1);
  for(let flags=0;flags<256;flags++){
    for(const c of cores){initialize(c,flags);c.pc=0;}
    assert.equal(cores[0]._execute('block',Infinity,32),32);
    for(let n=0;n<32;n++)cores[1].step();
    assert.deepEqual(cores[0].data,cores[1].data);assert.deepEqual(cores[0].state(),cores[1].state());
    assert.deepEqual(cores[0]._state,cores[1]._state);assert.equal(cores[0].state().deviceFault,0);
  }
});

for(const optimizePhaseLocals of [false,true])test(`CLR retirement preserves edited untouched flags, tied IRQ and RESET cancellation, locals=${optimizePhaseLocals}`,()=>{
  const binary=sequential([avr.eor(31,31)]),make=()=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals});
  const c=make();initialize(c,0xff);
  assert.equal(c.runUntilPs(1n),0);c.r[31]=0xa5;c.sreg=0x65;
  assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.r[31],0);assert.equal(c.sreg,flagsAfter(0x65));
  assert.equal(c.state().cpuPhase.retired,1n);
  const irq=make();initialize(irq,0);irq.writeIO(IO.TCNT0,255);irq.writeIO(IO.TIMSK0,MASK.TOIE0);irq.writeIO(IO.TCCR0B,1);
  assert.equal(irq.runUntilPs(1n),0);irq.sreg=0xe5;
  assert.equal(irq.runUntilPs(1000000n),1);assert.equal(irq.r[31],0);assert.equal(irq.sreg,flagsAfter(0x65));
  assert.equal(irq.state().cpuPhase.active,2);irq.runUntilPs(5000000n);assert.equal(irq.state().irqs,1);
  const reset=make();initialize(reset,0xff);const before=reset.r.slice();
  assert.equal(reset.runUntilPs(1n),0);reset.injectPinsPs({at:500000n,mask:32,levels:0});
  assert.equal(reset.runUntilPs(1000000n),0);assert.deepEqual(reset.r,before);assert.equal(reset.sreg,0);
  assert.equal(reset.state().cpuPhase.retired,0n);assert.equal(reset.state().resetCount,1);
  assert.equal(reset.state().deviceFault,0);
});
