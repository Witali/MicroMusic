import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {annotatePhaseLocals,stripLocalEffects,phaseLocalMasks} from '../lib/avr-phase-locals.js';
import {ATtiny13A} from '../lib/attiny13a.js';
import {put} from './helpers/avr-test-state.mjs';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const bytes=(...parts)=>parts.flat(Infinity);
const mock={bytes,get:n=>[0x20,n],set:(n,v)=>bytes(v,0x21,n),
  condition:(t,y,n=[])=>bytes(t,0x04,0x40,y,...n.length?[0x05,n]:[],0x0b),
  conditionValue:(t,y,n)=>bytes(t,0x04,0x7f,y,0x05,n,0x0b)};
const ir=annotatePhaseLocals(mock),read=ir.get,write=n=>ir.set(n,[]);
test('phase liveness retains clock inputs and treats branch writes as definite only on both paths',()=>{
  const phases=[{prefix:write(0),clock:read(7)},{prefix:write(7),clock:read(8)}];
  assert.deepEqual(phaseLocalMasks(phases,read(0)),[(1<<0)|(1<<7)|(1<<8),(1<<0)|(1<<8)]);
  const branch=ir.condition(read(1),write(0));
  assert.deepEqual(phaseLocalMasks([{prefix:[],clock:[]}],bytes(branch,read(0))),[3]);
  const both=ir.condition(read(1),write(0),write(0));
  assert.deepEqual(phaseLocalMasks([{prefix:[],clock:[]}],bytes(both,read(0))),[2]);
  assert.deepEqual(stripLocalEffects(branch),mock.condition(mock.get(1),mock.set(0,[])));
  assert.throws(()=>stripLocalEffects([{kind:'unknown'}]),/non-byte/);
  assert.throws(()=>ir.condition([{kind:'avr-clock-phase'}],[],[]),/non-byte/);
});
test('nested value expressions retain read-before-write dependencies and the f64 temporary',()=>{
  const expression=ir.set(0,ir.conditionValue(read(2),ir.set(1,read(0)),read(9)));
  assert.deepEqual(phaseLocalMasks([{prefix:[],clock:[]}],bytes(expression,read(1))),[(1<<0)|(1<<1)|(1<<2)|(1<<9)]);
  assert.deepEqual(stripLocalEffects(expression),mock.set(0,mock.conditionValue(mock.get(2),mock.set(1,mock.get(0)),mock.get(9))));
});
const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,spmCommandCycles:1};
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const pair=(binary,extra={})=>[true,false].map(optimizePhaseLocals=>new ATtiny13A(binary,null,{...options,...extra,optimizePhaseLocals}));
const same=(a,b,label)=>{assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);};
const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const image=new Uint8Array(1024).fill(255);
for(const [n,entry]of instructions.entries()){
  let word=parseInt(entry.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2);
  if(/^(IN|OUT)$/.test(entry.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
  if(/^(SBI|CBI|SBIC|SBIS)$/.test(entry.form))word|=IO.PORTB<<3;
  put(image,n*3,word);put(image,n*3+1,0);
}
for(const external of [false,true])test(`all123 forms preserve every phase with four C/Z inputs, external${external}`,()=>{
  const [a,b]=pair(image,external?{fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{});
  assert.equal(a.transpilation.optimizePhaseLocals,true);assert.equal(b.transpilation.optimizePhaseLocals,undefined);
  assert.ok(a.transpilation.stats.phaseLocals.liveSlots<a.transpilation.stats.phaseLocals.fullSlots);
  assert.ok(a.transpiledBytes.length<b.transpiledBytes.length);
  for(const [n,entry]of instructions.entries())for(let flags=0;flags<4;flags++){
    for(const c of [a,b]){
      c._call('avr_reset',0,0);c.pc=n*3;c.sreg=0x70|flags;c.r[0]=0x96;c.r[1]=0x69;
      if(entry.form==='RET'||entry.form==='RETI')c.pushPC(1);
      if(entry.form==='POP')c.push(0xa5);
      if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])c.r[pointer]=97;
    }
    let at=0n,level=1;
    const edges=Array.from({length:20},()=>{at+=external?(level?70000n:30000n):50000n;level^=1;return{timePs:at,level};});
    if(external)for(const c of [a,b])assert.equal(c.injectClkiPs({edges,knownUntilPs:at}),true);
    let retired=0;
    for(const edge of edges){
      for(const deadline of [edge.timePs-1n,edge.timePs]){
        const actual=a.runUntilPs(deadline);assert.equal(actual,b.runUntilPs(deadline));retired+=actual;
        same(a,b,entry.form+' flags'+flags+' at'+deadline);
        assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
      }
      if(retired)break;
    }
    assert.equal(retired,1,entry.form);
  }
});
test('latched RET bytes survive debugger changes during later waits',()=>{
  const [a,b]=pair(sequential([[0x9508]]));
  for(const c of [a,b]){c.sp=0x9d;c.data[0x9e]=1;c.data[0x9f]=0x23;}
  for(const [at,address]of [[200000n,0x9e],[300000n,0x9f]]){
    assert.equal(a.runUntilPs(at),b.runUntilPs(at));same(a,b,'pop before mutation');
    for(const c of [a,b])c.data[address]=0xff;
  }
  assert.equal(a.runUntilPs(400000n),1);assert.equal(b.runUntilPs(400000n),1);
  same(a,b,'retired');assert.equal(a.pc,0x123);
});
test('RESET at every CALL half phase cancels later effects equally',()=>{
  for(let half=0n;half<=6n;half++){
    const [a,b]=pair(sequential([[0xd000]]));
    for(const c of [a,b]){c.data[0x9f]=0xa5;c.injectPinsPs({at:half*50000n,mask:32,levels:0});}
    for(let at=1n;at<=350001n;at+=25000n){assert.equal(a.runUntilPs(at),b.runUntilPs(at));same(a,b,'reset half'+half);}
  }
});
test('translation cache separates full and live contexts and invalidates after SPM',()=>{
  const binary=flash({instructions:[[0x95e8],avr.rjmp(1,128)]},{at:128,instructions:[avr.ldi(20,17)]});
  const extra={fuseHigh:0xef,nvmClockProfile:1,nvmCalibrationReferenceHz:hz,osccalHz:undefined,
    fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
  const [a,b]=pair(binary,extra),again=new ATtiny13A(binary,null,{...options,...extra,optimizePhaseLocals:true});
  assert.equal(again.translationCacheHit,true);assert.equal(again._translatedModule,a._translatedModule);assert.notEqual(a._translatedModule,b._translatedModule);
  for(const c of [a,b]){c.r[31]=1;c.writeIO(IO.SPMCSR,3);assert.equal(c.injectClkiPs({edges:[],knownUntilPs:5000000000n}),true);c.runUntilPs(5000000000n);}
  same(a,b,'SPM');assert.equal(a.transpilation.optimizePhaseLocals,true);assert.equal(a.transpilation.mapping[128].word,0xffff);
});
test('invalid phase-local options cannot bypass admission through a precompiled module',()=>{
  const binary=sequential([avr.ldi(16,42)]),legacy=new ATtiny13A(binary,null,{...options,resumable:false});
  const precompiled={bytes:legacy.transpiledBytes,manifest:legacy.transpilation};
  for(const optimizePhaseLocals of [true,'yes',null])assert.throws(()=>new ATtiny13A(binary,null,
    {...options,resumable:false,optimizePhaseLocals,precompiled}),/requires resumable/);
});
