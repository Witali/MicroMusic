import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {controlRatios,statistics} from './lib/runtime-control-design.mjs';
const input=process.argv[2];if(!input)throw Error('Usage: node scripts/verify-incremental-benchmark.mjs report.json');
const report=JSON.parse(readFileSync(input,'utf8'));
assert.equal(report.schema,'micromusic-incremental-compilation-benchmark-v1');assert.equal(report.passed,true);
assert.equal(report.hardwareTested,false);assert.equal(report.realtimeTested,false);
assert.match(report.baselineCommit,/^[0-9a-f]{40}$/);assert.match(report.compilerIdentity,/^[0-9a-f]{64}$/);
assert.equal(report.nativeSha256,report.baselineSources['web-player/wasm/attiny13a.wasm']);
assert.equal(report.artifactParity.length,36);
assert.deepEqual(report.cases.map(c=>c.caseName),['host-patches','spm-compatible','spm-physical','spm-clki','audio-rhythmic','audio-lumiere']);
for(const c of report.cases){
  assert.equal(c.warmups.length,4);const expected=c.warmups[0];
  for(const run of [...c.warmups,...c.runs]){
    for(const key of ['snapshotSha256','translatedSha256','pinSha256','pins','pcmSha256'])assert.equal(run[key],expected[key],c.caseName+' '+key);
    assert.deepEqual(run.checkpoints.map(p=>p.translatedSha256),expected.checkpoints.map(p=>p.translatedSha256));
    if(run.variant.startsWith('new')){
      assert.ok(run.diagnostics,'Must activate incremental linking');
      if(c.caseName.startsWith('spm-')){
        assert.equal(run.diagnostics.compiled,1);assert.equal(run.diagnostics.reusedModules,32);
        assert.equal(run.diagnostics.instantiated,1);
      }
    }
  }
  assert.deepEqual(c.execution,controlRatios(c.runs,report.trials));
  assert.deepEqual(c.construction,controlRatios(c.runs.map(r=>({...r,ms:r.constructionMs})),report.trials));
  assert.deepEqual(c.ordinaryMs,statistics(c.runs.filter(r=>r.variant.startsWith('old')).map(r=>r.ms)));
  assert.deepEqual(c.incrementalMs,statistics(c.runs.filter(r=>r.variant.startsWith('new')).map(r=>r.ms)));
}
console.log(`Verified ${report.cases.reduce((n,c)=>n+c.runs.length,0)} observations, phase/state/code/output hashes and ${report.artifactParity.length} portable artifact comparisons.`);
