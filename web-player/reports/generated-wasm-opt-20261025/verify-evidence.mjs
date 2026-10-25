import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8').replaceAll('\r\n','\n');
const sha=s=>createHash('sha256').update(s).digest('hex');
const root=fileURLToPath(new URL('../../../',import.meta.url));
const screen=JSON.parse(read('screen.json')),validation=JSON.parse(read('validation.json'));
assert.equal(screen.complete,true);assert.equal(screen.cases.length,4);
assert.equal(validation.complete,true);assert.equal(validation.mode,'validation');assert.equal(validation.cases.length,13);
for(const [report,file]of [[screen,'screen-harness-source.txt'],[validation,'validation-harness-source.txt']])
  assert.equal(sha(read(file)),report.sourceSha256['web-player/scripts/benchmark-generated-wasm.mjs']);
for(const report of [screen,validation])
  assert.equal(sha(read('optimizer-source.txt')),report.sourceSha256['web-player/scripts/lib/optimize-avr-wasm.mjs']);
for(const report of [screen,validation]){
  for(const [path,expected]of Object.entries(report.sourceSha256)){
    if(path==='web-player/scripts/benchmark-generated-wasm.mjs'||path==='web-player/scripts/lib/optimize-avr-wasm.mjs')continue;
    assert.equal(sha(execFileSync('git',['show',report.revision+':'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n')),expected,path);
  }
  assert.equal(sha(execFileSync('git',['show',report.revision+':web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024})),report.runtimeSha256);
}
let timed=0,warmups=0,checkpoints=0,validationRuns=0,validationCheckpoints=0;
for(const row of screen.cases){
  assert.ok(['rhythmic-compatible','rhythmic-physical'].includes(row.id));assert.ok(['O3','Oz'].includes(row.level));
  assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
  assert.deepEqual(controlRatios(row.runs,screen.trials),row.ratios);
  timed+=row.runs.length;warmups+=row.warmups.length;
  checkpoints+=[...row.runs,...row.warmups].reduce((n,r)=>n+r.checkpoints,0);
}
const expected=['rhythmic-compatible','rhythmic-physical','lumiere-stereo-compatible','lumiere-stereo-physical',
  'hq4-chego-auto-compatible','hq4-chego-auto-physical','kernel-compatible-direct','kernel-physical-direct',
  'kernel-clki-20m-div1','kernel-clki-20m-div256','kernel-internal-20m-div1',
  'kernel-internal-20m-div1-adc-active','kernel-clki-20m-div1-adc-active'];
assert.deepEqual(validation.cases.map(c=>c.id),expected);
for(const row of validation.cases){
  assert.equal(row.level,'Oz');assert.equal(row.runs.length,2);assert.equal(row.warmups.length,0);assert.equal(row.ratios,undefined);
  validationRuns+=2;validationCheckpoints+=row.runs.reduce((n,r)=>n+r.checkpoints,0);
}
for(const report of [screen,validation])for(const row of report.cases){
  const runs=[...row.runs,...row.warmups],first=runs[0];
  for(const run of runs)for(const key of ['rawSha256','stateSha256','pinSha256','checkpoints'])assert.equal(run[key],first[key]);
  assert.ok(row.optimization.outputBytes<row.optimization.inputBytes);
  assert.ok(row.optimization.flags.includes('--skip-pass=remove-unused-module-elements'));
  assert.equal(row.rawLayout.customSectionBytes,row.optimizedLayout.customSectionBytes);
}
assert.deepEqual([timed,warmups,checkpoints,validationRuns,validationCheckpoints],[128,64,2304,26,168]);
const tap=read('full-test.tap');assert.match(tap,/# tests 1641\n/);assert.match(tap,/# pass 1641\n/);assert.match(tap,/# fail 0\n/);assert.match(tap,/# skipped 0\n/);
console.log(JSON.stringify({timed,warmups,checkpoints,validationRuns,validationCheckpoints,tests:1641}));
