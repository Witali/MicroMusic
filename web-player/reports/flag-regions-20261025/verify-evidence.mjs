import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=name=>JSON.parse(read(name));
const sha=s=>createHash('sha256').update(s).digest('hex');
const root=fileURLToPath(new URL('../../../',import.meta.url));
const sources=json('candidate-sources.json'),screen=json('screen.json'),validation=json('validation.json'),activation=json('activation.json');
for(const report of [screen,validation,activation]){
  assert.equal(report.complete,true);
  for(const [path,expected]of Object.entries(report.sourceSha256))assert.equal(sha(sources[path]),expected,path);
}
assert.equal(screen.cases.length,2);assert.equal(screen.transform,'flag-regions');assert.equal(screen.gcBeforeRun,true);
const totals={timed:0,warmups:0,checkpoints:0};
for(const row of screen.cases){
  assert.deepEqual(controlRatios(row.runs,screen.trials),row.ratios);
  totals.timed+=row.runs.length;totals.warmups+=row.warmups.length;
  totals.checkpoints+=[...row.runs,...row.warmups].reduce((n,r)=>n+r.checkpoints,0);
}
assert.deepEqual(totals,{timed:64,warmups:32,checkpoints:1152});
assert.equal(validation.cases.length,13);let validationRuns=0,validationCheckpoints=0;
assert.deepEqual(validation.cases.map(c=>c.id),['rhythmic-compatible','rhythmic-physical','lumiere-stereo-compatible','lumiere-stereo-physical',
  'hq4-chego-auto-compatible','hq4-chego-auto-physical','kernel-compatible-direct','kernel-physical-direct',
  'kernel-clki-20m-div1','kernel-clki-20m-div256','kernel-internal-20m-div1',
  'kernel-internal-20m-div1-adc-active','kernel-clki-20m-div1-adc-active']);
for(const row of validation.cases){validationRuns+=row.runs.length;validationCheckpoints+=row.runs.reduce((n,r)=>n+r.checkpoints,0);}
assert.deepEqual([validationRuns,validationCheckpoints],[26,168]);
for(const report of [screen,validation])for(const row of report.cases){
  const runs=[...row.runs,...row.warmups],first=runs[0];
  for(const run of runs)for(const key of ['rawSha256','stateSha256','pinSha256','checkpoints'])assert.equal(run[key],first[key]);
}
assert.deepEqual(activation.cases.map(c=>c.id),['rhythmic','lumiere-stereo','hq4-chego-tiny']);
assert.deepEqual(activation.cases.map(c=>c.regions.reduce((n,r)=>n+r.accepted,0)),[1,1789,15614]);
assert.equal(activation.cases.reduce((n,c)=>n+c.checkpoints,0),11698);
const candidate=read('candidate-full-test.tap');for(const line of ['tests 1662','pass 1662','fail 0','skipped 0'])assert.ok(candidate.includes('# '+line+'\n'));
const restored=read('restored-full-test.tap');for(const line of ['tests 1652','pass 1652','fail 0','skipped 0'])assert.ok(restored.includes('# '+line+'\n'));
const restoration=json('restoration.json');for(const [path,expected]of Object.entries(restoration.sources))
  assert.equal(sha(execFileSync('git',['show',restoration.baseline+':'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n')),expected,path);
console.log(JSON.stringify({...totals,validationRuns,validationCheckpoints,activationCheckpoints:11698,candidateTests:1662,restoredTests:1652}));
