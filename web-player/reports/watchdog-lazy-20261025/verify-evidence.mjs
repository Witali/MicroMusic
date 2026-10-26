import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex');
const git=(p,ref='2c52cc1')=>execFileSync('git',['show',ref+':'+p],{cwd:root,maxBuffer:4*1024*1024});
const manifest=json('native-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const adaptations={'web-player/native/peripherals/device.c':'candidate-device.c.txt',
  'web-player/native/devices/attiny13a/clki_board.inc':'candidate-clki-board.inc.txt'};
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],old[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==old.inputs[p]),Object.keys(adaptations));
for(const [p,digest]of Object.entries(manifest.inputs))
  assert.equal(sha(adaptations[p]?read(adaptations[p]):git(p).toString().replaceAll('\r\n','\n')),digest,p);
for(const [p,ref,n]of [
  ['web-player/tests/device-watchdog-clock.test.mjs','1c3910e','retained-test-source.txt'],
  ['web-player/scripts/benchmark-runtime-controls.mjs','1c3910e','harness-source.txt'],
  ['web-player/scripts/trace-device-calls.mjs','cccf9c3','trace-source.txt']])
  assert.equal(git(p,ref).toString().replaceAll('\r\n','\n'),read(n));
const binary=readFileSync(new URL('candidate.wasm',import.meta.url)),module=new WebAssembly.Module(binary);
assert.equal(binary.length,119377);assert.equal(sha(binary),'c3995caa57e94c5618153dd906bf5b4366870a26f93caf517c84e80dc44a62e0');
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
assert.equal(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').length,109);
assert.equal(sha(git('web-player/wasm/attiny13a.wasm')),old.artifacts['attiny13a.wasm']);
assert.equal(old.artifacts['attiny13a.wasm'],'953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0');
const validation=json('validation.json'),screen=json('screen.json'),kernels=json('kernels.json');
const totals={timed:0,warmups:0,snapshots:0,comparisons:0};
for(const r of [validation,screen,kernels]){
  assert.equal(r.complete,true);assert.equal(r.parameters.changeSet,'watchdog-lazy');
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
    assert.equal(row.translationSha256,validation.results.find(x=>x.id===row.id).translationSha256);
    if(r!==validation){
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
assert.deepEqual(totals,{timed:256,warmups:128,snapshots:2112,comparisons:2068});
const baselineTrace=json('baseline-trace.json'),candidateTrace=json('candidate-trace.json');
const count=(r,name)=>BigInt(r.counts.find(x=>x.name===name).count);
for(const [trace,m]of [[baselineTrace,old],[candidateTrace,manifest]]){
  assert.equal(trace.complete,true);assert.equal(trace.productionRuntimeSha256,m.artifacts['attiny13a.wasm']);
  assert.equal(trace.results.length,5);assert.equal(trace.policy.physicalFirmware,true);
  for(const [p,digest]of Object.entries(trace.sourceSha256NormalizedLF)){
    const contents=p==='web-player/scripts/trace-device-calls.mjs'?read('trace-source.txt'):
      trace===candidateTrace&&adaptations[p]?read(adaptations[p]):git(p).toString().replaceAll('\r\n','\n');
    assert.equal(sha(contents),digest,p);
  }
  for(const row of trace.results){assert.equal(row.productionEquality,true);assert.equal(row.timeUnits,'picoseconds');}
  assert.equal(trace.results.find(x=>x.requestedFirmwareId==='hq4-chego-auto').firmwareId,'hq4-chego-tiny');
}
for(const a of baselineTrace.results){
  const b=candidateTrace.results.find(x=>x.id===a.id);assert.ok(b);
  for(const key of ['rawPcmSha256','pinSha256','cycles','flashSha256'])assert.equal(a[key],b[key]);
  assert.equal(count(a,'rational'),count(a,'elapse'));assert.equal(count(b,'rational'),0n);
  assert.equal(count(b,'watchdog_sync'),0n);
  for(const key of ['elapse','analog_adc_advance','system_watchdog_advance','next_event_scan'])assert.equal(count(a,key),count(b,key));
}
const functions=json('function-analysis.json');
assert.deepEqual(functions.counts,{identical:168,'relocation-only':6,'body-changed':29,added:0,removed:0});
for(const line of ['tests 1687','pass 1687','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
for(const line of ['tests 10','pass 10','fail 0','skipped 0'])assert.ok(read('restored-test.tap').includes('# '+line+'\n'));
assert.ok(read('candidate-test-source.txt').includes('conversion really deferred'));
assert.ok(!read('retained-test-source.txt').includes('wdt_at'));
console.log(JSON.stringify({decision:'rejected',candidateSha256:sha(binary),tests:1687,restoredTests:10,validationCases:15,tracePairs:5,...totals}));
