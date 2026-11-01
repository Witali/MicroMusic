// DS40002198A 5.3/5.98: ADIW/SBIW update S/V/N/Z/C, preserve I/T/H, two AVRe cycles.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AVRCore as GeneratedCore} from '../lib/avr-transpiled.js';
import {transpileAVR} from '../lib/avr-transpiler.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';
import {bodyList,addressBytes,occurrences} from './helpers/wasm-code.mjs';
import {arithmeticFlags} from './helpers/avr-expectations.mjs';

const word=(subtract,d,k)=>[(subtract?0x9700:0x9600)|((d-24)<<3)|(k&15)|((k&48)<<2)];
const operations=[false,true].flatMap(subtract=>[24,26,28,30].flatMap(d=>Array.from({length:64},(_,k)=>({subtract,d,k}))));
const image=flash({instructions:operations.map(({subtract,d,k})=>word(subtract,d,k))});
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,optimizeFlags:false};
const modes=[['legacy13',()=>new GeneratedCore(image,null,{target:'attiny13a',fastIdle:false})],
  ['legacy88',()=>new GeneratedCore(image,null,{target:'attiny88',fastIdle:false})],
  ['full',()=>new ATtiny13A(image,null,{fastIdle:false})],
  ...[false,true].flatMap(optimizePhaseLocals=>[
    ['resumable-'+optimizePhaseLocals,()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals})],
    ['region-'+optimizePhaseLocals,()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals,boundedRegions:true})]])];
function expected(x,k,subtract,flags){
  const total=subtract?x-k:x+k,value=total&65535,n=value>>>15;
  const signed=x<32768?x:x-65536,signedTotal=subtract?signed-k:signed+k,v=Number(signedTotal< -32768||signedTotal>32767);
  return{value,flags:(flags&0xe0)|((n^v)<<4)|(v<<3)|(n<<2)|(Number(value===0)<<1)|Number(subtract?total<0:total>65535)};
}
for(const [name,make]of modes)test(`${name}: word lowering covers all512 encodings and preserves two-cycle arithmetic`,()=>{
  const c=make();c.clock(8);
  for(const [pc,{subtract,d,k}]of operations.entries())for(const x of [0,1,63,64,255,256,32704,32705,32767,32768,32831,65472,65535])for(let high=0;high<8;high++){
    const flags=(high<<5)|((x^k)&31),e=expected(x,k,subtract,flags);c.r.fill(0xa5);c.r[d]=x;c.r[d+1]=x>>8;c.sreg=flags;c.pc=pc;
    const before=c.r.slice(),cycles=c.cyc;before[d]=e.value;before[d+1]=e.value>>8;c.step();
    assert.deepEqual(c.r,before);assert.equal(c.sreg,e.flags);assert.equal(c.cyc,cycles+2);assert.equal(c.pc,(pc+1)&c.pcMask);
  }
  if(c.state().deviceFault!==undefined)assert.equal(c.state().deviceFault,0);
});
for(const [name,make]of modes)test(`${name}: individual word arithmetic uses a word load and a word store`,()=>{
  const c=make(),bodies=bodyList(c.transpiledBytes),base=c.transpilation.abi.data;
  for(const [pc,{d}]of operations.entries()){
    assert.equal(occurrences(bodies[pc],Buffer.from([...addressBytes(base+d),0x2f,1,0])),1);
    assert.equal(occurrences(bodies[pc],Buffer.from([...addressBytes(base+d),0x20,4,0x3b,1,0])),1);
    assert.equal(occurrences(bodies[pc],Buffer.from([...addressBytes(base+d+1),0x2d,0,0])),0);
  }
});
for(const optimizePhaseLocals of [false,true])test(`word arithmetic cached regions retain local dependencies, locals=${optimizePhaseLocals}`,()=>{
  const binary=flash({instructions:[avr.ldi(24,255),avr.ldi(25,127),word(false,24,1),word(true,24,63),avr.rjmp(4,0)]});
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals,boundedRegions}));
  for(const c of cores)c.clock(8);assert.equal(cores[0].transpilation.regions.length,1);
  for(const flags of [0,1,0x20,0x40,0x80,0xff]){
    for(const c of cores){c.r.fill(0x5a);c.pc=0;c.sreg=flags;}
    assert.equal(cores[0]._execute('block',Infinity,32),32);for(let n=0;n<32;n++)cores[1].step();
    assert.deepEqual(cores[0].data,cores[1].data);assert.deepEqual(cores[0].state(),cores[1].state());
  }
});
for(const optimizeFlags of [false,true])for(const optimizePhaseLocals of [false,true])
test(`uncached word blocks preserve dependencies and dead flags: flags${optimizeFlags}/locals${optimizePhaseLocals}`,()=>{
  const binary=sequential([word(false,24,1),word(true,24,63),avr.add(19,20)]);
  const c=new ATtiny13A(binary,null,{...physical,optimizeFlags,optimizePhaseLocals});c.clock(8);
  for(let flags=0;flags<256;flags++)for(const x of [255,0x7fff,0xffff]){
    c.pc=0;c.r.fill(0xa5);c.r[24]=x;c.r[25]=x>>8;c.sreg=flags;const cycles=c.cyc;
    assert.equal(c._execute('block',Infinity,3),3);
    assert.equal(c.r[24]|(c.r[25]<<8),(x+1-63)&65535);assert.equal(c.r[19],0x4a);
    assert.equal(c.sreg,arithmeticFlags(0xa5,0xa5,0,false,flags));assert.equal(c.cyc,cycles+5);assert.equal(c.pc,3);
  }
});
for(const subtract of [false,true])for(const optimizePhaseLocals of [false,true])
test(`word arithmetic retirement keeps host edits, IRQ and RESET: subtract${subtract}/locals${optimizePhaseLocals}`,()=>{
  const binary=sequential([word(subtract,30,63)]),make=()=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals});
  const c=make();c.r[30]=0xff;c.r[31]=0x7f;c.sreg=0x20;
  assert.equal(c.runUntilPs(1n),0);c.r[30]=0x80;c.r[31]=0x80;c.sreg=0xe5;
  assert.equal(c.runUntilPs(1999999n),0);assert.equal(c.r[30],0x80);assert.equal(c.r[31],0x80);
  const e=expected(0x8080,63,subtract,0xe5);assert.equal(c.runUntilPs(2000000n),1);
  assert.equal(c.r[30]|(c.r[31]<<8),e.value);assert.equal(c.sreg,e.flags);assert.equal(c.state().cpuPhase.retired,1n);
  const irq=make();irq.r[30]=0xff;irq.r[31]=0x7f;irq.sreg=0xe0;
  irq.writeIO(IO.TCNT0,254);irq.writeIO(IO.TIMSK0,MASK.TOIE0);irq.writeIO(IO.TCCR0B,1);
  irq.runUntilPs(2000000n);assert.equal(irq.r[30]|(irq.r[31]<<8),expected(0x7fff,63,subtract,0).value);
  assert.equal(irq.state().cpuPhase.active,2);irq.runUntilPs(6000000n);assert.equal(irq.state().irqs,1);
  const reset=make();reset.r[30]=0xff;reset.r[31]=0x7f;const before=reset.r.slice();
  reset.injectPinsPs({at:1000000n,mask:MASK.PINB5,levels:0});assert.equal(reset.runUntilPs(2000000n),0);
  assert.deepEqual(reset.r,before);assert.equal(reset.state().cpuPhase.retired,0n);assert.equal(reset.state().resetCount,1);
});
test('word arithmetic permits an odd ABI register base',()=>{
  const reference=modes[0][1](),abi={...reference.transpilation.abi,data:reference.transpilation.abi.data|1};
  const generated=transpileAVR(image,abi),memory=new WebAssembly.Memory({initial:abi.memoryPages||1,maximum:abi.memoryPages||1});
  const instance=new WebAssembly.Instance(new WebAssembly.Module(generated.bytes),{avr:{memory,clock(){},interrupt(){},writeIO(){return 0;},idle(){return 0;}}});
  const data=new Uint8Array(memory.buffer,abi.data,reference.data.length),view=new DataView(memory.buffer);
  for(const [pc,{subtract,d,k}]of operations.entries()){
    data.fill(0xa5);data[d]=0xff;data[d+1]=0x7f;data[reference.profile.system.sreg]=0xe0;view.setFloat64(abi.state.pc,pc,true);
    instance.exports.step();const e=expected(0x7fff,k,subtract,0xe0);
    assert.equal(data[d]|(data[d+1]<<8),e.value);assert.equal(data[reference.profile.system.sreg],e.flags);
  }
});
for(const subtract of [false,true])for(const optimizePhaseLocals of [false,true])
test(`word arithmetic survives held/unequal CLKI phases: subtract${subtract}/locals${optimizePhaseLocals}`,()=>{
  const c=new ATtiny13A(sequential([word(subtract,30,63)]),null,{resumable:true,optimizePhaseLocals,fastIdle:false,
    fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  c.r[30]=0xff;c.r[31]=0x7f;
  c.injectClkiPs({edges:[{timePs:70000n,level:0}],knownUntilPs:1000000n});
  assert.equal(c.runUntilPs(1000000n),0);assert.equal(c.cyc,.5);c.r[30]=0x80;c.r[31]=0x80;c.sreg=0xe5;
  c.injectClkiPs({edges:[{timePs:1030000n,level:1},{timePs:1100000n,level:0},{timePs:1800000n,level:1}],knownUntilPs:1800000n});
  assert.equal(c.runUntilPs(1799999n),0);assert.equal(c.r[30],0x80);assert.equal(c.r[31],0x80);assert.equal(c.sreg,0xe5);
  const e=expected(0x8080,63,subtract,0xe5);assert.equal(c.runUntilPs(1800000n),1);
  assert.equal(c.r[30]|(c.r[31]<<8),e.value);assert.equal(c.sreg,e.flags);assert.equal(c.cyc,2);
  assert.equal(c.state().cpuPhase.retired,1n);assert.equal(c.state().deviceFault,0);
});
