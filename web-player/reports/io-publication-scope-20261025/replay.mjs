import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const bytes=p=>readFileSync(join(dir,p)),read=p=>bytes(p).toString().replaceAll('\r\n','\n');
const json=p=>JSON.parse(read(p)),sha=b=>createHash('sha256').update(b).digest('hex');
const git=p=>execFileSync('git',['show','69c40b97:'+p],{cwd:root,maxBuffer:16*1024*1024});
const retained=json('evidence.json');
for(const [p,h]of Object.entries(retained.filesSha256))assert.equal(sha(p.endsWith('.wasm')?bytes(p):read(p)),h,p);
for(const [p,h]of Object.entries(retained.restoredSourceSha256))assert.equal(sha(git(p).toString().replaceAll('\r\n','\n')),h,p);
const m=json('candidate-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const overrides={
  'web-player/native/peripherals/device.c':'candidate-device.c',
  'web-player/native/peripherals/device.h':'candidate-device.h',
  'web-player/native/avr-device.inc':'candidate-avr-device.inc',
  'web-player/lib/avr-transpiled-runtime.js':'candidate-host.js',
  'web-player/lib/attiny13a-package.js':'candidate-package.js'};
assert.equal(sha(bytes('candidate.wasm')),m.artifacts['attiny13a.wasm']);
assert.equal(bytes('candidate.wasm').length,m.bytes);
for(const [p,h]of Object.entries(m.inputs))assert.equal(sha(overrides[p]?read(overrides[p]):git(p).toString().replaceAll('\r\n','\n')),h,p);
const design=await import('data:text/javascript;base64,'+git('web-player/scripts/lib/runtime-control-design.mjs').toString('base64'));
let timings=0,warmups=0,snapshots=0,comparisons=0;
for(const name of ['parity','screen','confirmation']){
  const r=json(name+'.json');assert.equal(r.complete,true);
  assert.equal(r.provenance.runtimes.oldA.sha256,old.artifacts['attiny13a.wasm']);
  assert.equal(r.provenance.runtimes.newA.sha256,m.artifacts['attiny13a.wasm']);
  for(const [p,h]of Object.entries(r.provenance.sourceSha256))assert.equal(sha(
    p==='web-player/scripts/benchmark-runtime-controls.mjs'?read('benchmark-source.txt'):
      overrides[p]?read(overrides[p]):git(p).toString().replaceAll('\r\n','\n')),h,p);
  for(const row of r.results){
    const runs=[...row.warmups,...row.runs],first=runs[0];
    for(const x of runs){
      for(const k of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.equal(x[k],first[k]);
      assert.deepEqual(x.finalState,first.finalState);snapshots+=x.checkpoints;
    }
    assert.equal(row.validation.checkpointsCompared,(runs.length-1)*first.checkpoints);
    comparisons+=row.validation.checkpointsCompared;
    if(name!=='parity'){assert.deepEqual(row.summary.ratios,design.controlRatios(row.runs,r.parameters.trials));timings+=row.runs.length;warmups+=row.warmups.length;}
  }
}
const on=json('trace-on.json'),off=json('trace-off.json');
assert.equal(on.complete,true);assert.equal(off.complete,true);
assert.equal(on.productionRuntimeSha256,m.artifacts['attiny13a.wasm']);
for(const [i,r]of on.results.entries()){
  const other=off.results[i];assert.equal(r.id,other.id);assert.equal(r.productionEquality,true);assert.equal(other.productionEquality,true);
  assert.equal(r.rawPcmSha256,other.rawPcmSha256);assert.equal(r.pinSha256,other.pinSha256);
  const count=(row,name)=>BigInt(row.counts.find(x=>x.name===name).count);
  for(const fn of ['service_end','mirror_dynamic'])assert.equal(count(r,fn),count(other,fn));
  assert.ok(count(r,'mirror_configuration')<count(other,'mirror_configuration'));
}
assert.ok(read('candidate-full-test.tap').includes('# pass 1711\n'));
assert.ok(read('restored-full-test.tap').includes('# pass 1704\n'));
assert.ok(read('rebuild-replay.log').includes('# pass 15\n'));
assert.equal(retained.restoredRuntimeSha256,old.artifacts['attiny13a.wasm']);
if(process.argv.includes('--rebuild')){
  const base=join(root,'build/replays');mkdirSync(base,{recursive:true});
  const target=mkdtempSync(join(base,'io-publication-'));
  const put=(p,b)=>{const dest=join(target,p);mkdirSync(dirname(dest),{recursive:true});writeFileSync(dest,b);};
  const libs=execFileSync('git',['ls-tree','-r','--name-only','69c40b97','web-player/lib'],{cwd:root,encoding:'utf8'}).trim().split('\n');
  const paths=new Set([...libs,...Object.keys(m.inputs),'web-player/package.json','web-player/firmware.json','web-player/hq4-firmware.json',
    'web-player/scripts/lib/runtime-control-design.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs']);
  for(const p of paths)put(p,overrides[p]?bytes(overrides[p]):git(p));
  put('web-player/scripts/benchmark-runtime-controls.mjs',bytes('benchmark-source.txt'));
  put('web-player/tests/device-io-scope.test.mjs',bytes('scope-test-source.txt'));
  const sdk=process.env.EMSDK||'C:/Work/MicroMusic/build/toolchains/emscripten-6.0.12';
  execFileSync(process.execPath,['web-player/scripts/build-device-wasm.mjs','--emsdk',sdk],{cwd:target,stdio:'inherit'});
  assert.equal(sha(readFileSync(join(target,'web-player/wasm/attiny13a.wasm'))),m.artifacts['attiny13a.wasm']);
  execFileSync(process.execPath,['--test','web-player/tests/device-io-scope.test.mjs'],{cwd:target,stdio:'inherit'});
  execFileSync(process.execPath,['web-player/scripts/benchmark-runtime-controls.mjs','--baseline-ref','69c40b97',
    '--change-set','io-publication-scope','--validate-only','--out','parity-replay.json'],{cwd:target,stdio:'inherit'});
  console.log('Isolated replay: '+target);
}
console.log(JSON.stringify({timings,warmups,snapshots,comparisons,tracePairs:on.results.length,candidateTests:1711}));
