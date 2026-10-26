import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const read=name=>readFileSync(new URL(name,import.meta.url));
const hash=b=>createHash('sha256').update(b).digest('hex');
const lf=b=>b.toString('utf8').replaceAll('\r\n','\n');
const b=JSON.parse(read('benchmark.json')),a=JSON.parse(read('analysis.json'));
assert.equal(b.complete,false);assert.equal(a.decision,'rejected');assert.equal(a.stoppedEarly,true);
assert.equal(b.results.length,6);assert.equal(a.completedCases,6);
assert.equal(hash(lf(read('benchmark-harness-source.txt'))),b.provenance.sourceSha256['web-player/scripts/benchmark-runtime-controls.mjs']);
const manifest=JSON.parse(read('native-manifest.json'));
assert.equal(hash(read('candidate.wasm')),manifest.artifacts['attiny13a.wasm']);
assert.equal(hash(read('candidate.wasm')),a.candidateSha256);
assert.equal(hash(lf(read('candidate-device-clock.h.txt'))),manifest.inputs['web-player/native/peripherals/device_clock.h']);
const median=v=>{v=[...v].sort((a,b)=>a-b);return(v[7]+v[8])/2;};
const labels=['oldA','oldB','newA','newB'];let runs=0,warmups=0,checkpoints=0;
for(const c of b.results){
  assert.equal(c.runs.length,64);assert.equal(c.warmups.length,16);
  const reference=c.warmups[0],ratios={oldIdentity:[],newIdentity:[],crossVersion:[]};
  for(const r of [...c.warmups,...c.runs])for(const key of ['rawSha256','architectureSha256','pinSha256','finalState'])assert.deepEqual(r[key],reference[key]);
  for(let trial=0;trial<16;trial++){
    const rows=c.runs.filter(r=>r.trial===trial);assert.deepEqual(rows.map(r=>r.variant),b.parameters.schedule[trial]);
    const time=label=>rows.find(r=>r.variant===label).ms;for(const label of labels)assert.ok(Number.isFinite(time(label))&&time(label)>0);
    ratios.oldIdentity.push(time('oldA')/time('oldB'));ratios.newIdentity.push(time('newA')/time('newB'));
    ratios.crossVersion.push(Math.sqrt(time('oldA')*time('oldB'))/Math.sqrt(time('newA')*time('newB')));
  }
  const entry=a.cases.find(r=>r.id===c.id);assert.ok(entry);
  for(const[key,values]of Object.entries(ratios))assert.ok(Math.abs(median(values)-entry[key])<1e-12);
  assert.equal(ratios.crossVersion.filter(r=>r>1).length,entry.fasterTrials);
  runs+=c.runs.length;warmups+=c.warmups.length;checkpoints+=c.validation.checkpointsCompared;
}
assert.deepEqual([runs,warmups,checkpoints],[384,96,5688]);
assert.match(lf(read('full-test.tap')),/# pass 1633\n# fail 0/);
console.log('Rejected candidate, six complete cases, 384 timings and 5688 recorded parity checkpoints verified.');
