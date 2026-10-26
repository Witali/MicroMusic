import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex'),git=p=>execFileSync('git',['show','0906621:'+p],{cwd:root,maxBuffer:4*1024*1024});
const manifest=json('native-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const source='web-player/native/peripherals/device.c';
const retained=p=>execFileSync('git',['show','5411a35:'+p],{cwd:root,maxBuffer:4*1024*1024});
assert.equal(retained(source).toString().replaceAll('\r\n','\n'),read('candidate-device.c.txt'));
assert.equal(retained('web-player/tests/device-ns-clock.test.mjs').toString().replaceAll('\r\n','\n'),read('test-source.txt'));
assert.equal(execFileSync('git',['show','e1f93ca:web-player/scripts/benchmark-runtime-controls.mjs'],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n'),read('long-harness-source.txt'));
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],old[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==old.inputs[p]),[source]);
for(const [p,digest]of Object.entries(manifest.inputs))assert.equal(sha(p===source?read('candidate-device.c.txt'):git(p).toString().replaceAll('\r\n','\n')),digest,p);
const binary=readFileSync(new URL('candidate.wasm',import.meta.url)),module=new WebAssembly.Module(binary);
assert.equal(binary.length,117975);assert.equal(sha(binary),'953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0');
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
assert.equal(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').length,109);
const validation=json('validation.json'),screen=json('screen.json'),matrix=json('matrix.json'),repeat=json('repeat.json'),long=json('long-kernels.json');
const totals={timed:0,warmups:0,snapshots:0,comparisons:0};
for(const r of [validation,screen,matrix,repeat,long]){
  assert.equal(r.complete,true);assert.equal(r.parameters.changeSet,'ns-remainder');
  for(const [p,digest]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(p==='web-player/scripts/benchmark-runtime-controls.mjs'?read(r===long?'long-harness-source.txt':'harness-source.txt'):git(p).toString().replaceAll('\r\n','\n')),digest,p);
  for(const label of ['oldA','oldB'])assert.equal(r.provenance.runtimes[label].sha256,old.artifacts['attiny13a.wasm']);
  for(const label of ['newA','newB'])assert.equal(r.provenance.runtimes[label].sha256,manifest.artifacts['attiny13a.wasm']);
  for(const row of r.results){
    const observations=[...row.warmups,...row.runs],first=observations[0];
    for(const x of observations)for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.deepEqual(x[key],first[key]);
    if(!row.id.startsWith('kernel'))for(const x of observations)assert.ok(x.finalState.irqs>0);
    for(const flag of Object.values(row.validation))if(typeof flag==='boolean')assert.equal(flag,true);
    const reference=validation.results.find(x=>x.id===row.id);assert.ok(reference);
    assert.equal(row.translationSha256,reference.translationSha256);
    if(r!==validation){
      assert.equal(r.parameters.trials,8);assert.equal(r.parameters.warmups,4);
      assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
      assert.deepEqual(controlRatios(row.runs,8),row.summary.ratios);
      totals.timed+=row.runs.length;totals.warmups+=row.warmups.length;
      totals.snapshots+=observations.reduce((n,x)=>n+x.checkpoints,0);totals.comparisons+=row.validation.checkpointsCompared;
    }
  }
}
assert.equal(validation.mode,'validation');assert.equal(validation.results.length,13);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.length,0),26);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.reduce((s,x)=>s+x.checkpoints,0),0),168);
assert.deepEqual([...screen.results,...matrix.results].map(r=>r.id).sort(),validation.results.map(r=>r.id).sort());
assert.equal(repeat.results.length,4);assert.equal(long.results.length,2);
assert.equal(long.parameters.kernelFrames,12000);assert.equal(long.parameters.instructions,10000000);
assert.deepEqual(totals,{timed:608,warmups:304,snapshots:5952,comparisons:5828});
for(const r of [screen,repeat]){
  const row=r.results.find(x=>x.id==='hq4-chego-auto-physical');
  assert.equal(row.summary.ratios.pairs.filter(p=>p.crossVersion>1).length,8);
}
const functions=json('function-analysis.json');assert.equal(functions.counts.identical,201);
assert.deepEqual(functions.changed.map(f=>[f.symbol,f.before.bytes,f.after.bytes]),[['elapse',431,489],['next_event',3335,3351]]);
for(const line of ['tests 1677','pass 1677','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
console.log(JSON.stringify({runtimeSha256:sha(binary),tests:1677,validationCases:13,...totals,hq4FasterPairs:16}));
