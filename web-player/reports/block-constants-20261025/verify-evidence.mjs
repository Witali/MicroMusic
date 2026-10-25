import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=name=>JSON.parse(read(name));
const sha=b=>createHash('sha256').update(b).digest('hex');
const root=fileURLToPath(new URL('../../../',import.meta.url));
const sources=json('candidate-sources.json'),screen=json('screen.json'),validation=json('validation.json');
for(const report of [screen,validation]){
  assert.equal(report.complete,true);assert.equal(report.transform,'block-constants');
  for(const [path,expected]of Object.entries(report.sourceSha256))assert.equal(sha(sources[path]),expected,path);
}
assert.equal(screen.cases.length,2);assert.equal(screen.gcBeforeRun,true);assert.equal(screen.cpuModulePolicy,'production-translation-cache');
const totals={timed:0,warmups:0,checkpoints:0};
for(const row of screen.cases){
  assert.deepEqual(controlRatios(row.runs,screen.trials),row.ratios);totals.timed+=row.runs.length;totals.warmups+=row.warmups.length;
  totals.checkpoints+=[...row.runs,...row.warmups].reduce((n,r)=>n+r.checkpoints,0);
}
assert.deepEqual(totals,{timed:64,warmups:32,checkpoints:1152});
assert.deepEqual(validation.cases.map(c=>c.id),['rhythmic-compatible','rhythmic-physical','lumiere-stereo-compatible','lumiere-stereo-physical',
  'hq4-chego-auto-compatible','hq4-chego-auto-physical','kernel-compatible-direct','kernel-physical-direct',
  'kernel-clki-20m-div1','kernel-clki-20m-div256','kernel-internal-20m-div1','kernel-internal-20m-div1-adc-active','kernel-clki-20m-div1-adc-active']);
let validationRuns=0,validationCheckpoints=0;
for(const row of validation.cases){validationRuns+=row.runs.length;validationCheckpoints+=row.runs.reduce((n,r)=>n+r.checkpoints,0);if(row.optimization.constantFolding)assert.equal(row.optimization.constantFolding.unsupported,0);}
assert.deepEqual([validationRuns,validationCheckpoints],[26,168]);
for(const report of [screen,validation])for(const row of report.cases){
  const runs=[...row.runs,...row.warmups],first=runs[0];
  for(const run of runs)for(const key of ['rawSha256','stateSha256','pinSha256','checkpoints'])assert.equal(run[key],first[key]);
}
const optimizer=json('optimizer-comparison.json');assert.equal(optimizer.cases.length,6);
for(const row of optimizer.cases){assert.equal(row.identicalCode,false);assert.ok(row.codeBytes[1]<row.codeBytes[0]);}
for(const [file,count]of [['candidate-full-test.tap',1660],['restored-full-test.tap',1655]]){
  const tap=read(file);for(const line of ['tests '+count,'pass '+count,'fail 0','skipped 0'])assert.ok(tap.includes('# '+line+'\n'));
}
const restoration=json('restoration.json');for(const [path,expected]of Object.entries(restoration.sources))
  assert.equal(sha(execFileSync('git',['show',restoration.baseline+':'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n')),expected,path);
console.log(JSON.stringify({...totals,validationRuns,validationCheckpoints,candidateTests:1660,restoredTests:1655}));
