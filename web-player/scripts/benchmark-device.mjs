import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {cpus,platform,arch,endianness,release,totalmem} from 'node:os';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a.js';
import {Renderer as AudioRenderer} from '../lib/renderer-js.js';
import {parseHex} from '../lib/hex.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{
  frames:{type:'string',default:'12000'},rate:{type:'string',default:'48000'},
  trials:{type:'string',default:'4'},firmware:{type:'string',multiple:true},
  out:{type:'string',default:'build/benchmarks/device-benchmark.json'},help:{type:'boolean'},
}});
if(values.help){
  console.log('node web-player/scripts/benchmark-device.mjs [--frames 12000] [--rate 48000] [--trials 4] [--firmware id,id|all] [--out build/benchmarks/device-benchmark.json]');
  process.exit(0);
}
function integer(value,name,low,high){
  const number=Number(value);
  if(!Number.isInteger(number)||number<low||number>high)throw Error(`${name} must be an integer ${low}..${high}`);
  return number;
}
const frames=integer(values.frames,'frames',1,1048576),rate=integer(values.rate,'rate',8000,192000);
const trials=integer(values.trials,'trials',1,64),blockFrames=1024,warmupFrames=Math.min(frames,4096);
const output=resolve(root,values.out),controls={cutoff:9000,volume:.65,filtered:true};
const json=path=>JSON.parse(readFileSync(resolve(root,path),'utf8'));
const catalogFiles=['web-player/firmware.json','web-player/hq4-firmware.json'];
const catalog=catalogFiles.flatMap(file=>json(file).entries.map(entry=>({...entry,catalogFile:file})));
const ids=values.firmware?.flatMap(value=>value.split(',').filter(Boolean))??['rhythmic','lumiere-stereo','hq4-chego-auto'];
if(ids.includes('all')&&ids.length!==1)throw Error('Use --firmware all by itself');
const selected=ids[0]==='all'?catalog:ids.map(id=>{
  const entry=catalog.find(entry=>entry.id===id);
  if(!entry)throw Error(`Unknown firmware ${id}; choose ${catalog.map(entry=>entry.id).join(', ')}`);
  return entry;
});
if(new Set(selected.map(entry=>entry.id)).size!==selected.length)throw Error('Duplicate firmware selection');
const variants=[
  {id:'idle-on_flags-on',fastIdle:true,optimizeFlags:true},
  {id:'idle-off_flags-on',fastIdle:false,optimizeFlags:true},
  {id:'idle-on_flags-off',fastIdle:true,optimizeFlags:false},
  {id:'idle-off_flags-off',fastIdle:false,optimizeFlags:false},
];
// Four-order Williams rotation: every variant occupies each position in 4 trials.
const orders=[[0,1,3,2],[1,2,0,3],[2,3,1,0],[3,0,2,1]];
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const bytes=array=>Buffer.from(array.buffer,array.byteOffset,array.byteLength);
const normalize=(_,value)=>typeof value==='bigint'?value.toString():
  typeof value==='number'&&!Number.isFinite(value)?String(value):value;
const serialized=value=>JSON.stringify(value,normalize);
const stateHash=value=>hash(serialized(value));
const normalizedSource=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const manifestPath='web-player/wasm/device-build.json',manifest=json(manifestPath);
const runtimePath='web-player/wasm/attiny13a.wasm',runtimeBytes=readFileSync(resolve(root,runtimePath));
assert.equal(hash(runtimeBytes),manifest.artifacts['attiny13a.wasm'],'Device runtime hash differs from its manifest');
for(const [path,expected] of Object.entries(manifest.inputs))
  assert.equal(hash(normalizedSource(path)),expected,`Device source is newer than the binary: ${path}`);
const runtime=new WebAssembly.Module(runtimeBytes);
assert.deepEqual(WebAssembly.Module.imports(runtime),[],'Peripheral WASM must have no host imports');
const metadata=new WebAssembly.Instance(runtime).exports;
const sourceFiles=[...new Set([
  ...Object.keys(manifest.inputs),
  'web-player/scripts/benchmark-device.mjs','web-player/lib/attiny13a.js',
  'web-player/lib/attiny13a-runtime.js','web-player/lib/avr-transpiled-runtime.js',
  'web-player/lib/avr-runtime.js',
  'web-player/lib/avr-transpiled.js','web-player/lib/avr-transpiler.js',
  'web-player/lib/avr-wasm.js','web-player/lib/renderer-js.js','web-player/lib/hex.js',
])].sort();
const sourceHashes=Object.fromEntries(sourceFiles.map(path=>[path,hash(normalizedSource(path))]));
const git=args=>{try{return execFileSync('git',args,{cwd:root,encoding:'utf8'}).trim();}catch{return null;}};
function statistics(samples){
  const sorted=[...samples].sort((a,b)=>a-b),n=sorted.length,mean=samples.reduce((a,b)=>a+b,0)/n;
  return {median:n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2,
    min:sorted[0],max:sorted[n-1],mean,
    standardDeviation:n>1?Math.sqrt(samples.reduce((sum,value)=>sum+(value-mean)**2,0)/(n-1)):0};
}
function snapshot(core){
  const {idleCycles,...state}=core.state();
  const diagnostics={};
  for(const name of ['irqDelay','irqStart','irqCount','frameCount','inIRQ','maxIRQ',
    'minSP','lost','workLost','writes','leftWrites','eempeUntil','clkprUntil','error'])diagnostics[name]=core[name];
  return {state,diagnostics,data:core.data.slice(),eeprom:core.eeprom.slice(),
    flash:core.rom.slice(),irqFrames:Array.from(core.irqFrames)};
}
function compare(actual,expected,context){
  assert.ok(bytes(actual.raw).equals(bytes(expected.raw)),`${context}: raw Float32 PCM differs byte for byte`);
  assert.ok(bytes(actual.filtered).equals(bytes(expected.filtered)),`${context}: filtered Float32 PCM differs byte for byte`);
  assert.equal(actual.snapshots.length,expected.snapshots.length,context+' checkpoints');
  for(let n=0;n<actual.snapshots.length;n++)
    assert.deepEqual(actual.snapshots[n],expected.snapshots[n],`${context}: registers/I/O/SRAM/Flash/EEPROM/cycles/IRQ checkpoint ${n}`);
}
function signalSummary(pcm,channels){
  return Array.from({length:channels},(_,channel)=>{
    let min=Infinity,max=-Infinity,squares=0,changes=0,previous;
    for(let n=channel;n<pcm.length;n+=channels){
      const value=pcm[n];assert.ok(Number.isFinite(value),'PCM must be finite');
      min=Math.min(min,value);max=Math.max(max,value);squares+=value*value;
      if(previous!==undefined&&value!==previous)changes++;
      previous=value;
    }
    return {min,max,rms:Math.sqrt(squares/(pcm.length/channels)),changes};
  });
}
function makeCore(binary,eeprom,entry,variant,cacheTranslation){
  return new ATtiny13A(binary,eeprom,{oscillatorHz:entry.cpuHz??9600000,
    fastIdle:variant.fastIdle,optimizeFlags:variant.optimizeFlags,cacheTranslation});
}
function construct(binary,eeprom,entry,variant,trial,position){
  let cold,warm,coldMs,warmMs;
  // Prime outside the construction timers; each instance still gets new memory.
  makeCore(binary,eeprom,entry,variant,true);
  const policyOrder=(trial+position)%2?['warm','cold']:['cold','warm'];
  for(const policy of policyOrder){
    const start=performance.now();
    const core=makeCore(binary,eeprom,entry,variant,policy==='warm');
    const elapsed=performance.now()-start;
    if(policy==='cold'){cold=core;coldMs=elapsed;}else{warm=core;warmMs=elapsed;}
  }
  assert.equal(cold.translationCacheHit,false,'Uncached construction must bypass the library cache');
  assert.equal(warm.translationCacheHit,true,'Warm construction must hit the library cache');
  assert.notEqual(cold._exports.memory,warm._exports.memory,'Cache must never share mutable runtime state');
  return {core:warm,record:{policyOrder,coldUncachedMs:coldMs,warmCacheHitMs:warmMs,
    coldCacheHit:false,warmCacheHit:true}};
}
function execute(core,entry,count){
  const channels=entry.audioChannels||1;
  // Use the actual public processRaw implementation without constructing a
  // second CPU. The adapter returns this existing device to the DSP constructor.
  class ExistingDevice{constructor(){return core;}}
  const dsp=new AudioRenderer(entry,rate,controls,ExistingDevice);
  const raw=new Float32Array(count*channels),filtered=new Float32Array(count*channels);
  const snapshots=[],checkpoints=[];
  let captureMs=0,dspMs=0;
  for(let offset=0;offset<count;offset+=blockFrames){
    const n=Math.min(blockFrames,count-offset);
    let start=performance.now();
    const block=core.capturePhysical(n,rate,channels);
    captureMs+=performance.now()-start;
    const architectural=snapshot(core);
    assert.equal(architectural.state.deviceFault,0,`${entry.id}: peripheral fault`);
    start=performance.now();
    const pcm=dsp.processRaw(block,n);
    dspMs+=performance.now()-start;
    // Benchmark bookkeeping, hashes and validation stay outside both timers.
    raw.set(block,offset*channels);filtered.set(pcm,offset*channels);
    snapshots.push(architectural);
    checkpoints.push({frames:offset+n,baseHalf:architectural.state.baseHalf,
      cycles:architectural.state.cycles,pc:architectural.state.pc,irqs:architectural.state.irqs,
      pendingIRQs:architectural.state.pendingIRQs,dataSha256:hash(architectural.data),
      architectureSha256:stateHash(architectural),rawBlockSha256:hash(bytes(block))});
  }
  const final=core.state();
  return {raw,filtered,snapshots,record:{capturePhysicalMs:captureMs,processRawMs:dspMs,
    capturePlusDspMs:captureMs+dspMs,rawPcmSha256:hash(bytes(raw)),filteredPcmSha256:hash(bytes(filtered)),
    rawSignal:signalSummary(raw,channels),filteredSignal:signalSummary(filtered,channels),
    checkpoints,finalState:final,finalDataSha256:hash(core.data),
    irqFrames:Array.from(core.irqFrames),idleCycles:core.idleCycles,
    translatedBytes:core.transpiledBytes.length,translatedSha256:hash(core.transpiledBytes),
    translationStatistics:core.transpilation.stats}};
}
const hostCpus=cpus(),benchmarkStart=performance.now();
const report={schema:'micromusic-attiny13a-device-benchmark-v1',
  createdAt:new Date().toISOString(),node:process.version,versions:process.versions,
  nodeExecutable:process.execPath,nodeFlags:process.execArgv,
  host:{platform:platform(),release:release(),arch:arch(),endianness:endianness(),
    cpu:hostCpus[0]?.model,logicalCpus:hostCpus.length,cpuReportedMHz:hostCpus.map(cpu=>cpu.speed),memoryBytes:totalmem()},
  git:{head:git(['rev-parse','HEAD']),status:git(['status','--short'])},
  parameters:{frames,sampleRate:rate,seconds:frames/rate,trials,blockFrames,warmupFrames,
    controls,firmwareOrder:selected.map(entry=>entry.id),variants,
    orderSchedule:orders.map(order=>order.map(index=>variants[index].id))},
  provenance:{sourceSha256NormalizedLF:sourceHashes,
    catalogs:Object.fromEntries(catalogFiles.map(path=>[path,hash(normalizedSource(path))])),
    runtime:{path:runtimePath,sha256:hash(runtimeBytes),bytes:runtimeBytes.length,
      memoryBytes:metadata.memory.buffer.byteLength,imports:[],manifestSha256:hash(normalizedSource(manifestPath)),
      compilerVersion:manifest.compilerVersion,buildFlags:manifest.flags},
    legacyRuntimeArtifactSha256:hash(readFileSync(resolve(root,'web-player/wasm/avr.wasm')))},
  method:{construction:'Cold means cacheTranslation:false: fresh runtime instance, initialization, lowering, WASM module compilation and instance binding. Warm is a verified library translation-cache hit into fresh device memory. Runtime module import/compilation is excluded. V8 may internally cache identical compiled bytes even when the library cache is bypassed; this is not a cold process launch.',
    capture:'Time only public capturePhysical calls on a fresh warm-constructed device, from reset through identical frame intervals. Includes translated CPU, C peripheral scheduling, physical pin integration, wrapper allocation/copy and initial audio configuration. These costs are coupled; CPU-only and peripheral-only wall times are unresolved without internal instrumentation.',
    dsp:'Time only the production JS Renderer.processRaw calls on exactly those captured blocks. Includes filter/gain state, output allocation and JS sample-summary updates, with no CPU/peripheral execution. DSP construction is outside the timers.',
    correctness:'Every trial compares all four configurations byte for byte for raw and filtered Float32 PCM, plus complete visible data/EEPROM/Flash and architectural/IRQ state at every block endpoint. Trial baselines are also compared across trials. The idleCycles performance counter is excluded from equality; the snapshots enumerate the selected architectural diagnostics. Hashing, signal summaries, snapshots and assertions are outside measured regions.',
    ordering:'One unmeasured warmup per firmware/variant, then fresh devices for every run. Four-order Williams rotation across variants; cold/warm constructor order alternates with trial and run position. No forced GC or CPU affinity; V8 tiering, GC and other host load remain in samples.',
    limits:'Node measurements are not browser guarantees. Samples start at reset and cover only the selected duration, not whole compositions. Exclusive CPU/peripheral timing, browser AudioWorklet overhead and host audio scheduling are not measured.'},
  results:[]};
for(const entry of selected){
  console.log(`Benchmark ${entry.id}: ${frames} frames, ${rate} Hz, ${trials} trials`);
  const binary=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  assert.equal(hash(binary),entry.flashSha256,entry.id+' catalog Flash hash');
  if(eeprom&&entry.eepromSha256)assert.equal(hash(eeprom),entry.eepromSha256,entry.id+' catalog EEPROM hash');
  for(const variant of variants)execute(makeCore(binary,eeprom,entry,variant,true),entry,warmupFrames);
  const row={id:entry.id,kind:entry.kind??'music',channels:entry.audioChannels||1,
    oscillatorHz:entry.cpuHz??9600000,flashBytes:binary.length,flashSha256:hash(binary),
    paddedFlashSha256:hash(Uint8Array.from({length:1024},(_,n)=>binary[n]??255)),
    eepromSha256:hash(eeprom??new Uint8Array(64).fill(255)),runs:[]};
  let reference;
  for(let trial=0;trial<trials;trial++){
    const completed=new Map(),order=orders[trial%orders.length];
    for(const [position,index] of order.entries()){
      const variant=variants[index],startedAtOffsetMs=performance.now()-benchmarkStart;
      const created=construct(binary,eeprom,entry,variant,trial,position);
      const measured=execute(created.core,entry,frames);
      completed.set(variant.id,measured);
      row.runs.push({trial,position,variant:variant.id,startedAtOffsetMs,construction:created.record,...measured.record});
    }
    const baseline=completed.get(variants[0].id);
    for(const variant of variants)compare(completed.get(variant.id),baseline,`${entry.id} trial ${trial} ${variant.id}`);
    if(reference)compare(baseline,reference,`${entry.id} trial ${trial} determinism`);
    else reference=baseline;
  }
  row.validation={rawPcmByteEquality:true,filteredPcmByteEquality:true,
    registersIoSramEepromFlashEqual:true,cyclesIrqStateEqual:true,crossTrialDeterminism:true,
    comparedCheckpoints:trials*variants.length*Math.ceil(frames/blockFrames)};
  row.summary=Object.fromEntries(variants.map(variant=>{
    const runs=row.runs.filter(run=>run.variant===variant.id);
    return [variant.id,{coldUncachedMs:statistics(runs.map(run=>run.construction.coldUncachedMs)),
      warmCacheHitMs:statistics(runs.map(run=>run.construction.warmCacheHitMs)),
      capturePhysicalMs:statistics(runs.map(run=>run.capturePhysicalMs)),
      processRawMs:statistics(runs.map(run=>run.processRawMs)),
      capturePlusDspMs:statistics(runs.map(run=>run.capturePlusDspMs))}];
  }));
  const metric=id=>row.summary[id].capturePhysicalMs.median,baseline=row.summary[variants[0].id];
  row.ratios={constructionCacheSpeedup:baseline.coldUncachedMs.median/baseline.warmCacheHitMs.median,
    idleSpeedupWithFlags:metric(variants[1].id)/metric(variants[0].id),
    flagOptimizationSpeedupWithIdle:metric(variants[2].id)/metric(variants[0].id),
    idleSpeedupWithoutFlags:metric(variants[3].id)/metric(variants[2].id),
    flagOptimizationSpeedupWithoutIdle:metric(variants[3].id)/metric(variants[1].id),
    captureRealtimeHeadroom:frames/rate*1000/baseline.capturePhysicalMs.median,
    capturePlusDspRealtimeHeadroom:frames/rate*1000/baseline.capturePlusDspMs.median};
  report.results.push(row);
  // Save after each complete firmware so a later failure cannot fabricate
  // validation for missing entries or lose already completed measurements.
  report.complete=report.results.length===selected.length;
  report.updatedAt=new Date().toISOString();report.elapsedMs=performance.now()-benchmarkStart;
  mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,normalize,2)+'\n');
}
console.table(report.results.map(row=>{
  const baseline=row.summary[variants[0].id];
  return {firmware:row.id,cold_ms:baseline.coldUncachedMs.median.toFixed(2),
    warm_ms:baseline.warmCacheHitMs.median.toFixed(2),capture_ms:baseline.capturePhysicalMs.median.toFixed(2),
    dsp_ms:baseline.processRawMs.median.toFixed(2),idle_gain:row.ratios.idleSpeedupWithFlags.toFixed(2)+'x',
    flags_gain:row.ratios.flagOptimizationSpeedupWithIdle.toFixed(2)+'x',
    realtime:row.ratios.capturePlusDspRealtimeHeadroom.toFixed(2)+'x'};
}));
console.log(`All byte/state checks passed. Report: ${relative(root,output).replaceAll('\\','/')}`);
