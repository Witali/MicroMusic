import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
import {parseArgs} from 'node:util';

const {values}=parseArgs({options:{rebuild:{type:'boolean',default:false},variant:{type:'string',default:'v2'}}});
assert.ok(['v1','v2'].includes(values.variant));
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const bytes=p=>readFileSync(join(dir,p)),read=p=>bytes(p).toString().replaceAll('\r\n','\n');
const json=p=>JSON.parse(read(p)),sha=b=>createHash('sha256').update(b).digest('hex');
const baseline='61bafe9f',git=p=>execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:16*1024*1024});
const original=JSON.parse(git('web-player/wasm/device-build.json')),evidence=json('evidence.json');
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.wasm')?bytes(p):read(p)),h,p);
const design=await import('data:text/javascript;base64,'+git('web-player/scripts/lib/runtime-control-design.mjs').toString('base64'));
const replacements={
  'web-player/native/peripherals/device.c':'candidate-device.c',
  'web-player/native/devices/attiny13a/clki_board.inc':'candidate-clki_board.inc'
};
const summaries={};
for(const [variant,prefix]of [['v1','v1/'],['v2','']]){
  const m=json(prefix+'candidate-manifest.json');
  const input=p=>replacements[p]?read(prefix+replacements[p]):git(p).toString().replaceAll('\r\n','\n');
  assert.equal(sha(bytes(prefix+'candidate.wasm')),m.artifacts['attiny13a.wasm']);
  for(const [p,h]of Object.entries(m.inputs))assert.equal(sha(input(p)),h,prefix+p);
  for(const k of ['exports','flags','compilerVersion','sources'])assert.deepEqual(m[k],original[k]);
  assert.deepEqual(Object.keys(m.inputs).filter(p=>m.inputs[p]!==original.inputs[p]),Object.keys(replacements));
  const module=new WebAssembly.Module(bytes(prefix+'candidate.wasm'));
  assert.deepEqual(WebAssembly.Module.imports(module),[]);
  assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
  assert.equal(WebAssembly.Module.exports(module).filter(x=>x.kind==='function').length,109);
  let timings=0,warmups=0,snapshots=0,comparisons=0;
  for(const name of variant==='v1'?['parity','screen','confirmation']:['parity','confirmation']){
    const r=json(prefix+name+'.json');assert.equal(r.complete,true);
    for(const label of ['oldA','oldB'])assert.equal(r.provenance.runtimes[label].sha256,original.artifacts['attiny13a.wasm']);
    for(const label of ['newA','newB'])assert.equal(r.provenance.runtimes[label].sha256,m.artifacts['attiny13a.wasm']);
    for(const [p,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(p==='web-player/scripts/benchmark-runtime-controls.mjs'?
      read(prefix+'benchmark-source.txt'):git(p).toString().replaceAll('\r\n','\n')),h,p);
    for(const row of r.results){
      const runs=[...row.warmups,...row.runs],first=runs[0];
      const matching=json(prefix+'parity.json').results.find(x=>x.id===row.id);assert.ok(matching);
      assert.equal(row.translationSha256,matching.translationSha256);
      for(const x of runs){
        for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(x[k],first[k]);
        assert.deepEqual(x.finalState,first.finalState);snapshots+=x.checkpoints;
      }
      assert.equal(row.validation.checkpointsCompared,(runs.length-1)*first.checkpoints);
      comparisons+=row.validation.checkpointsCompared;
      if(name!=='parity'){
        assert.deepEqual(row.summary.ratios,design.controlRatios(row.runs,r.parameters.trials));
        timings+=row.runs.length;warmups+=row.warmups.length;
      }
    }
  }
  const comparison=json(prefix+'function-comparison.json');
  assert.equal(comparison.productionUnmodified,true);
  assert.equal(comparison.before.rebuildByteEqual,true);assert.equal(comparison.after.rebuildByteEqual,true);
  assert.equal(comparison.before.runtimeSha256,original.artifacts['attiny13a.wasm']);
  assert.equal(comparison.after.runtimeSha256,m.artifacts['attiny13a.wasm']);
  assert.deepEqual(comparison.counts,{identical:variant==='v1'?194:195,'relocation-only':0,'body-changed':variant==='v1'?9:8,added:0,removed:0});
  // The new certificate uses old padding; no existing board field shifts.
  for(const n of ['baseline','candidate'])assert.match(read(prefix+n+'-runtime-link.map'),/^\s+fa10\s+0\s+b2e8\s+board\r?$/m);
  const tests=variant==='v1'?16:18;
  for(const n of ['tests '+tests,'pass '+tests,'fail 0','skipped 0'])assert.ok(read(prefix+'contract-test.tap').includes('# '+n+'\n'));
  summaries[variant]={timings,warmups,snapshots,comparisons,contractTests:tests};
}
const on=json('trace-on.json'),off=json('trace-off.json'),m=json('candidate-manifest.json');
for(const [trace,full]of [[on,false],[off,true]]){
  assert.equal(trace.complete,true);assert.equal(trace.policy.gpioFullDispatch,full);
  assert.equal(trace.productionRuntimeSha256,m.artifacts['attiny13a.wasm']);
  for(const [p,h]of Object.entries(trace.sourceSha256NormalizedLF))assert.equal(sha(
    p==='web-player/scripts/trace-device-calls.mjs'?read('trace-source.txt'):
    replacements[p]?read(replacements[p]):git(p).toString().replaceAll('\r\n','\n')),h,p);
}
for(const a of on.results){
  const b=off.results.find(x=>x.id===a.id);assert.ok(b);
  assert.equal(a.productionEquality,true);assert.equal(b.productionEquality,true);
  for(const k of ['frames','cycles','flashSha256','timeUnits','divisor','rawPcmSha256','pinSha256'])assert.equal(a[k],b[k]);
  if(a.id.startsWith('kernel-clki-'))assert.deepEqual(a.counts,b.counts);
}
for(const n of ['tests 1722','pass 1722','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+n+'\n'));
function verifyRebuiltParity(repeated,prefix=''){
 assert.equal(repeated.complete,true);assert.equal(repeated.results.length,15);
 for(const row of repeated.results){
  const reference=json(prefix+'parity.json').results.find(x=>x.id===row.id);assert.ok(reference);
  assert.equal(row.translationSha256,reference.translationSha256);
  for(const x of row.runs){
    for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(x[k],reference.runs[0][k]);
    assert.deepEqual(x.finalState,reference.runs[0].finalState);
  }
 }
}
if(existsSync(join(dir,'rebuild-parity.json')))verifyRebuiltParity(json('rebuild-parity.json'));
else assert.equal(values.rebuild,true,'An archived rebuilt parity matrix is required for static replay');
if(values.rebuild){
  const prefix=values.variant==='v1'?'v1/':'',manifest=json(prefix+'candidate-manifest.json');
  const base=join(root,'build/replays');mkdirSync(base,{recursive:true});const target=mkdtempSync(join(base,'gpio-idle-'+values.variant+'-'));
  const put=(p,b)=>{const dest=join(target,p);mkdirSync(dirname(dest),{recursive:true});writeFileSync(dest,b);};
  const libs=execFileSync('git',['ls-tree','-r','--name-only',baseline,'web-player/lib'],{cwd:root,encoding:'utf8'}).trim().split('\n');
  const paths=new Set([...libs,...Object.keys(manifest.inputs),'web-player/package.json','web-player/firmware.json','web-player/hq4-firmware.json',
    'web-player/scripts/lib/runtime-control-design.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs','web-player/tests/analog-test-build.mjs']);
  for(const p of paths)put(p,replacements[p]?bytes(prefix+replacements[p]):git(p));
  put('web-player/scripts/benchmark-runtime-controls.mjs',bytes(prefix+'benchmark-source.txt'));
  put('web-player/tests/device-gpio-idle.test.mjs',bytes(prefix+'contract-test-source.txt'));
  const sdk=process.env.EMSDK||'C:/Work/MicroMusic/build/toolchains/emscripten-6.0.12';
  execFileSync(process.execPath,['web-player/scripts/build-device-wasm.mjs','--emsdk',sdk],{cwd:target,stdio:'inherit'});
  assert.equal(sha(readFileSync(join(target,'web-player/wasm/attiny13a.wasm'))),manifest.artifacts['attiny13a.wasm']);
  execFileSync(process.execPath,['--test','web-player/tests/device-gpio-idle.test.mjs'],{cwd:target,stdio:'inherit'});
  execFileSync(process.execPath,['web-player/scripts/benchmark-runtime-controls.mjs','--baseline-ref',baseline,
    '--change-set','gpio-idle','--validate-only','--out','parity-replay.json'],{cwd:target,stdio:'inherit'});
  verifyRebuiltParity(JSON.parse(readFileSync(join(target,'parity-replay.json'),'utf8')),prefix);
  console.log('Isolated replay: '+target);
}
console.log(JSON.stringify({variants:summaries,tracePairs:on.results.length,fullRegressionTests:1722}));
