import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
import {controlLabels,controlSchedule,controlRatios,statistics} from './controls-source.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex'),normalize=b=>b.toString().replaceAll('\r\n','\n');
const raw=p=>readFileSync(join(dir,p)),read=p=>p.endsWith('.gz')?gunzipSync(raw(p)):raw(p),json=p=>JSON.parse(read(p));
const evidence=json('evidence.json'),baseline=evidence.baseline,inputs=new Map();
const git=p=>{if(!inputs.has(p))inputs.set(p,execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:16*1024*1024}));return inputs.get(p);};
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.gz')||p.endsWith('.wasm')?raw(p):normalize(raw(p))),h,p);
const candidate=json('candidate-manifest.json'),old=JSON.parse(git('web-player/wasm/device-build.json'));
const currentBinary=raw('candidate.wasm'),oldBinary=git('web-player/wasm/attiny13a.wasm');
assert.equal(sha(currentBinary),candidate.artifacts['attiny13a.wasm']);assert.equal(currentBinary.length,candidate.bytes);
assert.equal(sha(oldBinary),old.artifacts['attiny13a.wasm']);assert.equal(oldBinary.length,old.bytes);
for(const key of ['exports','flags','compilerVersion','sources','memoryPages','maximumMemoryPages','stackBytes','imports'])assert.deepEqual(candidate[key],old[key],key);
const changed=Object.keys(candidate.inputs).filter(p=>candidate.inputs[p]!==old.inputs[p]);assert.deepEqual(changed,['web-player/native/peripherals/device.c']);
for(const [p,h]of Object.entries(candidate.inputs))assert.equal(sha(normalize(p===changed[0]?raw('candidate-device.c'):git(p))),h,p);
for(const [p,h]of Object.entries(old.inputs))assert.equal(sha(normalize(git(p))),h,p);
const instances=[oldBinary,currentBinary].map(b=>{const m=new WebAssembly.Module(b);assert.deepEqual(WebAssembly.Module.imports(m),[]);return new WebAssembly.Instance(m).exports;});
assert.deepEqual(Object.keys(instances[0]),Object.keys(instances[1]));
for(const e of instances)assert.equal(e.memory.buffer.byteLength,131072);
for(let n=0;n<20;n++)assert.equal(instances[0].avr_layout(n),instances[1].avr_layout(n),'native layout '+n);
for(let n=0;n<10;n++)assert.equal(instances[0].avr_device_phase_layout(n),instances[1].avr_device_phase_layout(n),'phase layout '+n);
const screen=json('screen.json.gz');assert.equal(screen.complete,true);assert.equal(screen.mode,'timing');assert.equal(screen.git.baseline,baseline);
assert.equal(screen.parameters.changeSet,'timer-deadline-budget');assert.equal(screen.parameters.trials,8);assert.equal(screen.parameters.warmups,4);
assert.deepEqual(screen.parameters.schedule,controlSchedule(8));
for(const [p,h]of Object.entries(screen.provenance.sourceSha256))assert.equal(sha(normalize(p==='web-player/scripts/benchmark-runtime-controls.mjs'?raw('benchmark-source.mjs'):git(p))),h,p);
assert.equal(normalize(raw('controls-source.mjs')),normalize(git('web-player/scripts/lib/runtime-control-design.mjs')));
for(const [label,m]of Object.entries(screen.provenance.runtimes)){
  const expected=label.startsWith('old')?old:candidate;assert.equal(m.sha256,expected.artifacts['attiny13a.wasm']);assert.equal(m.bytes,expected.bytes);assert.deepEqual(m.inputs,expected.inputs);
}
let timings=0,warmups=0,snapshots=0,comparisons=0;const ratios={};
for(const row of screen.results){
  assert.equal(row.runs.length,32);assert.equal(row.warmups.length,16);timings+=row.runs.length;warmups+=row.warmups.length;
  const reference=row.warmups[0];
  for(const [entries,field]of [[row.warmups,'pass'],[row.runs,'trial']])for(const r of entries){
    assert.equal(r.variant,screen.parameters.schedule[r[field]][r.position]);
    assert.equal(r.rawSha256,reference.rawSha256);assert.equal(r.architectureSha256,reference.architectureSha256);assert.equal(r.pinSha256,reference.pinSha256);
    assert.deepEqual(r.finalState,reference.finalState);assert.ok(r.ms>0);snapshots+=r.checkpoints;
    assert.equal(r.finalState.deviceFault,0);
  }
  if(row.id.includes('kernel-'))assert.equal(reference.finalState.clockDivisor,1);
  assert.deepEqual(row.summary,{...Object.fromEntries(controlLabels.map(label=>[label,statistics(row.runs.filter(r=>r.variant===label).map(r=>r.ms))])),ratios:controlRatios(row.runs,8)});
  assert.equal(row.validation.checkpointsCompared,(row.runs.length+row.warmups.length-1)*reference.checkpoints);
  for(const k of ['exactWarmupAndTimedState','exactPcmAndPins','sameRuntimeModuleInsidePairs','identicalCPUBytesAndABI','freshCPUmodulePerConstruction'])assert.equal(row.validation[k],true);
  comparisons+=row.validation.checkpointsCompared;ratios[row.id]=row.summary.ratios.crossVersion.median;
}
assert.equal(screen.results.length,6);assert.equal(timings,192);assert.equal(warmups,96);
assert.match(read('candidate-full-test.tap.gz').toString(),/# tests 1888\r?\n# suites 0\r?\n# pass 1888\r?\n# fail 0/);
for(const p of ['candidate-unit-test.tap.gz','restored-unit-test.tap.gz'])assert.match(read(p).toString(),/# tests 16\r?\n# suites 0\r?\n# pass 16\r?\n# fail 0/);
const restored=json('restored-state.json');assert.equal(restored.baseline,baseline);
for(const [p,h]of Object.entries(restored.sourceAndArtifacts)){
  assert.equal(sha(p.endsWith('.wasm')?git(p):normalize(git(p))),h,p+' archived restoration');
  if(process.argv.includes('--check-current'))assert.equal(sha(p.endsWith('.wasm')?readFileSync(join(root,p)):normalize(readFileSync(join(root,p)))),h,p+' current restoration');
}
if(process.argv.includes('--rebuild')){
  const parent=join(root,'build/replays');mkdirSync(parent,{recursive:true});const target=mkdtempSync(join(parent,'timer-budget-'));
  for(const p of [...Object.keys(candidate.inputs),'web-player/tests/analog-test-build.mjs','web-player/lib/attiny13a-registers.js','web-player/lib/attiny13a-registers.json']){
    const path=join(target,p);mkdirSync(dirname(path),{recursive:true});writeFileSync(path,p===changed[0]?raw('candidate-device.c'):git(p));
  }
  writeFileSync(join(target,'package.json'),'{"type":"module"}\n');
  const testPath=join(target,'web-player/tests/device-timer-deadline-budget.test.mjs');writeFileSync(testPath,raw('candidate-test-source.mjs'));
  const build=spawnSync(process.execPath,[join(target,'web-player/scripts/build-device-wasm.mjs')],{cwd:target,encoding:'utf8'});
  assert.equal(build.status,0,build.stderr||build.stdout);assert.ok(readFileSync(join(target,'web-player/wasm/attiny13a.wasm')).equals(currentBinary),'isolated candidate bytes');
  const tests=spawnSync(process.execPath,['--test',testPath],{cwd:target,encoding:'utf8'});assert.equal(tests.status,0,tests.stderr||tests.stdout);assert.match(tests.stdout,/# pass 16/);
  writeFileSync(join(target,'rebuild.log'),build.stdout+'\n'+tests.stdout);
  console.log('Isolated rebuild and 16 candidate tests: '+target);
}
console.log(JSON.stringify({timings,warmups,snapshots,comparisons,ratios,productionRestored:process.argv.includes('--check-current')}));
