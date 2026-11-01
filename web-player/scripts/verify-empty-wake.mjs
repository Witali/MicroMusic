// Collect the isolated wake-delay experiment; never modify production.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs,isDeepStrictEqual} from 'node:util';
import {controlRatios} from './lib/runtime-control-design.mjs';
import {bodyList} from '../tests/helpers/wasm-code.mjs';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string',default:'build/empty-wake-20261101'},
  output:{type:'string',default:'build/empty-wake-evidence.json'}}});
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n'),
  sha=b=>createHash('sha256').update(b).digest('hex'),raw=n=>read(join(values.input,n)),json=n=>JSON.parse(raw(n));
const baseline='9e8909ff',native='web-player/wasm/attiny13a.wasm',device='web-player/native/peripherals/device.c';
const git=p=>execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:8*1024*1024});
const old=git(native),base=JSON.parse(git('web-player/wasm/device-build.json')),
  candidate=raw('shadow/'+native),manifest=json('shadow/web-player/wasm/device-build.json'),proof=json('build-proof.json');
assert.ok(read(native).equals(old),'Production native differs');
assert.ok(isDeepStrictEqual(JSON.parse(text('web-player/wasm/device-build.json')),base),'Production manifest differs');
for(const [path,h]of Object.entries(base.inputs))assert.equal(sha(text(path)),h,'Production source differs');
for(const [path,h]of Object.entries(AVR_CACHE_SOURCES)){
  assert.equal(sha(text(path)),h,'Compiler source differs');
  assert.equal(sha(git(path).toString().replaceAll('\r\n','\n')),h,'Compiler changed from baseline');
}
assert.ok(raw('control-native.wasm').equals(old));assert.equal(proof.controlByteEqual,true);
assert.equal(proof.controlSha256,sha(old));assert.equal(proof.candidateSha256,sha(candidate));
assert.equal(proof.deviceSourceSha256,sha(text(join(values.input,'candidate-device.c'))));
assert.equal(manifest.artifacts['attiny13a.wasm'],sha(candidate));assert.equal(manifest.bytes,candidate.length);
for(const key of ['flags','exports','sources','compilerVersion'])assert.ok(isDeepStrictEqual(manifest[key],base[key]),'Build contract differs');
for(const [path,h]of Object.entries(manifest.inputs))assert.equal(sha(path===device?text(join(values.input,'candidate-device.c')):
  git(path).toString().replaceAll('\r\n','\n')),h,'Candidate input differs');
for(const bytes of [old,candidate]){
  const m=new WebAssembly.Module(bytes);assert.deepEqual(WebAssembly.Module.imports(m),[]);
  assert.deepEqual(WebAssembly.Module.exports(m).filter(e=>e.kind==='function').map(e=>e.name).sort(),[...base.exports].sort());
  const e=new WebAssembly.Instance(m).exports;assert.equal(e.memory.buffer.byteLength,131072);assert.throws(()=>e.memory.grow(1),RangeError);
}
const a=bodyList(old),b=bodyList(candidate);assert.equal(a.length,b.length);
const changedBodies=a.flatMap((body,index)=>body.equals(b[index])?[]:[{index,beforeBytes:body.length,afterBytes:b[index].length}]);
const inputs={},captures=[];let timedRuns=0,warmups=0,checkpoints=0;
for(const name of ['parity','screen','confirmation']){
  const r=json(name+'.json');inputs[name+'.json']=sha(raw(name+'.json'));assert.equal(r.complete,true);
  assert.equal(r.mode,name==='parity'?'validation':'timing');assert.equal(r.results.length,name==='parity'?16:4);
  assert.equal(r.parameters.changeSet,'empty-wake');assert.equal(r.parameters.boundedRegions,true);assert.equal(r.parameters.phaseLocals,true);
  assert.equal(r.host.node,process.version);assert.equal(r.host.v8,process.versions.v8);
  for(const [path,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(text(path)),h,'Captured host source differs');
  for(const [label,version]of Object.entries(r.provenance.runtimes)){
    const expected=label.startsWith('old')?base:manifest;assert.equal(version.sha256,expected.artifacts['attiny13a.wasm']);
    assert.ok(isDeepStrictEqual(version.inputs,expected.inputs),'Captured native inputs differ');
  }
  const cases=r.results.map(row=>{
    assert.ok(Object.values(row.validation).every(v=>typeof v==='number'||v===true),'Incomplete validation');
    if(row.options.resumable){assert.equal(row.options.boundedRegions,true);assert.equal(row.options.optimizePhaseLocals,true);}
    const runs=[...row.warmups,...row.runs],reference=runs[0];
    for(const run of runs){assert.equal(run.finalState.deviceFault,0);
      for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(run[key],reference[key],'Output parity differs');}
    assert.equal(row.validation.checkpointsCompared,(runs.length-1)*reference.checkpoints);checkpoints+=row.validation.checkpointsCompared;
    const common={id:row.id,options:row.options,frames:row.frames,instructions:row.instructions,channels:row.channels,
      flashSha256:row.flashSha256,translationSha256:row.translationSha256,validation:row.validation,
      finalState:reference.finalState,outputHashes:Object.fromEntries(['rawSha256','architectureSha256','pinSha256'].map(k=>[k,reference[k]]))};
    if(name==='parity'){assert.equal(row.runs.length,2);return common;}
    assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
    assert.ok(isDeepStrictEqual(controlRatios(row.runs,r.parameters.trials),row.summary.ratios),'Timing ratios differ');
    timedRuns+=row.runs.length;warmups+=row.warmups.length;
    return {...common,runs:row.runs.map(({trial,position,variant,ms})=>({trial,position,variant,ms})),
      warmups:row.warmups.map(({pass,position,variant,ms})=>({pass,position,variant,ms})),ratios:row.summary.ratios};
  });captures.push({id:name,parameters:r.parameters,host:r.host,cases});
}
const taps={};
for(const kind of ['baseline','candidate']){
  const path='build/empty-wake-'+kind+'-tests-20261101.tap',bytes=read(path),counts=Object.fromEntries(
    ['tests','pass','fail','skipped','cancelled','todo'].map(key=>{const m=bytes.toString().match(new RegExp('^# '+key+' (\\d+)$','m'));
      assert.ok(m,'Incomplete TAP');return [key,Number(m[1])];}));
  assert.equal(counts.pass,6);assert.equal(counts.tests,6);assert.equal(counts.fail+counts.skipped+counts.cancelled+counts.todo,0);
  taps[kind]={...counts,path,sha256:sha(bytes)};
}
const sources=['web-player/scripts/rebuild-empty-wake.mjs','web-player/scripts/verify-empty-wake.mjs',
  'web-player/scripts/benchmark-runtime-controls.mjs','web-player/scripts/lib/runtime-control-design.mjs',
  'web-player/tests/helpers/wasm-code.mjs','web-player/tests/analog-test-build.mjs','web-player/tests/device-wake-delays.test.mjs'];
const report={schema:'micromusic-empty-wake-experiment-v1',date:'2026-11-01',baselineRef:baseline,decision:'not-retained',productionUnchanged:true,
  compilerIdentity:AVR_CACHE_COMPILER_ID,compilerSourcesVerified:Object.keys(AVR_CACHE_SOURCES).length,
  native:{baselineBytes:old.length,baselineSha256:sha(old),candidateBytes:candidate.length,candidateSha256:sha(candidate)},
  proof,changedBodies,completedTimedRuns:timedRuns,completedWarmups:warmups,exactCheckpoints:checkpoints,
  fullCandidateRuntimeSuiteRun:false,taps,inputs,captures,sources:Object.fromEntries(sources.map(p=>[p,sha(text(p))])),
  plan:{complete:24,total:31,open:7},
  meaning:'Isolated conditional wake-delay evaluation; all elapsed runs are coupled Node execution with exact output checks. No exclusive subsystem, silicon, browser real-time or audio-underrun claim.'};
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({timedRuns,warmups,checkpoints,productionUnchanged:true,changedBodies}));
