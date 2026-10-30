// Recheck retained experiment inputs and collect public, path-free evidence.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,relative,isAbsolute,dirname,join,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {controlRatios} from './lib/runtime-control-design.mjs';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string',default:'build/clock-power2-20261030'},
  output:{type:'string',default:'build/clock-power2-evidence.json'}}});
const input=resolve(root,values.input),rel=relative(resolve(root,'build'),input);
assert.ok(rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep),'Raw inputs must stay in build/');
const read=p=>readFileSync(resolve(root,p)),json=p=>JSON.parse(read(p));
const normal=p=>read(p).toString('utf8').replaceAll('\r\n','\n');
const hash=b=>createHash('sha256').update(b).digest('hex');
const raw=name=>join(input,name),load=name=>json(raw(name));
const manifest=json('web-player/wasm/device-build.json'),native=read('web-player/wasm/attiny13a.wasm');
assert.equal(hash(native),manifest.artifacts['attiny13a.wasm']);
for(const [p,h]of Object.entries(manifest.inputs))assert.equal(hash(normal(p)),h,'Stale native input');
const module=new WebAssembly.Module(native),instance=new WebAssembly.Instance(module);
assert.deepEqual(WebAssembly.Module.imports(module),[]);assert.equal(instance.exports.memory.buffer.byteLength,131072);
assert.equal(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').length,117);
assert.throws(()=>instance.exports.memory.grow(1),RangeError);

const captures=[['screen.json',2],['matched-screen.json',1],['controls.json',12],['parity.json',15],['final-parity.json',16]];
const baseline=load('screen.json').git.baseline;assert.match(baseline,/^[0-9a-f]{40}$/);
const git=p=>execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:4*1024*1024});
const oldNative=git('web-player/wasm/attiny13a.wasm'),oldManifest=JSON.parse(git('web-player/wasm/device-build.json'));
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],oldManifest[key]);
const changedInputs=Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==oldManifest.inputs[p]);
assert.deepEqual(changedInputs,['web-player/native/peripherals/device_clock.h']);
const producer='web-player/scripts/benchmark-runtime-controls.mjs',currentProducer=normal(producer);
const directCase="cases.push({...cases.find(row=>row.id==='kernel-internal-20m-div1'),id:'kernel-internal-20m-div1-direct',instructions});\n";
assert.equal(currentProducer.split(directCase).length,2);
const initialProducer=currentProducer.replace(directCase,'');
const files={},translationHashes=new Map();
const measurements=captures.map(([file,count])=>{
  const r=load(file);files[file]=hash(read(raw(file)));assert.equal(r.complete,true);assert.equal(r.results.length,count);
  assert.equal(r.git.baseline,baseline);assert.deepEqual(r.provenance.changedInputs,changedInputs);
  for(const [label,v]of Object.entries(r.provenance.runtimes))
    assert.equal(v.sha256,label.startsWith('old')?hash(oldNative):hash(native));
  for(const [p,h]of Object.entries(r.provenance.sourceSha256)){
    const text=p===producer&&['screen.json','parity.json'].includes(file)?initialProducer:normal(p);
    assert.equal(hash(text),h,'Capture source changed');
  }
  const cases=r.results.map(row=>{
    if(translationHashes.has(row.id))assert.equal(row.translationSha256,translationHashes.get(row.id),'Changed CPU bytes');
    translationHashes.set(row.id,row.translationSha256);
    const records=[...row.warmups,...row.runs],reference=records[0];assert.ok(reference);
    for(const key of ['exactWarmupAndTimedState','exactPcmAndPins','sameRuntimeModuleInsidePairs',
      'identicalCPUBytesAndABI','freshCPUmodulePerConstruction'])assert.equal(row.validation[key],true);
    for(const record of records)assert.ok(Number.isFinite(record.ms)&&record.ms>0&&Number.isSafeInteger(record.checkpoints)&&record.checkpoints>0);
    for(const record of records)for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])
      assert.equal(record[key],reference[key],'Output/checkpoint mismatch');
    assert.equal(row.validation.checkpointsCompared,(records.length-1)*reference.checkpoints);
    if(r.mode==='timing')assert.deepEqual(row.summary.ratios,controlRatios(row.runs,r.parameters.trials));
    const times=rows=>rows.map(({trial,pass,position,variant,ms})=>({...(trial===undefined?{pass}:{trial}),position,variant,ms}));
    return {id:row.id,options:row.options,...(row.frames===undefined?{}:{frames:row.frames}),
      ...(row.instructions===undefined?{}:{instructions:row.instructions}),flashSha256:row.flashSha256,
      translationSha256:row.translationSha256,translationBytes:row.translationBytes,
      output:{...Object.fromEntries(['rawSha256','architectureSha256','pinSha256','checkpoints'].map(k=>[k,reference[k]]))},
      validation:row.validation,warmups:times(row.warmups),runs:times(row.runs),
      ...(r.mode==='timing'?{ratios:row.summary.ratios}:{})};
  });
  return {input:file,mode:r.mode,host:r.host,parameters:r.parameters,method:r.method,
    captureSourceHashes:r.provenance.sourceSha256,cases};
});
const comparisonFolders=readdirSync(raw('functions')).filter(n=>n.startsWith('compare-'));
assert.equal(comparisonFolders.length,1);
const staticPath=raw('functions/'+comparisonFolders[0]+'/summary.json'),comparison=json(staticPath);
files['function-comparison']=hash(read(staticPath));
assert.equal(comparison.before.runtimeSha256,hash(oldNative));assert.equal(comparison.after.runtimeSha256,hash(native));
assert.equal(comparison.scriptSha256,hash(normal('web-player/scripts/compare-device-functions.mjs')));
assert.ok(comparison.before.rebuildByteEqual&&comparison.after.rebuildByteEqual);
assert.deepEqual(comparison.counts,{identical:216,'relocation-only':0,'body-changed':2,added:0,removed:0});
const changed=comparison.functions.filter(f=>f.status!=='identical');
assert.deepEqual(changed.map(f=>f.symbol).sort(),['duration','ratio']);
const accuracy=load('event-accuracy.json');files['event-accuracy.json']=hash(read(raw('event-accuracy.json')));
assert.equal(accuracy.native.sha256,hash(native));assert.equal(accuracy.compilerIdentity,AVR_CACHE_COMPILER_ID);
assert.ok(BigInt(accuracy.maxErrorPs)<=10000n);
const tests={};
for(const file of ['baseline-clock.tap','candidate-clock.tap','full.tap','shared.tap']){
  const bytes=read(raw(file)),text=bytes.toString(),counts={};
  for(const key of ['tests','pass','fail','cancelled','skipped','todo']){
    const match=text.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(match,'Incomplete TAP');counts[key]=Number(match[1]);
  }
  assert.ok(counts.pass>0&&counts.pass===counts.tests);assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  tests[file]={...counts,sha256:hash(bytes)};
}
const timed=measurements.filter(m=>m.mode==='timing'),timedCases=timed.flatMap(m=>m.cases);
const matched=timedCases.filter(r=>r.id==='kernel-internal-20m-div1-direct');assert.equal(matched.length,2);
assert.equal(matched.flatMap(r=>r.ratios.pairs).filter(r=>r.crossVersion>1).length,16);
const sourcePaths=['web-player/scripts/verify-clock-power2.mjs',producer,'web-player/scripts/lib/runtime-control-design.mjs',
  'web-player/tests/device-clock.test.mjs','web-player/native/peripherals/device_clock.h',
  'web-player/lib/attiny13a.js','web-player/lib/avr-cache-identity.js'];
const report={schema:'micromusic-clock-power2-evidence-v1',baselineCommit:baseline,
  decision:'Retained for the repeated synthetic 20 MHz unbounded-run improvement; capture/music gains remain unproven.',
  native:{beforeBytes:oldNative.length,afterBytes:native.length,beforeSha256:hash(oldNative),afterSha256:hash(native),
    manifestSha256:hash(normal('web-player/wasm/device-build.json')),compiler:manifest.compilerVersion,
    imports:0,functionExports:117,memoryPages:2,changedInputs,
    functionCounts:comparison.counts,changedFunctions:changed.map(f=>({symbol:f.symbol,before:f.before,after:f.after})),
    toolIdentities:Object.fromEntries(Object.entries(comparison.tools).map(([name,v])=>[name,{sha256:v.sha256,version:v.version.split('\n')[0]}]))},
  compilerIdentity:AVR_CACHE_COMPILER_ID,sourceHashes:Object.fromEntries(sourcePaths.map(p=>[p,hash(normal(p))])),
  loaderRefresh:{allCPUTranslationHashesUnchanged:true,
    initialProducerDifference:'Only the later 20 MHz direct fixture is absent; its exact removal reconstructs both initial producer hashes.'},
  inputHashes:files,tests,
  virtualEvents:{scenarios:accuracy.results.length,events:accuracy.results.reduce((n,r)=>n+r.eventCount,0),
    maxErrorPs:accuracy.maxErrorPs,tolerancePs:accuracy.tolerancePs,meaning:accuracy.meaning},
  measurements,totals:{timedRuns:timedCases.reduce((n,r)=>n+r.runs.length,0),warmups:timedCases.reduce((n,r)=>n+r.warmups.length,0),
    checkpointComparisons:timedCases.reduce((n,r)=>n+r.validation.checkpointsCompared,0)},
  limits:['Coupled Node execution, no exclusive subsystem duration or browser real-time claim.',
    'Synthetic 20 MHz software oscillator profile is not measured ATtiny13A RC calibration.',
    'Sparse native PC positions and static code shape do not establish a causal timing breakdown.',
    'Music/capture controls include possible small losses and large host variation; retain every trial.',
    'Virtual event fixtures validate the configured digital model, not silicon or unresolved device modes.']};
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({nativeBytes:native.length,passingTests:tests['full.tap'].pass+tests['shared.tap'].pass,...report.totals,matchedPositivePairs:16}));
