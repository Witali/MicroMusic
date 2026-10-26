import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {controlRatios} from '../../scripts/lib/runtime-control-design.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8').replaceAll('\r\n','\n'),json=n=>JSON.parse(read(n));
const sha=b=>createHash('sha256').update(b).digest('hex');
const git=(p,ref='238aab2')=>execFileSync('git',['show',ref+':'+p],{cwd:root,maxBuffer:4*1024*1024});
const manifest=json('native-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const adaptations={'web-player/native/peripherals/analog.c':'candidate-analog.c.txt',
  'web-player/native/peripherals/analog_adc.c':'candidate-analog_adc.c.txt',
  'web-player/native/peripherals/analog_adc.h':'candidate-analog_adc.h.txt'};
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],old[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(p=>manifest.inputs[p]!==old.inputs[p]),Object.keys(adaptations));
for(const [p,digest]of Object.entries(manifest.inputs)){
  const source=adaptations[p]?read(adaptations[p]):git(p).toString().replaceAll('\r\n','\n');
  assert.equal(sha(source),digest,p);
  if(adaptations[p])assert.equal(git(p,'14da787').toString().replaceAll('\r\n','\n'),source);
}
for(const [p,ref,n]of [
  ['web-player/tests/analog-idle-dispatch.test.mjs','14da787','test-source.txt'],
  ['web-player/tests/fixtures/analog-unconditional-reference.c','14da787','reference-source.txt'],
  ['web-player/scripts/benchmark-runtime-controls.mjs','befa0d7','harness-source.txt'],
  ['web-player/scripts/trace-device-calls.mjs','238aab2','baseline-trace-source.txt'],
  ['web-player/scripts/trace-device-calls.mjs','befa0d7','candidate-trace-source.txt']])
  assert.equal(git(p,ref).toString().replaceAll('\r\n','\n'),read(n));
assert.equal(read('reference-source.txt').replace(/^\/\*[\s\S]*?\*\/\n/,''),git('web-player/native/peripherals/analog.c').toString().replaceAll('\r\n','\n'));
const binary=readFileSync(new URL('candidate.wasm',import.meta.url)),module=new WebAssembly.Module(binary);
assert.equal(binary.length,118071);assert.equal(sha(binary),'b6a678437b62fac3e6be1f90d90cc0bc76b9c71c0752c438504c2cda858643b4');
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
assert.equal(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').length,109);
assert.equal(sha(git('web-player/wasm/attiny13a.wasm')),old.artifacts['attiny13a.wasm']);
assert.equal(old.artifacts['attiny13a.wasm'],'953024d5087b5959814f3f577199b35c1deff20fad180e64fff56c8a81ca56c0');
const validation=json('validation.json'),screen=json('screen.json'),matrix=json('matrix.json'),long=json('long-confirmation.json');
const totals={timed:0,warmups:0,snapshots:0,comparisons:0};
for(const r of [validation,screen,matrix,long]){
  assert.equal(r.complete,true);assert.equal(r.parameters.changeSet,'adc-idle');
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
assert.deepEqual([...screen.results,...matrix.results].map(x=>x.id).sort(),validation.results.map(x=>x.id).sort());
assert.equal(long.results.length,6);assert.equal(long.parameters.frames,48000);assert.equal(long.parameters.kernelFrames,4800);
assert.deepEqual(totals,{timed:672,warmups:336,snapshots:11712,comparisons:11468});
assert.equal(long.results.find(x=>x.id==='rhythmic-physical').summary.ratios.pairs.filter(p=>p.crossVersion>1).length,8);
assert.equal(long.results.find(x=>x.id==='kernel-internal-20m-div1').summary.ratios.pairs.filter(p=>p.crossVersion>1).length,1);
const before=json('baseline-trace.json'),after=json('candidate-trace.json');
const count=(r,name)=>BigInt(r.counts.find(x=>x.name===name).count);
for(const [trace,m,n]of [[before,old,'baseline-trace-source.txt'],[after,manifest,'candidate-trace-source.txt']]){
  assert.equal(trace.complete,true);assert.equal(trace.productionRuntimeSha256,m.artifacts['attiny13a.wasm']);
  assert.equal(trace.results.length,7);assert.equal(trace.policy.physicalFirmware,true);
  for(const [p,digest]of Object.entries(trace.sourceSha256NormalizedLF)){
    const contents=p==='web-player/scripts/trace-device-calls.mjs'?read(n):
      trace===after&&adaptations[p]?read(adaptations[p]):git(p).toString().replaceAll('\r\n','\n');
    assert.equal(sha(contents),digest,p);
  }
  for(const row of trace.results){
    assert.equal(row.productionEquality,true);assert.equal(row.timeUnits,'picoseconds');
    const s=row.adcActivity;
    assert.equal(BigInt(s.disabled)+BigInt(s['enabled-idle'])+BigInt(s.converting),count(row,'analog_adc_advance'));
    assert.ok(BigInt(s['clock-gated'])<=count(row,'analog_adc_advance'));
  }
}
for(const a of before.results){
  const b=after.results.find(x=>x.id===a.id);assert.ok(b);
  for(const key of ['rawPcmSha256','pinSha256','cycles','flashSha256'])assert.equal(a[key],b[key]);
  for(const key of ['elapse','analog_advance','analog_comparator_advance','next_event_scan'])assert.equal(count(a,key),count(b,key));
  if(a.adcState==='converting')assert.equal(count(a,'analog_adc_advance'),count(b,'analog_adc_advance'));
  else assert.ok(count(b,'analog_adc_advance')<count(a,'analog_adc_advance'));
}
const functions=json('function-analysis.json');
assert.deepEqual(functions.counts,{identical:202,'relocation-only':0,'body-changed':1,added:0,removed:0});
assert.deepEqual(functions.changed.map(f=>[f.symbol,f.before.bytes,f.after.bytes]),[['analog_advance',318,414]]);
for(const line of ['tests 1693','pass 1693','fail 0','skipped 0'])assert.ok(read('full-test.tap').includes('# '+line+'\n'));
for(const [,name]of read('test-source.txt').matchAll(/test\('([^']+)'/g))assert.ok(read('full-test.tap').includes('# Subtest: '+name+'\n'));
console.log(JSON.stringify({decision:'retained-with-synthetic-regression',runtimeSha256:sha(binary),tests:1693,validationCases:15,tracePairs:7,...totals}));
