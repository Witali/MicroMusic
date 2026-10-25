import {test} from 'node:test';
import assert from 'node:assert/strict';
import {UniversalReference} from './universal-reference.mjs';
const hold=[...Array(16)].flatMap((_,i)=>[i,0,0]);
const score=extra=>({schema:'micromusic-um88-score',version:1,voices:1,channels:1,
 waves:Array(64).fill(0x77),contexts:[[0,0,0,128]],envelopes:[hold],pitches:[null],
 commands:[64,0,143,2,0],controlTicks:2,normalizer:[],normalizerMinimum:0,masterShift:0,...extra});
function sample(r){const result=r.beginSample();r.finishSample();return result;}

test('independent oracle checks signed output, interpolation and ring wrap',()=>{
 const r=new UniversalReference(score({}),8000000);
 assert.equal(sample(r),0xfff1fff1);assert.deepEqual([...r.ring.slice(188)],[124,124,120,120]);
 assert.deepEqual([...r.ring.slice(0,4)],[116,116,113,113]);assert.equal(r.write,4);
});
test('rational musical clock preserves duration for a one-tick loop at 8 and 12 MHz',()=>{
 for(const cpu of [8000000,12000000]){
  const r=new UniversalReference(score({commands:[143,1,0],controlTicks:1}),cpu);
  while(!r.loops)sample(r);
  assert.equal(r.totalTicks,1);
  assert.ok(Math.abs(r.samples/(cpu/1024)-256/18750)<1024/cpu);
 }
});
test('envelope transitions precede same-tick commands',()=>{
 const decay=Array.from({length:16},(_,i)=>[Math.max(0,i-1),255,255]).flat();
 const r=new UniversalReference(score({envelopes:[decay],commands:[143,1,138,2,0]}),75000);
 sample(r);assert.equal(r.voices[0].level,10);
});
test('kick uses fractional advance, hat and snare use exact 16-bit LFSR',()=>{
 const r=new UniversalReference(score({}),8000000);r.drumMode=128;
 r.percussion();assert.equal(r.drumPhase,2);r.percussion();assert.equal(r.drumPhase,4);
 r.percussion();assert.equal(r.drumPhase,7);
 r.drumMode=129;r.drumPhase=255;r.noiseHigh=255;r.percussion();
 assert.equal(r.drumPhase|(r.noiseHigh<<8),65534^45);
 r.drumMode=130;r.drumPhase=0;r.noiseHigh=1;assert.equal(r.percussion(),-8);
});
test('normalizer refuses out-of-table samples instead of accepting firmware reads',()=>{
 const r=new UniversalReference(score({normalizer:[128],normalizerMinimum:0}),8000000);
 r.beginSample();assert.throws(()=>r.finishSample(),/Normalizer/);
});
