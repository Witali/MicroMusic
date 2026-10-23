// Compare the actual pre-cache shipped runtime with a separately built candidate.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {cpus,platform,arch,release,totalmem} from 'node:os';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {parseHex} from '../lib/hex.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{
  candidate:{type:'string',default:'build/deadline-cache-test/runtime'},
  'baseline-ref':{type:'string',default:'f4aec2f'},
  frames:{type:'string',default:'48000'},rate:{type:'string',default:'48000'},
  trials:{type:'string',default:'6'},clock:{type:'string',default:'physical'},
  firmware:{type:'string',multiple:true},
  out:{type:'string',default:'build/benchmarks/deadline-cache.json'},help:{type:'boolean'},
}});
if(values.help){
  console.log('node web-player/scripts/benchmark-deadline-cache.mjs [--candidate build/<runtime>] [--baseline-ref f4aec2f] [--frames 48000] [--rate 48000] [--trials 6] [--clock physical|legacy] [--firmware id,id] [--out build/benchmarks/deadline-cache.json]');
  process.exit(0);
}
function integer(value,name,min,max){const n=Number(value);
  if(!Number.isInteger(n)||n<min||n>max)throw Error(`${name} must be ${min}..${max}`);return n;}
const frames=integer(values.frames,'frames',1,1048576),rate=integer(values.rate,'rate',8000,192000);
const trials=integer(values.trials,'trials',2,64),blockFrames=1024,warmupFrames=Math.min(4096,frames);
if(!['physical','legacy'].includes(values.clock))throw Error('clock must be physical or legacy');
const physical=values.clock==='physical',output=resolve(root,values.out);
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const bytes=array=>Buffer.from(array.buffer,array.byteOffset,array.byteLength);
const normalize=(_,v)=>typeof v==='bigint'?v.toString():typeof v==='number'&&!Number.isFinite(v)?String(v):v;
const digest=value=>hash(JSON.stringify(value,normalize));
const source=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const gitText=args=>git(args).toString().trim();
const manifestPath='web-player/wasm/device-build.json',runtimePath='web-player/wasm/attiny13a.wasm';
const baselineBytes=git(['show',`${values['baseline-ref']}:${runtimePath}`]);
const baselineManifest=JSON.parse(git(['show',`${values['baseline-ref']}:${manifestPath}`]));
const candidateDir=resolve(root,values.candidate);
const candidateBytes=readFileSync(resolve(candidateDir,'attiny13a.wasm'));
const candidateManifest=JSON.parse(readFileSync(resolve(candidateDir,'device-build.json')));
for(const [id,binary,manifest] of [['baseline',baselineBytes,baselineManifest],['candidate',candidateBytes,candidateManifest]]){
  assert.equal(hash(binary),manifest.artifacts['attiny13a.wasm'],`${id} binary/manifest mismatch`);
  assert.equal(binary.length,manifest.bytes,`${id} size/manifest mismatch`);
}
// Verify the actual baseline source objects and all current candidate inputs.
for(const [path,expected] of Object.entries(baselineManifest.inputs))
  assert.equal(hash(git(['show',`${values['baseline-ref']}:${path}`]).toString().replaceAll('\r\n','\n')),expected,`baseline source ${path}`);
for(const [path,expected] of Object.entries(candidateManifest.inputs))
  assert.equal(hash(source(path)),expected,`candidate source is newer than its WASM: ${path}`);
assert.deepEqual(candidateManifest.flags,baselineManifest.flags,'Use identical native compiler flags');
assert.equal(candidateManifest.compilerVersion,baselineManifest.compilerVersion,'Use identical native compiler');
assert.deepEqual(candidateManifest.sources,baselineManifest.sources,'Use identical native source list');
assert.deepEqual(candidateManifest.exports,baselineManifest.exports,'Use identical export surface');
assert.deepEqual(Object.keys(candidateManifest.inputs),Object.keys(baselineManifest.inputs));
const changedInputs=Object.keys(candidateManifest.inputs).filter(path=>candidateManifest.inputs[path]!==baselineManifest.inputs[path]);
assert.deepEqual(changedInputs,['web-player/native/peripherals/device.c'],'Only the device cache may differ');
const variants=[
  {id:'baseline',binary:baselineBytes,manifest:baselineManifest},
  {id:'candidate',binary:candidateBytes,manifest:candidateManifest},
].map(v=>({...v,module:new WebAssembly.Module(v.binary)}));
for(const variant of variants){assert.deepEqual(WebAssembly.Module.imports(variant.module),[]);
  assert.equal(new WebAssembly.Instance(variant.module).exports.memory.buffer.byteLength,131072);}
const catalogFiles=['web-player/firmware.json','web-player/hq4-firmware.json'];
const catalog=catalogFiles.flatMap(path=>JSON.parse(source(path)).entries);
const ids=values.firmware?.flatMap(v=>v.split(',').filter(Boolean))??['rhythmic','lumiere-stereo','hq4-chego-auto'];
assert.equal(new Set(ids).size,ids.length,'Duplicate firmware');
const entries=ids.map(id=>{const entry=catalog.find(e=>e.id===id);if(!entry)throw Error(`Unknown firmware ${id}`);return entry;});
function statistics(samples){const sorted=[...samples].sort((a,b)=>a-b),n=sorted.length;
  const mean=samples.reduce((sum,v)=>sum+v,0)/n;
  return {median:n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2,min:sorted[0],max:sorted[n-1],mean,
    standardDeviation:Math.sqrt(samples.reduce((sum,v)=>sum+(v-mean)**2,0)/(n-1))};}
function snapshot(core){return {state:core.state(),diagnostics:Array.from(core._state),
  data:core.data.slice(),flash:core.rom.slice(),eeprom:core.eeprom.slice(),irqFrames:Array.from(core.irqFrames)};}
function compare(actual,expected,context){
  assert.ok(bytes(actual.raw).equals(bytes(expected.raw)),`${context}: raw PCM byte equality`);
  assert.deepEqual(actual.snapshots,expected.snapshots,`${context}: full state/CPU/IO/IRQ/Flash/EEPROM`);
  assert.deepEqual(actual.pins,expected.pins,`${context}: remaining pin trace`);
}
function options(entry){const hz=entry.cpuHz||9600000;
  return {oscillatorHz:hz,fastIdle:true,optimizeFlags:true,
    ...(physical?{osccalHz:Array.from({length:128},(_,cal)=>cal===0?hz:0),
      factoryOsccal96:0,nvmClockProfile:1,nvmCalibrationReferenceHz:hz}:{})};}
function construct(variant,entry,flash,eeprom){
  const core=new ATtiny13A(flash,eeprom,{...options(entry),runtimeModule:variant.module});
  // Same external waveform in each run; no callbacks while executing the CPU.
  if(physical){core.injectPinsPs({at:777777n,mask:4,levels:4});core.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
  else{core.injectPins({at:777n,mask:4,levels:4});core.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  return core;
}
function execute(core,entry,count){
  const channels=entry.audioChannels||1,raw=new Float32Array(count*channels),snapshots=[],checkpoints=[];
  let captureMs=0;
  for(let offset=0;offset<count;offset+=blockFrames){
    const n=Math.min(blockFrames,count-offset),start=performance.now();
    const block=core.capturePhysical(n,rate,channels);
    captureMs+=performance.now()-start;
    raw.set(block,offset*channels);const snap=snapshot(core);snapshots.push(snap);
    assert.equal(snap.state.deviceFault,0,entry.id+' peripheral fault');
    checkpoints.push({frames:offset+n,architectureSha256:digest(snap),rawBlockSha256:hash(bytes(block)),
      cycles:snap.state.cycles,timePs:snap.state.timePs,baseHalf:snap.state.baseHalf,pc:snap.state.pc,
      pendingIRQs:snap.state.pendingIRQs,irqFrames:snap.irqFrames});
  }
  const pins=physical?core.drainPinsPs():core.drainPins();
  return {raw,snapshots,pins,record:{capturePhysicalMs:captureMs,rawPcmSha256:hash(bytes(raw)),checkpoints,
    finalState:core.state(),finalArchitectureSha256:digest(snapshots.at(-1)),remainingPinsSha256:digest(pins),
    translatedSha256:hash(core.transpiledBytes),translatedBytes:core.transpiledBytes.length,
    translationCacheHit:core.translationCacheHit}};
}
const supportingFiles=['web-player/scripts/benchmark-deadline-cache.mjs','web-player/lib/attiny13a-runtime.js',
  'web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-runtime.js','web-player/lib/avr-transpiler.js',
  'web-player/lib/devices/profiles.js','web-player/lib/devices/attiny13a-profile.js','web-player/lib/hex.js'];
const hostCpus=cpus(),started=performance.now();
const report={schema:'micromusic-device-deadline-cache-benchmark-v1',createdAt:new Date().toISOString(),
  node:{version:process.version,versions:process.versions,executable:process.execPath,flags:process.execArgv},
  host:{platform:platform(),release:release(),arch:arch(),cpu:hostCpus[0]?.model,logicalCpus:hostCpus.length,
    reportedMHz:hostCpus.map(c=>c.speed),memoryBytes:totalmem()},
  git:{candidateHead:gitText(['rev-parse','HEAD']),status:gitText(['status','--short']),
    baselineCommit:gitText(['rev-parse',values['baseline-ref']])},
  provenance:{runtimes:Object.fromEntries(variants.map(v=>[v.id,{sha256:hash(v.binary),bytes:v.binary.length,
    sourceInputsSha256:digest(v.manifest.inputs),sourceInputs:v.manifest.inputs,compiler:v.manifest.compilerVersion,
    compilerFlags:v.manifest.flags,imports:[],memoryBytes:131072}])),changedInputs,
    jsSourceSha256NormalizedLF:Object.fromEntries(supportingFiles.map(path=>[path,hash(source(path))])),
    catalogsSha256NormalizedLF:Object.fromEntries(catalogFiles.map(path=>[path,hash(source(path))]))},
  parameters:{frames,rate,seconds:frames/rate,trials,blockFrames,warmupFrames,clock:values.clock,
    firmwareOrder:ids,fastIdle:true,optimizeFlags:true,orderSchedule:[['baseline','candidate'],['candidate','baseline']]},
  method:{timing:'Only public capturePhysical calls, summed over1024-frame blocks; fresh device from reset for every run. Construction, translation, snapshots, hashing, copying into retained PCM, assertions and pin trace draining are outside timers. Runtime WASM compilation is before warmup.',
    warmup:'One discarded4096-frame-or-shorter run per firmware/runtime before trials. Trial construction must hit each runtime identity\'s production translation cache into fresh mutable memory. V8 tiering is not forced.',
    order:'Serial runs only. Baseline/candidate order alternates each trial. The first baseline is also checked across every later run for deterministic bytes/state. No GC forcing or affinity.',
    parity:'Raw Float32 bytes and complete state/_state diagnostics, registers/IO/SRAM/Flash/EEPROM/IRQ frames compared at every block endpoint; remaining physical pin events compared after capture. All runs receive identical queued digital/analog inputs.',
    clocks:physical?'Explicit nominal CAL0 frequency per catalog; all other CAL values unspecified. Fixed-ps physical time, NVM fixed-ns profile, no power observer or guessed voltage/calibration table.':'Fixed oscillator-half compatibility contract with each catalog oscillatorHz; no physical calibration table.',
    limits:'CPU, native scheduler/modules, pin/audio integration and JS call/copy overhead are coupled. This is no exclusive CPU/peripheral measurement, browser guarantee or whole-composition benchmark. No DSP filter timing. Host scheduling, V8 tiering and GC remain possible variance.'},results:[]};
for(const entry of entries){
  console.log(`Serial ${entry.id}: ${frames} frames @${rate}, ${trials} trials, ${values.clock}`);
  const flash=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  assert.equal(hash(flash),entry.flashSha256);
  if(eeprom&&entry.eepromSha256)assert.equal(hash(eeprom),entry.eepromSha256);
  for(const v of variants)execute(construct(v,entry,flash,eeprom),entry,warmupFrames);
  const row={id:entry.id,channels:entry.audioChannels||1,options:options(entry),flashSha256:hash(flash),
    eepromSha256:hash(eeprom??new Uint8Array(64).fill(255)),runs:[]};
  let reference;
  for(let trial=0;trial<trials;trial++){
    const order=trial%2?[...variants].reverse():variants,completed={};
    for(const [position,v] of order.entries()){
      const core=construct(v,entry,flash,eeprom);assert.equal(core.translationCacheHit,true);
      const run=execute(core,entry,frames);completed[v.id]=run;
      row.runs.push({trial,position,variant:v.id,endedAtOffsetMs:performance.now()-started,...run.record});
    }
    compare(completed.candidate,completed.baseline,`${entry.id} trial${trial}`);
    if(reference)compare(completed.baseline,reference,`${entry.id} determinism trial${trial}`);
    else reference=completed.baseline;
  }
  row.summary=Object.fromEntries(variants.map(v=>[v.id,statistics(row.runs.filter(r=>r.variant===v.id).map(r=>r.capturePhysicalMs))]));
  const ratios=Array.from({length:trials},(_,trial)=>{
    const run=id=>row.runs.find(r=>r.trial===trial&&r.variant===id).capturePhysicalMs;
    return run('baseline')/run('candidate');});
  row.summary.pairedSpeedup=statistics(ratios);
  row.summary.medianRatio=row.summary.baseline.median/row.summary.candidate.median;
  row.validation={rawPcmByteEquality:true,fullArchitecturalStateEquality:true,remainingPinTraceEquality:true,
    crossTrialDeterminism:true,checkpointsCompared:2*trials*Math.ceil(frames/blockFrames)};
  report.results.push(row);report.complete=report.results.length===entries.length;
  report.elapsedMs=performance.now()-started;
  mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,normalize,2)+'\n');
}
console.table(report.results.map(r=>({firmware:r.id,baseline_ms:r.summary.baseline.median.toFixed(2),
  candidate_ms:r.summary.candidate.median.toFixed(2),ratio:r.summary.medianRatio.toFixed(3)+'x',
  paired_median:r.summary.pairedSpeedup.median.toFixed(3)+'x'})));
console.log(`All raw PCM/state/trace checks passed: ${relative(root,output).replaceAll('\\','/')}`);
