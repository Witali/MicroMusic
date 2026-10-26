import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex');
const git=(p,ref='77c354b')=>execFileSync('git',['show',ref+':'+p],{cwd:root,maxBuffer:4*1024*1024});
const manifest=json('native-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const adaptations={'web-player/native/peripherals/device.c':'candidate-device.c.txt',
  'web-player/native/devices/attiny13a/clki_board.inc':'candidate-clki-board.inc.txt'};
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],old[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==old.inputs[p]),Object.keys(adaptations));
for(const [p,digest]of Object.entries(manifest.inputs))
  assert.equal(sha(adaptations[p]?read(adaptations[p]):git(p).toString().replaceAll('\r\n','\n')),digest,p);
assert.equal(git('web-player/tests/device-watchdog-clock.test.mjs','41c9936').toString().replaceAll('\r\n','\n'),read('test-source.txt'));
assert.equal(git('web-player/scripts/benchmark-runtime-controls.mjs','e371c5d').toString().replaceAll('\r\n','\n'),read('harness-source.txt'));
const binary=readFileSync(new URL('candidate.wasm',import.meta.url)),module=new WebAssembly.Module(binary);
assert.equal(binary.length,118183);assert.equal(sha(binary),'bb2885077843d09ca030579cefa6e503055b1092eb862f24b4f584f7a4d45565');
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
assert.equal(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').length,109);
assert.equal(sha(git('web-player/wasm/attiny13a.wasm')),old.artifacts['attiny13a.wasm']);
assert.equal(old.artifacts['attiny13a.wasm'],'953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0');
const validation=json('validation.json'),screen=json('screen.json');
const totals={timed:0,warmups:0,snapshots:0,comparisons:0};
for(const r of [validation,screen]){
  assert.equal(r.complete,true);assert.equal(r.parameters.changeSet,'watchdog-period');
  for(const [p,digest]of Object.entries(r.provenance.sourceSha256))
    assert.equal(sha(p==='web-player/scripts/benchmark-runtime-controls.mjs'?read('harness-source.txt'):git(p).toString().replaceAll('\r\n','\n')),digest,p);
  assert.deepEqual(r.provenance.changedInputs,Object.keys(adaptations));
  for(const label of ['oldA','oldB'])assert.equal(r.provenance.runtimes[label].sha256,old.artifacts['attiny13a.wasm']);
  for(const label of ['newA','newB'])assert.equal(r.provenance.runtimes[label].sha256,manifest.artifacts['attiny13a.wasm']);
  for(const row of r.results){
    const observations=[...row.warmups,...row.runs],first=observations[0];
    for(const x of observations){
      for(const key of ['rawSha256','architectureSha256','pinSha256','checkpoints'])assert.deepEqual(x[key],first[key]);
      if(!row.id.startsWith('kernel')||row.watchdogEnabled)assert.ok(x.finalState.irqs>0);
    }
    for(const flag of Object.values(row.validation))if(typeof flag==='boolean')assert.equal(flag,true);
    const reference=validation.results.find(x=>x.id===row.id);assert.ok(reference);
    assert.equal(row.translationSha256,reference.translationSha256);
    if(r===screen){
      assert.equal(r.parameters.trials,8);assert.equal(r.parameters.warmups,4);
      assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);
      assert.deepEqual(controlRatios(row.runs,8),row.summary.ratios);
      totals.timed+=row.runs.length;totals.warmups+=row.warmups.length;
      totals.snapshots+=observations.reduce((n,x)=>n+x.checkpoints,0);totals.comparisons+=row.validation.checkpointsCompared;
    }
  }
}
assert.equal(validation.mode,'validation');assert.equal(validation.results.length,15);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.length,0),30);
assert.equal(validation.results.reduce((n,r)=>n+r.runs.reduce((s,x)=>s+x.checkpoints,0),0),176);
assert.equal(validation.results.reduce((n,r)=>n+r.validation.checkpointsCompared,0),88);
assert.equal(validation.results.filter(r=>r.watchdogEnabled).length,2);assert.equal(screen.results.length,4);
assert.deepEqual(totals,{timed:128,warmups:64,snapshots:1824,comparisons:1786});
for(const row of screen.results)assert.ok(row.summary.ratios.crossVersion.median<1);
const functions=json('function-analysis.json');
assert.deepEqual(functions.counts,{identical:195,'relocation-only':0,'body-changed':8,added:0,removed:0});
for(const [symbol,before,after]of [['elapse',489,575],['next_event',3351,3367],['reset_startup',778,808]]){
  const f=functions.changed.find(x=>x.symbol===symbol);assert.equal(f.before.bytes,before);assert.equal(f.after.bytes,after);
}
for(const line of ['tests 1681','pass 1681','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
for(const line of ['tests 4','pass 4','fail 0','skipped 0'])assert.ok(read('restored-test.tap').includes('# '+line+'\n'));
assert.ok(read('node-inlining-options.txt').includes('--no-experimental-wasm-inlining'));
console.log(JSON.stringify({decision:'rejected',candidateSha256:sha(binary),tests:1681,restoredTests:4,validationCases:15,...totals}));
