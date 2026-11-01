// Verify the completed checked-overflow screen; never adopt the candidate.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname,parse} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {controlRatios} from './lib/runtime-control-design.mjs';
import {compileAnalog} from '../tests/analog-test-build.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string',default:'build/clock-intrinsic-20261101'},
  reconstruction:{type:'string',default:'build/clock-intrinsic-reconstruction-20261101'},
  output:{type:'string',default:'build/clock-intrinsic-evidence.json'},emsdk:{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n'),sha=b=>createHash('sha256').update(b).digest('hex');
const raw=name=>read(join(values.input,name)),json=name=>JSON.parse(raw(name));
const git=(ref,path)=>execFileSync('git',['show',ref+':'+path],{cwd:root,maxBuffer:8*1024*1024});
const baseline='103ca59a',producer='2fb13f82',native='web-player/wasm/attiny13a.wasm',header='web-player/native/peripherals/device_clock.h';
const old=git(baseline,native),candidate=raw('shadow/'+native),base=JSON.parse(git(baseline,'web-player/wasm/device-build.json')),
  manifest=json('shadow/web-player/wasm/device-build.json'),candidateHeader=text(join(values.input,'candidate-device-clock.h'));
assert.ok(read(native).equals(old));assert.equal(text(header),git(baseline,header).toString().replaceAll('\r\n','\n'));
assert.deepEqual(JSON.parse(text('web-player/wasm/device-build.json')),base);
assert.equal(sha(candidate),'19b325dc8a79730a7c9cb197879b838ff6f5f6d61312aed9bd830529cc438e1f');
assert.equal(sha(candidateHeader),'ac430ead2893c05682cf10c572b42966cc4a20bbf8dcb772f0ae18cc3d1e3bc9');
assert.equal(manifest.artifacts['attiny13a.wasm'],sha(candidate));
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],base[key]);
for(const [path,h]of Object.entries(manifest.inputs))assert.equal(sha(path===header?candidateHeader:git(baseline,path).toString().replaceAll('\r\n','\n')),h);
assert.ok(read(join(values.reconstruction,'shadow',native)).equals(candidate));
const reconstruction=JSON.parse(text(join(values.reconstruction,'build-proof.json')));
assert.equal(reconstruction.controlSha256,sha(old));assert.equal(reconstruction.controlByteEqual,true);
for(const bytes of [old,candidate]){
  const module=new WebAssembly.Module(bytes);assert.deepEqual(WebAssembly.Module.imports(module),[]);
  assert.deepEqual(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').map(e=>e.name).sort(),[...base.exports].sort());
  const instance=new WebAssembly.Instance(module);assert.equal(instance.exports.memory.buffer.byteLength,131072);
  assert.throws(()=>instance.exports.memory.grow(1),RangeError);
}
function bodies(data){
  let p=8;const u32=()=>{let n=0;for(let s=0;s<35;s+=7){assert.ok(p<data.length);const v=data[p++];n+=(v&127)*2**s;if(!(v&128))return n;}assert.fail('Bad LEB');};
  while(p<data.length){const id=data[p++],end=u32()+p;assert.ok(end<=data.length);
    if(id===10){const rows=[];for(let n=u32();n;n--){const size=u32();assert.ok(p+size<=end);rows.push(data.subarray(p,p+size));p+=size;}assert.equal(p,end);return rows;}p=end;}
  assert.fail('Missing code section');
}
const a=bodies(old),b=bodies(candidate);assert.equal(a.length,218);assert.equal(a.length,b.length);
const changedBodies=a.flatMap((body,index)=>body.equals(b[index])?[]:[{index,beforeBytes:body.length,afterBytes:b[index].length}]);
assert.deepEqual(changedBodies,[{index:154,beforeBytes:577,afterBytes:577},{index:155,beforeBytes:522,afterBytes:532}]);
let sdk=values.emsdk||process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const path=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(path,'upstream/bin/wasm-dis.exe')))sdk=path;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Pass the registered SDK');sdk=resolve(sdk);
const disassembler=join(sdk,'upstream/bin',process.platform==='win32'?'wasm-dis.exe':'wasm-dis');
const instructionCounts=[];
for(const [variant,path]of [['baseline',join(values.input,'control-native.wasm')],['candidate',join(values.input,'shadow',native)]]){
  if(variant==='baseline')assert.ok(read(path).equals(old));
  const wat=resolve(root,values.input,variant+'-native.wat');
  const run=spawnSync(disassembler,[resolve(root,path),'-o',wat],{encoding:'utf8'});assert.equal(run.status,0,run.stderr||String(run.error));
  const source=text(wat),functions=[...source.matchAll(/^ \(func /gm)];assert.equal(functions.length,218);
  const counts=[154,155].map(index=>{
    const start=functions[index].index;let depth=0,end=start;
    for(;end<source.length;end++){if(source[end]==='(')depth++;else if(source[end]===')'&&!--depth)break;}
    assert.equal(depth,0);const body=source.slice(start,end+1);
    return {index,division:(body.match(/\bi64\.div_u\b/g)||[]).length,remainder:(body.match(/\bi64\.rem_u\b/g)||[]).length};
  });instructionCounts.push({variant,watSha256:sha(read(wat)),counts});
}
assert.deepEqual(instructionCounts.map(v=>v.counts),[
  [{index:154,division:4,remainder:0},{index:155,division:5,remainder:0}],
  [{index:154,division:4,remainder:0},{index:155,division:4,remainder:0}]]);
const captures=[],inputs={};let timedRuns=0,warmups=0,checkpoints=0;
for(const name of ['parity','screen']){
  const r=json(name+'.json');inputs[name+'.json']=sha(raw(name+'.json'));assert.equal(r.complete,true);
  assert.equal(r.mode,name==='parity'?'validation':'timing');assert.equal(r.results.length,name==='parity'?16:4);
  assert.equal(r.parameters.changeSet,'clock-intrinsic');assert.ok(r.parameters.candidateRoot.endsWith('/shadow'));
  for(const [path,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(git(producer,path).toString().replaceAll('\r\n','\n')),h);
  for(const [label,version]of Object.entries(r.provenance.runtimes)){
    const expected=label.startsWith('old')?base:manifest;assert.equal(version.sha256,expected.artifacts['attiny13a.wasm']);assert.deepEqual(version.inputs,expected.inputs);
  }
  const cases=r.results.map(row=>{
    assert.ok(Object.values(row.validation).every(v=>typeof v==='number'||v===true));
    const runs=[...row.warmups,...row.runs],reference=runs[0];
    for(const run of runs)for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(run[key],reference[key]);
    assert.equal(row.validation.checkpointsCompared,(runs.length-1)*reference.checkpoints);checkpoints+=row.validation.checkpointsCompared;
    const common={id:row.id,options:row.options,frames:row.frames,instructions:row.instructions,channels:row.channels,
      flashSha256:row.flashSha256,translationSha256:row.translationSha256,validation:row.validation,
      outputHashes:Object.fromEntries(['rawSha256','architectureSha256','pinSha256'].map(k=>[k,reference[k]]))};
    if(name==='parity'){assert.equal(row.runs.length,2);return common;}
    assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
    assert.deepEqual(controlRatios(row.runs,r.parameters.trials),row.summary.ratios);timedRuns+=row.runs.length;warmups+=row.warmups.length;
    return {...common,runs:row.runs.map(({trial,position,variant,ms})=>({trial,position,variant,ms})),
      warmups:row.warmups.map(({pass,position,variant,ms})=>({pass,position,variant,ms})),ratios:row.summary.ratios};
  });captures.push({id:name,parameters:r.parameters,host:r.host,complete:true,cases});
}
const taps={};
for(const [name,path]of [['baseline','build/clock-intrinsic-baseline-20261101.tap'],['candidate',join(values.input,'clock-tests.tap')]]){
  const bytes=read(path),t=bytes.toString();const counts=Object.fromEntries(['tests','pass','fail','skipped','cancelled','todo'].map(key=>{
    const m=t.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(m);return [key,Number(m[1])];}));
  assert.equal(counts.pass,7);assert.equal(counts.tests,7);assert.equal(counts.fail+counts.skipped+counts.cancelled+counts.todo,0);
  taps[name]={...counts,sha256:sha(bytes)};
}
const fixture=candidateHeader+'\nstatic uint64_t qv,rv;\nint ratio(uint64_t a,uint64_t b,uint64_t c,uint64_t d){return device_clock_ratio(a,b,c,d,&qv,&rv);}\n'+
  'int delay(uint64_t n,uint64_t d,uint64_t r,uint64_t p){return device_clock_delay(n,d,r,p,&qv);}\nuint64_t q(void){return qv;}\nuint64_t r(void){return rv;}\n';
const savedSDK=process.env.EMSDK;process.env.EMSDK=sdk;let create;
try{create=compileAnalog('clock-intrinsic-evidence',[],fixture);}finally{if(savedSDK===undefined)delete process.env.EMSDK;else process.env.EMSDK=savedSDK;}
const c=create(),U=(1n<<64n)-1n,u=n=>BigInt.asUintN(64,n);let count=0,seed=42n;
const check=(a,b,carry,d)=>{
  c.ratio(7n,13n,5n,11n);const before=[c.q(),c.r()],n=a*b+carry,q=d?n/d:U+1n,ok=d!==0n&&q<=U;
  assert.equal(c.ratio(a,b,carry,d),Number(ok));if(ok){assert.equal(u(c.q()),q);assert.equal(u(c.r()),n%d);}else assert.deepEqual([c.q(),c.r()],before);count++;
};
for(const a of [0n,1n,0xffffffffn,0x100000000n,U])for(const b of [0n,1n,40000000n,1000000000000n,U])
  for(const carry of [0n,1n,U])for(const d of [0n,1n,3n,1000000000000n,U])check(a,b,carry,d);
const random=()=>seed=(seed*6364136223846793005n+1442695040888963407n)&U;
for(let n=0;n<5000;n++)check(random(),random(),random(),random());assert.equal(count,5375);
const sources=['web-player/scripts/rebuild-clock-intrinsic.mjs','web-player/scripts/verify-clock-intrinsic.mjs',
  'web-player/scripts/benchmark-runtime-controls.mjs','web-player/scripts/lib/runtime-control-design.mjs',
  'web-player/tests/analog-test-build.mjs','web-player/tests/device-clock.test.mjs',header];
const report={schema:'micromusic-clock-intrinsic-rejected-v1',date:'2026-11-01',decision:'not-retained',baselineRef:baseline,
  harnessRef:producer,productionUnchanged:true,fullCandidateRuntimeSuiteRun:false,completedTimedRuns:timedRuns,completedWarmups:warmups,
  exactCheckpoints:checkpoints,arithmetic:{cases:count,BigIntOracle:true,failedOutputsPreserved:true},taps,inputs,reconstruction,changedBodies,
  instructionCounts,disassemblerSha256:sha(read(disassembler)),
  sources:Object.fromEntries(sources.map(p=>[p,sha(text(p))])),captures,
  meaning:'Checked overflow is exact and removes one static ratio division, but this screen does not establish a useful speedup. Production stays unchanged; no silicon, browser real-time or exclusive-cost claim.'};
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({timedRuns,warmups,checkpoints,arithmeticCases:count,productionUnchanged:true,decision:report.decision}));
