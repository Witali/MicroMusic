// Retain completed observations from the rejected zero-ratio experiment.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {controlRatios} from './lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string',default:'build/clock-zero-20261030'},
  output:{type:'string',default:'build/clock-zero-evidence.json'}}});
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n');
const raw=name=>read(resolve(values.input,name)),json=name=>JSON.parse(raw(name));
const hash=b=>createHash('sha256').update(b).digest('hex');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const baseline=git('rev-parse','702450d8^{commit}').toString().trim();
const nativePath='web-player/wasm/attiny13a.wasm',headerPath='web-player/native/peripherals/device_clock.h';
const original=git('show',baseline+':'+nativePath),candidate=raw('candidate/attiny13a.wasm');
const originalManifest=JSON.parse(git('show',baseline+':web-player/wasm/device-build.json'));
const candidateManifest=json('candidate/device-build.json');
assert.deepEqual(read(nativePath),original,'Production native must be restored');
assert.equal(text(headerPath),git('show',baseline+':'+headerPath).toString().replaceAll('\r\n','\n'));
assert.deepEqual(JSON.parse(text('web-player/wasm/device-build.json')),originalManifest);
assert.equal(hash(candidate),candidateManifest.artifacts['attiny13a.wasm']);
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(candidateManifest[key],originalManifest[key]);
const guard=' /* A zero elapsed span with a proper carry has no quotient to calculate.\n'+
  '  * Keep invalid divisors and carry normalization on their original paths. */\n'+
  ' if (!a && carry<divisor) {\n  *quotient=0; *remainder=carry; return 1;\n }\n';
const anchor=' if (!divisor) return 0;\n';assert.equal(text(headerPath).split(anchor).length,2);
const candidateHeader=text(headerPath).replace(anchor,anchor+guard);
assert.equal(raw('candidate/device_clock.h').toString().replaceAll('\r\n','\n'),candidateHeader);
for(const [path,expected]of Object.entries(candidateManifest.inputs))
  assert.equal(hash(path===headerPath?candidateHeader:text(path)),expected,path);
for(const binary of [original,candidate]){
  const module=new WebAssembly.Module(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
  assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
}
function bodies(data){
  let p=8;const u32=()=>{let n=0;for(let s=0;s<35;s+=7){assert.ok(p<data.length);const b=data[p++];n+=(b&127)*2**s;if(!(b&128))return n;}assert.fail('Invalid LEB');};
  while(p<data.length){const id=data[p++],end=u32()+p;assert.ok(end<=data.length);
    if(id===10){const out=[];for(let n=u32();n;n--){const size=u32();assert.ok(p+size<=end);out.push(data.subarray(p,p+size));p+=size;}assert.equal(p,end);return out;}p=end;}
  assert.fail('Missing code section');
}
const oldBodies=bodies(original),newBodies=bodies(candidate);assert.equal(oldBodies.length,newBodies.length);
const changedBodies=oldBodies.flatMap((body,index)=>body.equals(newBodies[index])?[]:
  [{index,beforeBytes:body.length,afterBytes:newBodies[index].length}]);
assert.deepEqual(changedBodies,[{index:155,beforeBytes:522,afterBytes:539}]);
const inputs={},captures=[];let checkpoints=0,timedRuns=0,warmups=0;
for(const name of ['parity','screen','confirmation']){
  const r=json(name+'.json');inputs[name+'.json']=hash(raw(name+'.json'));
  assert.equal(r.complete,name!=='confirmation');assert.equal(r.results.length,{parity:16,screen:4,confirmation:1}[name]);
  for(const [label,version]of Object.entries(r.provenance.runtimes)){
    const expected=label.startsWith('old')?originalManifest:candidateManifest;
    assert.equal(version.sha256,expected.artifacts['attiny13a.wasm']);assert.deepEqual(version.inputs,expected.inputs);
  }
  for(const [path,expected]of Object.entries(r.provenance.sourceSha256))assert.equal(hash(text(path)),expected,path);
  const cases=r.results.map(row=>{
    assert.ok(Object.values(row.validation).every(v=>typeof v==='number'||v===true));
    const runs=[...row.warmups,...row.runs],reference=runs[0];assert.ok(reference);
    for(const run of runs)for(const key of ['rawSha256','architectureSha256','pinSha256'])assert.equal(run[key],reference[key]);
    checkpoints+=row.validation.checkpointsCompared;
    const common={id:row.id,options:row.options,frames:row.frames,channels:row.channels,
      flashSha256:row.flashSha256,translationSha256:row.translationSha256,
      validation:row.validation,outputHashes:Object.fromEntries(['rawSha256','architectureSha256','pinSha256'].map(k=>[k,reference[k]]))};
    if(name==='parity')return common;
    assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
    assert.deepEqual(controlRatios(row.runs,r.parameters.trials),row.summary.ratios);
    timedRuns+=row.runs.length;warmups+=row.warmups.length;
    return {...common,runs:row.runs.map(({trial,position,variant,ms})=>({trial,position,variant,ms})),
      warmups:row.warmups.map(({pass,position,variant,ms})=>({pass,position,variant,ms})),
      ratios:row.summary.ratios};
  });
  captures.push({id:name,complete:r.complete,parameters:r.parameters,host:r.host,cases,
    ...(name==='confirmation'?{termination:'Stopped intentionally after the first completed longer workload failed the performance gate. Unpublished partial work is excluded.'}:{})});
}
const taps={};
for(const name of ['baseline','clock','restored']){
  const b=raw(name+'.tap'),t=b.toString(),counts=Object.fromEntries(['tests','pass','fail','skipped','cancelled','todo'].map(k=>{
    const m=t.match(new RegExp('^# '+k+' (\\d+)$','m'));assert.ok(m);return [k,Number(m[1])];}));
  assert.equal(counts.tests,counts.pass);assert.equal(counts.fail+counts.skipped+counts.cancelled+counts.todo,0);
  taps[name]={...counts,sha256:hash(b)};
}
assert.equal(taps.baseline.pass,22);assert.equal(taps.clock.pass,7);assert.equal(taps.restored.pass,23);
const sources=['web-player/scripts/verify-clock-zero.mjs','web-player/scripts/benchmark-runtime-controls.mjs',
  'web-player/scripts/lib/runtime-control-design.mjs','web-player/tests/device-clock.test.mjs',headerPath];
const report={schema:'micromusic-clock-zero-rejected-v1',baselineCommit:baseline,decision:'rejected',
  productionRestored:true,baseline:{bytes:original.length,sha256:hash(original)},
  candidate:{bytes:candidate.length,sha256:hash(candidate),headerSha256:hash(candidateHeader),
    insertionAfter:anchor,insertedText:guard,changedBodies},
  sources:Object.fromEntries(sources.map(p=>[p,hash(text(p))])),inputs,taps,
  completedTimedRuns:timedRuns,completedWarmups:warmups,exactCheckpoints:checkpoints,captures,
  meaning:'The zero-product shortcut is mathematically exact and passes scoped parity, but longer Rhythmic measurements do not establish a useful speedup. Only the original production arithmetic remains enabled. No full candidate runtime suite, real-time or silicon claim.'};
const out=resolve(root,values.output);mkdirSync(dirname(out),{recursive:true});writeFileSync(out,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({decision:report.decision,productionRestored:true,timedRuns,warmups,checkpoints}));
