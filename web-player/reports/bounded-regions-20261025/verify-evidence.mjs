import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8').replaceAll('\r\n','\n');
const json=name=>JSON.parse(read(name)),sha=b=>createHash('sha256').update(b).digest('hex');
const sources=json('sources.json'),screen=json('screen.json'),matrix=json('matrix.json'),validation=json('validation.json'),activation=json('activation.json');
for(const [path,source]of Object.entries(sources))
  assert.equal(execFileSync('git',['show','50b330e:'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n'),source,path+' retained implementation');
const expected=['rhythmic-compatible','rhythmic-physical','lumiere-stereo-compatible','lumiere-stereo-physical',
  'hq4-chego-auto-compatible','hq4-chego-auto-physical','kernel-compatible-direct','kernel-physical-direct',
  'kernel-clki-20m-div1','kernel-clki-20m-div256','kernel-internal-20m-div1',
  'kernel-internal-20m-div1-adc-active','kernel-clki-20m-div1-adc-active'];
for(const report of [screen,matrix,validation,activation]){
  assert.equal(report.complete,true);
  for(const [path,hash]of Object.entries(report.sourceSha256))assert.equal(sha(sources[path]),hash,path);
  assert.equal(report.runtimeSha256,'111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6');
}
for(const report of [screen,matrix,validation]){
  assert.equal(report.transform,'bounded-regions');
  assert.equal(report.baseline.revision,'bc8f6db3a4f481db3f909ce7c2af3ec7741aae33');
  for(const [path,hash]of Object.entries(report.baseline.sourceSha256))
    assert.equal(sha(execFileSync('git',['show',report.baseline.revision+':'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n')),hash,path);
  assert.equal(sha(execFileSync('git',['show',report.baseline.revision+':web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024})),report.runtimeSha256);
  for(const row of report.cases){
    const observations=[...row.runs,...row.warmups],first=observations[0];
    for(const run of observations)for(const key of ['rawSha256','stateSha256','pinSha256','checkpoints'])assert.equal(run[key],first[key],row.id+' '+key);
  }
}
assert.deepEqual(validation.cases.map(c=>c.id),expected);assert.equal(validation.mode,'validation');
assert.equal(validation.cases.reduce((n,c)=>n+c.runs.length,0),26);
assert.equal(validation.cases.reduce((n,c)=>n+c.runs.reduce((s,r)=>s+r.checkpoints,0),0),168);
const measured=[...screen.cases,...matrix.cases];
assert.deepEqual(measured.map(c=>c.id).sort(),[...expected].sort());
const totals={timed:0,warmups:0,checkpoints:0};
for(const report of [screen,matrix]){
  assert.equal(report.cpuModulePolicy,'production-translation-cache');assert.equal(report.gcBeforeRun,true);
  assert.equal(report.trials,8);assert.equal(report.warmups,4);
  for(const row of report.cases){
    assert.deepEqual(controlRatios(row.runs,report.trials),row.ratios);
    assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
    totals.timed+=row.runs.length;totals.warmups+=row.warmups.length;
    totals.checkpoints+=[...row.runs,...row.warmups].reduce((n,r)=>n+r.checkpoints,0);
    const parity=validation.cases.find(c=>c.id===row.id);
    for(const key of ['inputSha256','outputSha256','inputBytes','outputBytes'])assert.equal(row.optimization[key],parity.optimization[key]);
  }
}
assert.deepEqual(totals,{timed:416,warmups:208,checkpoints:4032});
assert.deepEqual(activation.cases.map(c=>c.id),['rhythmic','lumiere-stereo','hq4-chego-tiny']);
assert.equal(activation.instructions,1000000);
const proven=[[4678,79740],[3494,39630],[17149,462093]];
activation.cases.forEach((c,n)=>{
  assert.ok(c.irqCount>5000);
  assert.deepEqual([c.regions.reduce((s,r)=>s+r.provenBatches,0),c.regions.reduce((s,r)=>s+r.provenInstructions,0)],proven[n]);
});
assert.equal(activation.cases.reduce((n,c)=>n+c.checkpoints,0),11609);
const packaged=json('optimized-package.json');assert.equal(packaged.complete,true);
assert.equal(packaged.runtimeSha256,validation.runtimeSha256);assert.equal(packaged.cases.length,3);
for(const row of packaged.cases){
  const original=validation.cases.find(c=>c.actualId===row.id&&c.id.endsWith('-physical'));assert.ok(original);
  assert.equal(row.optimization.inputSha256,original.optimization.outputSha256);
  assert.equal(row.optimization.executableSha256,'ece3a130458778d485ede67297ac139bb6b66a008bb84292b7f0e10f4af2cd95');
  assert.deepEqual(row.optimization.flags,['-Oz','--mvp-features','--enable-mutable-globals','--skip-pass=remove-unused-module-elements']);
  assert.equal(row.checkpoints,4);assert.ok(row.irqCount>0);
}
for(const line of ['tests 1673','pass 1673','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
for(const line of ['tests 1','pass 1','fail 0'])assert.ok(read('cli-test.tap').includes('# '+line+'\n'));
console.log(JSON.stringify({...totals,validationRuns:26,validationCheckpoints:168,activationCheckpoints:11609,optimizedPackageCheckpoints:12,tests:1673}));
