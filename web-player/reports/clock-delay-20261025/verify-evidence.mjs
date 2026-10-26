import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex'),git=p=>execFileSync('git',['show','410be01:'+p],{cwd:root,maxBuffer:4*1024*1024});
const manifest=json('native-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const header='web-player/native/peripherals/device_clock.h';
assert.deepEqual(Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==old.inputs[p]),[header]);
for(const [path,hash]of Object.entries(manifest.inputs))assert.equal(sha(path===header?read('candidate-device-clock.h.txt'):git(path).toString().replaceAll('\r\n','\n')),hash,path);
const binary=readFileSync(new URL('candidate.wasm',import.meta.url));assert.equal(binary.length,117951);
assert.equal(sha(binary),'dc2c069206ee8079b7d5a0ddd46f5c3beb2f80319acd6f01fc019d001c934c9f');
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);
assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)),[]);
assert.equal(new WebAssembly.Instance(new WebAssembly.Module(binary)).exports.memory.buffer.byteLength,131072);
const validation=json('validation.json'),screen=json('screen.json');
for(const r of [validation,screen]){
  assert.equal(r.complete,true);assert.equal(r.parameters.changeSet,'clock-delay');
  for(const [p,digest]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(p==='web-player/scripts/benchmark-runtime-controls.mjs'?read('harness-source.txt'):git(p).toString().replaceAll('\r\n','\n')),digest,p);
  assert.equal(r.provenance.runtimes.oldA.sha256,old.artifacts['attiny13a.wasm']);
  assert.equal(r.provenance.runtimes.newA.sha256,manifest.artifacts['attiny13a.wasm']);
  for(const row of r.results){
    const runs=[...row.warmups,...row.runs],first=runs[0];
    for(const run of runs)for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.deepEqual(run[key],first[key]);
    for(const flag of Object.values(row.validation))if(typeof flag==='boolean')assert.equal(flag,true);
  }
}
assert.equal(validation.mode,'validation');assert.equal(validation.results.length,13);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.length,0),26);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.reduce((s,x)=>s+x.checkpoints,0),0),168);
assert.equal(screen.mode,'timing');assert.equal(screen.results.length,3);
let timed=0,warmups=0,snapshots=0;
for(const row of screen.results){
  assert.deepEqual(controlRatios(row.runs,screen.parameters.trials),row.summary.ratios);
  timed+=row.runs.length;warmups+=row.warmups.length;snapshots+=[...row.runs,...row.warmups].reduce((n,r)=>n+r.checkpoints,0);
}
assert.deepEqual([timed,warmups,snapshots],[96,48,1728]);
const functions=json('function-analysis.json');assert.equal(functions.counts.identical,202);
assert.equal(functions.changed.length,1);assert.equal(functions.changed[0].symbol,'duration');
assert.deepEqual([functions.changed[0].before.bytes,functions.changed[0].after.bytes],[526,576]);
for(const line of ['tests 1674','pass 1674','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
console.log(JSON.stringify({candidateSha256:sha(binary),candidateTests:1674,validationCases:13,timed,warmups,snapshots,retained:false}));
