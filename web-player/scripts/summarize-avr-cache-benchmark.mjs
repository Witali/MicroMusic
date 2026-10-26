import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {controlRatios,statistics} from './lib/runtime-control-design.mjs';
const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node scripts/summarize-avr-cache-benchmark.mjs input.json output.json');
const report=JSON.parse(readFileSync(input,'utf8'));
assert.equal(report.schema,'micromusic-persistent-cache-construction-v1');assert.equal(report.passed,true);
assert.match(report.compilerIdentity,/^[0-9a-f]{64}$/);
assert.equal(report.hardwareTested,false);assert.equal(report.realtimeTested,false);
assert.deepEqual(report.workloads.map(w=>w.id),['rhythmic','lumiere-stereo']);
const workloads=report.workloads.map(w=>{
  assert.equal(w.warmups.length,4);const expected=w.warmups[0];
  for(const run of [...w.warmups,...w.runs])for(const key of ['snapshotSha256','translatedSha256','runtimeSha256']){
    assert.match(run[key],/^[0-9a-f]{64}$/);assert.equal(run[key],expected[key],key+' differs');
  }
  assert.ok(w.runs.filter(r=>r.variant.startsWith('new')).every(r=>r.cache?.hit===true));
  return {id:w.id,construction:controlRatios(w.runs,report.trials),
    readiness:controlRatios(w.runs.map(r=>({...r,ms:r.readyMs})),report.trials),
    ordinaryMs:statistics(w.runs.filter(r=>r.variant.startsWith('old')).map(r=>r.ms)),
    persistentMs:statistics(w.runs.filter(r=>r.variant.startsWith('new')).map(r=>r.ms))};
});
assert.equal(report.workloads[0].runs[0].runtimeSha256,report.workloads[1].runs[0].runtimeSha256);
const summary={schema:'micromusic-persistent-cache-construction-summary-v1',
  compilerIdentity:report.compilerIdentity,hardwareTested:false,realtimeTested:false,workloads};
writeFileSync(output,JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify(workloads.map(w=>({id:w.id,ordinaryMs:w.ordinaryMs.median,persistentMs:w.persistentMs.median,
  constructionRatio:w.construction.crossVersion,workerReadyRatio:w.readiness.crossVersion})),null,2));
