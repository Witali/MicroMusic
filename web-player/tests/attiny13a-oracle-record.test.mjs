import {test} from 'node:test';
import assert from 'node:assert/strict';
import {coreProbeCases} from '../scripts/lib/avr-core-probe-cases.mjs';
import {decodeAttiny13aOracle as decode} from '../scripts/lib/attiny13a-oracle-record.mjs';
import {oracleSuite} from '../scripts/lib/attiny13a-oracle-cases.mjs';
const descriptor=()=>({schema:'micromusic-attiny13a-studio-control-v1',device:'ATtiny13A',
  buildId:[1,2,3,4],recordBytes:60,cases:coreProbeCases.map(c=>({...c}))});
function record(before=0,overhead=2){
  const b=new Uint8Array(60);b.set([65,86,49,51,1,2,3,4,0,0,before,(before+overhead)&255]);
  coreProbeCases.forEach((c,n)=>b.set([c.result,c.sreg,before,(before+overhead+c.cycles)&255],12+4*n));return b;
}
test('oracle decoder retains all twelve independent results and calibrated cycle totals across wrap',()=>{
  for(const before of [0,1,127,250,255])for(const overhead of [1,2,3]){
    const r=decode(record(before,overhead),descriptor());assert.equal(r.passed,true);assert.equal(r.hostVerified,false);
    assert.equal(r.overheadTicks,overhead);assert.deepEqual(r.cases.map(c=>c.cycles),coreProbeCases.map(c=>c.cycles));
  }
});
test('oracle decoder reports altered result, preserved flag and timing bytes as failures',()=>{
  for(const offset of [12,13,15]){const b=record();b[offset]^=1;const r=decode(b,descriptor());
    assert.equal(r.passed,false);assert.equal(r.cases[0].passed,false);assert.equal(r.hostVerified,false);}
});
test('oracle decoder rejects incomplete, wrong-sized and stale-build records',()=>{
  assert.throws(()=>decode(record().subarray(1),descriptor()),/length/);
  const a=record();a[0]=0;assert.throws(()=>decode(a,descriptor()),/Incomplete/);
  const b=record();b[4]^=1;assert.throws(()=>decode(b,descriptor()),/build/);
});
test('oracle decoder rejects changed descriptor targets and expectations',()=>{
  for(const mutate of [d=>d.device='ATtiny88',d=>d.schema='other',d=>d.recordBytes=59,
    d=>d.cases[0].sreg^=1,d=>d.cases[0].flags^=1,d=>d.cases[0].asm='nop',d=>d.cases.pop()]){const d=descriptor();mutate(d);assert.throws(()=>decode(record(),d));}
});
test('oracle decoder rejects invalid empty controls and refuses to certify a source',()=>{
  const b=record();b[8]=1;assert.throws(()=>decode(b,descriptor()),/control/);
  assert.throws(()=>decode(record(),descriptor(),{captureKind:'official-simulator'}),/source/);
  const r=decode(record(),descriptor(),{captureKind:'synthetic-emulator'});assert.equal(r.hostVerified,false);
});

test('oracle suites reject cross-suite records, unknown suites and changed flag stimuli',()=>{
  const cases=oracleSuite('flags').cases,d={...descriptor(),suite:'flags',cases:cases.map(c=>({...c}))},b=record();
  cases.forEach((c,n)=>b.set([c.result,c.sreg,254,(254+2+c.cycles)&255],12+4*n));
  assert.equal(decode(b,d).passed,true);assert.equal(decode(b,d).suite,'flags');
  assert.throws(()=>decode(b,{...d,suite:'unknown'}),/suite/);
  assert.throws(()=>decode(b,{...d,suite:'core'}),/catalog/);
  assert.throws(()=>decode(record(),{...descriptor(),suite:'flags'}),/catalog/);
  d.cases[0].flags^=2;assert.throws(()=>decode(b,d),/catalog/);
});
