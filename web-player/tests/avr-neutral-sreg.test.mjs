import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AVRCore as GeneratedCore} from '../lib/avr-transpiled.js';
import {AVRCore as NativeCore} from '../lib/avr-wasm.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,optimizeFlags:false};
const instructions=[['NOP',avr.nop()],['LDI',avr.ldi(16,42)],['MOV',[0x2f10]],['MOVW',[0x0180]],['SWAP',[0x9502]]];
function initialize(c){c.r[0]=0x12;c.r[1]=0x34;c.r[16]=0xab;c.r[17]=0x5c;}

for(const optimizePhaseLocals of [false,true])for(const [name,words] of instructions)
  test(`${name} preserves a debugger SREG edit during its clock phase, locals=${optimizePhaseLocals}`,()=>{
    const c=new ATtiny13A(sequential([words]),null,{...physical,optimizePhaseLocals});initialize(c);
    c.sreg=0x12;assert.equal(c.runUntilPs(1n),0);c.sreg=0x65;
    assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.sreg,0x65);
    assert.equal(c.state().cpuPhase.retired,1n);assert.equal(c.state().timePs,1000000n);
    assert.equal(c.r[16],name==='LDI'?42:name==='MOVW'?0x12:name==='SWAP'?0xba:0xab);
    assert.equal(c.r[17],name==='MOV'?0xab:name==='MOVW'?0x34:0x5c);
    assert.equal(c.state().deviceFault,0);
  });

for(const [name,words] of instructions)test(`${name} retains edited SREG.I for a tied Timer0 IRQ`,()=>{
  const c=new ATtiny13A(sequential([words]),null,physical);initialize(c);
  c.writeIO(IO.TCNT0,255);c.writeIO(IO.TIMSK0,MASK.TOIE0);c.writeIO(IO.TCCR0B,1);
  assert.equal(c.runUntilPs(1n),0);c.sreg=MASK.SREG_I|MASK.SREG_C;
  assert.equal(c.runUntilPs(1000000n),1);
  assert.equal(c.state().cpuPhase.active,2);assert.equal(c.sreg,MASK.SREG_C);
  c.runUntilPs(5000000n);assert.equal(c.state().irqs,1);assert.equal(c.state().cpuPhase.retired,1n);
  assert.equal(c.state().deviceFault,0);
});

for(const [name,words] of instructions)test(`${name} still aborts on RESET after a paused SREG edit`,()=>{
  const c=new ATtiny13A(sequential([words]),null,physical);initialize(c);
  assert.equal(c.runUntilPs(1n),0);c.sreg=0x65;c.injectPinsPs({at:500000n,mask:32,levels:0});
  assert.equal(c.runUntilPs(1000000n),0);assert.equal(c.state().cpuPhase.retired,0n);
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,true);assert.equal(c.sreg,0);
  assert.equal(c.r[16],0xab);assert.equal(c.r[17],0x5c);assert.equal(c.state().deviceFault,0);
});

for(const target of ['attiny13a','attiny88'])test(`${target}: all five neutral instructions retain every SREG input against native C`,()=>{
  const image=sequential(instructions.map(([,w])=>w));
  const a=new GeneratedCore(image,null,{target,fastIdle:false}),b=new NativeCore(image,null,{target,fastIdle:false});
  for(let flags=0;flags<256;flags++)for(let pc=0;pc<instructions.length;pc++){
    for(const c of [a,b]){c._call('avr_reset',0,0);initialize(c);c.sreg=flags;c.pc=pc;}
    a.step();b.step();assert.deepEqual(a.data,b.data);assert.equal(a.sreg,flags);
    assert.equal(a.pc,b.pc);assert.equal(a.cyc,b.cyc);
  }
});

function functionBodies(bytes){
  let p=8;const u32=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=bytes[p++];n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid test WASM');};
  while(p<bytes.length){const id=bytes[p++],size=u32(),end=p+size;
    if(id===10){const count=u32();return Array.from({length:count},()=>{const size=u32(),body=Buffer.from(bytes.subarray(p,p+size));p+=size;return body;});}
    p=end;
  }
  throw Error('Missing code section');
}
function addressBytes(value){const out=[0x41];let more;
  do{const b=value&127;value>>=7;more=!((value===0&&!(b&64))||(value===-1&&(b&64)));out.push(b|(more?128:0));}while(more);
  return Buffer.from(out);
}
const references=(body,needle)=>{let count=0;for(let at=0;(at=body.indexOf(needle,at))>=0;at+=needle.length)count++;return count;};
for(const mode of ['legacy13','legacy88','full','resumable'])test(`${mode}: neutral bodies omit SREG copies but retain block IRQ guards`,()=>{
  const image=sequential(instructions.map(([,w])=>w));
  const c=mode.startsWith('legacy')?new GeneratedCore(image,null,{target:mode==='legacy88'?'attiny88':'attiny13a'}):
    new ATtiny13A(image,null,mode==='resumable'?physical:{});
  const bodies=functionBodies(c.transpiledBytes),address=addressBytes(c.transpilation.abi.data+c.profile.system.sreg);
  for(let pc=0;pc<instructions.length;pc++)assert.equal(references(bodies[pc],address),0,instructions[pc][0]);
  const firstBlock=bodies[c.words];assert.equal(references(firstBlock,address),mode==='resumable'?1:0);
});
