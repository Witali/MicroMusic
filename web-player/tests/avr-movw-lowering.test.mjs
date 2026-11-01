// MOVW: Microchip DS40002198A section5.76; WASM Core memory instructions.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AVRCore as GeneratedCore} from '../lib/avr-transpiled.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {transpileAVR} from '../lib/avr-transpiler.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';
import {bodyList,addressBytes,occurrences} from './helpers/wasm-code.mjs';

const pairs=Array.from({length:256},(_,n)=>({d:(n>>4)*2,s:(n&15)*2}));
const movw=(d,s)=>[0x0100|((d>>1)<<4)|(s>>1)];
const image=sequential(pairs.map(({d,s})=>movw(d,s)));
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,optimizeFlags:false};
const modes=[['legacy13',()=>new GeneratedCore(image,null,{target:'attiny13a',fastIdle:false})],
  ['legacy88',()=>new GeneratedCore(image,null,{target:'attiny88',fastIdle:false})],
  ['full',()=>new ATtiny13A(image,null,{fastIdle:false})],
  ...[false,true].flatMap(optimizePhaseLocals=>[
    ['resumable-'+optimizePhaseLocals,()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals})],
    ['region-'+optimizePhaseLocals,()=>new ATtiny13A(image,null,{...physical,optimizePhaseLocals,boundedRegions:true})]])];
function initialize(c,seed){
  for(let r=0;r<32;r++)c.r[r]=(seed+r*37)&255;
  c.sreg=seed&255;
}
function copy(data,d,s){data[d]=data[s];data[d+1]=data[s+1];}
const wordCopy=(base,d,s)=>Buffer.from([...addressBytes(base+d),...addressBytes(base+s),0x2f,1,0,0x3b,1,0]);

for(const [name,make]of modes)test(`${name}: MOVW copies every register pair, preserves all other data and costs one cycle`,()=>{
  const c=make();c.clock(8);
  const values=[0,1,255,256,0x80ff,0xff00,0xffff];
  for(const [pc,{d,s}]of pairs.entries())for(const value of values){
    initialize(c,pc*37+value);c.r[s]=value&255;c.r[s+1]=value>>8;c.pc=pc;
    const expected=c.data.slice(),flags=c.sreg,cycles=c.cyc;copy(expected,d,s);
    c.step();assert.deepEqual(c.data,expected,`${name} r${d},r${s},${value}`);
    assert.equal(c.sreg,flags);assert.equal(c.pc,pc+1);assert.equal(c.cyc,cycles+1);
    if(c.state().deviceFault!==undefined)assert.equal(c.state().deviceFault,0);
  }
});

for(const [name,make]of modes)test(`${name}: individual MOVW bodies use one unsigned word load and word store`,()=>{
  const c=make(),bodies=bodyList(c.transpiledBytes),base=c.transpilation.abi.data;
  for(const [pc,{d,s}]of pairs.entries())assert.equal(occurrences(bodies[pc],wordCopy(base,d,s)),1,`r${d},r${s}`);
  if(!name.startsWith('region'))for(const [n,block]of c.transpilation.blocks.entries()){
    const body=bodies[c.words+n];
    for(const {d,s}of pairs.slice(block.start,block.end))assert.equal(occurrences(body,wordCopy(base,d,s)),1,`block${n} r${d},r${s}`);
  }
});

for(const [name,make]of modes.filter(([n])=>!n.startsWith('region')))test(`${name}: accepted MOVW blocks preserve sequential register dependencies`,()=>{
  const c=make();c.clock(8);
  for(const block of c.transpilation.blocks){
    initialize(c,block.start*19);c.pc=block.start;
    const expected=c.data.slice(),cycles=c.cyc;
    for(const {d,s}of pairs.slice(block.start,block.end))copy(expected,d,s);
    assert.equal(c._execute('block',Infinity,block.instructions),block.instructions);
    assert.deepEqual(c.data,expected);assert.equal(c.pc,block.end);assert.equal(c.cyc,cycles+block.cycles);
  }
});

test('MOVW unsigned word access works with an odd ABI register base',()=>{
  const reference=modes[0][1](),abi={...reference.transpilation.abi,data:reference.transpilation.abi.data|1};
  assert.equal(abi.data&1,1);
  const generated=transpileAVR(image,abi),memory=new WebAssembly.Memory({initial:abi.memoryPages||1,maximum:abi.memoryPages||1});
  const instance=new WebAssembly.Instance(new WebAssembly.Module(generated.bytes),{avr:{memory,
    clock(){},interrupt(){},writeIO(){return 0;},idle(){return 0;}}});
  const data=new Uint8Array(memory.buffer,abi.data,reference.data.length),view=new DataView(memory.buffer);
  for(const [pc,{d,s}]of pairs.entries()){
    data.fill(0);for(let r=0;r<32;r++)data[r]=(pc+r*37)&255;
    data[s]=0xff;data[s+1]=0x81;data[reference.profile.system.sreg]=pc;
    view.setFloat64(abi.state.pc,pc,true);const expected=data.slice();copy(expected,d,s);
    instance.exports.step();assert.deepEqual(data,expected);assert.equal(view.getFloat64(abi.state.pc,true),pc+1);
  }
});

for(const optimizePhaseLocals of [false,true])test(`cached MOVW region retains word dependencies and public entry edits, locals=${optimizePhaseLocals}`,()=>{
  const binary=flash({instructions:[movw(30,0),movw(0,2),movw(2,30),movw(28,28),avr.rjmp(4,0)]});
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals,boundedRegions}));
  for(const c of cores)c.clock(8);
  assert.equal(cores[0].transpilation.regions.length,1);
  for(const seed of [0,1,0x40,0x73,0x80,0xff]){
    for(const c of cores){initialize(c,seed);c.pc=0;}
    assert.equal(cores[0]._execute('block',Infinity,32),32);
    for(let n=0;n<32;n++)cores[1].step();
    assert.deepEqual(cores[0].data,cores[1].data);assert.deepEqual(cores[0].state(),cores[1].state());
    assert.deepEqual(cores[0]._state,cores[1]._state);assert.equal(cores[0].state().deviceFault,0);
  }
  const c=cores[0],bodies=bodyList(c.transpiledBytes),body=bodies[c.words+c.transpilation.stats.blocks];
  for(const [d,s]of [[30,0],[0,2],[2,30],[28,28]])assert.equal(occurrences(body,wordCopy(c.transpilation.abi.data,d,s)),0);
});

for(const optimizePhaseLocals of [false,true])test(`MOVW word copy samples public registers at retirement and preserves SREG edits and RESET cancellation, locals=${optimizePhaseLocals}`,()=>{
  const binary=sequential([movw(30,0)]),make=()=>new ATtiny13A(binary,null,{...physical,optimizePhaseLocals});
  const c=make();initialize(c,0x12);c.r[0]=0xff;c.r[1]=0x80;
  assert.equal(c.runUntilPs(1n),0);c.r[0]=0x34;c.r[1]=0x12;c.sreg=0xe5;
  assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.r[30],0x34);assert.equal(c.r[31],0x12);
  assert.equal(c.r[0],0x34);assert.equal(c.r[1],0x12);assert.equal(c.sreg,0xe5);assert.equal(c.state().cpuPhase.retired,1n);
  const reset=make();initialize(reset,0x12);reset.r[0]=0xff;reset.r[1]=0x80;
  const before=reset.r.slice();assert.equal(reset.runUntilPs(1n),0);
  reset.injectPinsPs({at:500000n,mask:32,levels:0});assert.equal(reset.runUntilPs(1000000n),0);
  assert.deepEqual(reset.r,before);assert.equal(reset.sreg,0);assert.equal(reset.state().cpuPhase.retired,0n);
  assert.equal(reset.state().resetCount,1);assert.equal(reset.state().deviceFault,0);
});

for(const optimizePhaseLocals of [false,true])test(`MOVW high pair commits before a tied Timer0 interrupt, locals=${optimizePhaseLocals}`,()=>{
  const binary=flash({instructions:[movw(30,0),avr.rjmp(1,1)]});
  const c=new ATtiny13A(binary,null,{...physical,optimizePhaseLocals});
  initialize(c,0);c.r[0]=0xff;c.r[1]=0x80;c.writeIO(IO.TCNT0,255);c.writeIO(IO.TIMSK0,MASK.TOIE0);c.writeIO(IO.TCCR0B,1);
  assert.equal(c.runUntilPs(1n),0);c.sreg=0x81;
  assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.r[30],0xff);assert.equal(c.r[31],0x80);
  assert.equal(c.state().cpuPhase.active,2);assert.equal(c.sreg,1);c.runUntilPs(5000000n);
  assert.equal(c.state().irqs,1);assert.equal(c.state().deviceFault,0);
});
