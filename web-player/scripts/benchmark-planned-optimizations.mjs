// Separate native activity savings from resumable compiler savings, uninstrumented.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {cpus,platform,arch,release} from 'node:os';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{
  'baseline-ref':{type:'string',default:'0a61ae7'},trials:{type:'string',default:'6'},
  frames:{type:'string',default:'12000'},instructions:{type:'string',default:'1000000'},
  out:{type:'string',default:'build/benchmarks/planned-optimizations.json'},help:{type:'boolean'},
}});
if(values.help){
  console.log('node web-player/scripts/benchmark-planned-optimizations.mjs [--baseline-ref 0a61ae7] [--trials 6] [--frames 12000] [--instructions 1000000] [--out build/benchmarks/planned-optimizations.json]');
  process.exit(0);
}
function integer(value,min,max){const n=Number(value);assert.ok(Number.isInteger(n)&&n>=min&&n<=max);return n;}
const trials=integer(values.trials,2,32),frames=integer(values.frames,1024,48000);
const instructions=integer(values.instructions,1000,10000000),rate=48000,blockFrames=1024;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const bytes=array=>Buffer.from(array.buffer,array.byteOffset,array.byteLength);
const replacer=(_,v)=>typeof v==='bigint'?v.toString():v;
const digest=value=>hash(JSON.stringify(value,replacer));
const source=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const gitText=args=>git(args).toString().trim();
const wasmPath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const baselineRef=values['baseline-ref'];
const compilerPath='web-player/lib/avr-transpiler.js';
const baselineCompiler=git(['show',`${baselineRef}:${compilerPath}`]).toString().replaceAll('\r\n','\n');
const baselineCompilerFile=resolve(root,'build/benchmarks/compiler-'+hash(baselineCompiler).slice(0,16)+'.mjs');
mkdirSync(dirname(baselineCompilerFile),{recursive:true});
// Only relocate the two static imports. Both imported implementations must
// still equal the original Git dependencies; no baseline lowering is patched.
let relocated=baselineCompiler;
for(const dependency of ['devices/profiles.js','avr-wasm-phases.js']){
  const path='web-player/lib/'+dependency;
  assert.equal(source(path),git(['show',`${baselineRef}:${path}`]).toString().replaceAll('\r\n','\n'),path+' baseline dependency');
  relocated=relocated.replace("'./"+dependency+"'",JSON.stringify(pathToFileURL(resolve(root,path)).href));
}
writeFileSync(baselineCompilerFile,relocated);
const baselineTranspile=(await import(pathToFileURL(baselineCompilerFile).href)).transpileAVR;
const currentBinary=readFileSync(resolve(root,wasmPath)),currentManifest=JSON.parse(source(manifestPath));
const variants=[
  {id:'baseline',binary:git(['show',`${baselineRef}:${wasmPath}`]),
    manifest:JSON.parse(git(['show',`${baselineRef}:${manifestPath}`])),compiler:baselineTranspile},
  {id:'native-only',binary:currentBinary,manifest:currentManifest,compiler:baselineTranspile},
  {id:'candidate',binary:currentBinary,manifest:currentManifest,compiler:transpileAVR},
];
for(const v of variants){
  assert.equal(hash(v.binary),v.manifest.artifacts['attiny13a.wasm']);
  assert.equal(v.binary.length,v.manifest.bytes);
  for(const [path,expected] of Object.entries(v.manifest.inputs)){
    const text=v.id==='baseline'?git(['show',`${baselineRef}:${path}`]).toString().replaceAll('\r\n','\n'):source(path);
    assert.equal(hash(text),expected,`${v.id}: ${path}`);
  }
  v.module=new WebAssembly.Module(v.binary);assert.deepEqual(WebAssembly.Module.imports(v.module),[]);
  assert.equal(new WebAssembly.Instance(v.module).exports.memory.buffer.byteLength,131072);
}
const [baseline,nativeOnly,candidate]=variants;
for(const key of ['compilerVersion','flags','sources','exports'])
  assert.deepEqual(candidate.manifest[key],baseline.manifest[key],key);
assert.deepEqual(Object.keys(candidate.manifest.inputs),Object.keys(baseline.manifest.inputs));
const changedInputs=Object.keys(candidate.manifest.inputs)
  .filter(path=>candidate.manifest.inputs[path]!==baseline.manifest.inputs[path]);
assert.deepEqual(changedInputs,['web-player/native/avr-device.inc','web-player/native/peripherals/device.c',
  'web-player/native/peripherals/device.h','web-player/native/devices/attiny13a/clki_board.inc']);
function stats(samples){const sorted=[...samples].sort((a,b)=>a-b),n=sorted.length,mean=samples.reduce((a,b)=>a+b,0)/n;
  return {median:n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2,min:sorted[0],max:sorted[n-1],mean,
    standardDeviation:Math.sqrt(samples.reduce((sum,v)=>sum+(v-mean)**2,0)/(n-1))};}
function table(hz){const result=Array(128).fill(0);result[0]=hz;return result;}
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),
  avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const catalog=['web-player/firmware.json','web-player/hq4-firmware.json'].flatMap(path=>JSON.parse(source(path)).entries);
const cases=[];
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-auto'])for(const physical of [false,true]){
  const entry=catalog.find(e=>e.id===id);assert.ok(entry,id);const hz=entry.cpuHz||9600000;
  const binary=parseHex(entry.flashHex);assert.equal(hash(binary),entry.flashSha256);
  cases.push({id:id+(physical?'-physical':'-compatible'),binary,
    eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):null,frames,channels:entry.audioChannels||1,
    physical,options:{oscillatorHz:hz,fastIdle:true,optimizeFlags:true,
      ...physical?{resumable:true,osccalHz:table(hz),nvmClockProfile:1,nvmCalibrationReferenceHz:hz}:{}}});
}
for(const physical of [false,true])cases.push({id:'kernel-'+(physical?'physical':'compatible')+'-direct',
  binary:kernel,instructions,physical,options:{oscillatorHz:9600000,fastIdle:false,fuseLow:0x72,
    ...physical?{resumable:true,osccalHz:table(9600000)}:{}}});
// A longer arithmetic region exposes block amortization separately from the
// three-instruction loop above; neither is a claim about normal firmware speed.
const registerKernel=flash({instructions:[...Array.from({length:30},(_,n)=>avr.inc(16+n%8)),avr.rjmp(30,0)]});
for(const physical of [false,true])cases.push({id:'kernel-register-span-'+(physical?'physical':'compatible')+'-direct',
  binary:registerKernel,instructions,physical,registerSpan:true,
  options:{oscillatorHz:9600000,fastIdle:false,fuseLow:0x72,
    ...physical?{resumable:true,osccalHz:table(9600000)}:{}}});
for(const external of [false,true])for(const divisor of external?[1,256]:[1])
  cases.push({id:'kernel-'+(external?'clki':'internal')+'-20m-div'+divisor,binary:kernel,
    frames:1200,channels:1,physical:true,external,divisor,
    options:{oscillatorHz:20000000,resumable:true,fastIdle:false,fuseLow:external?0x70:0x72,
      ...external?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz:table(20000000)}}});
function construct(entry,variant){
  const c=new ATtiny13A(entry.binary,entry.eeprom,{...entry.options,runtimeModule:variant.module,
    precompiled:entry.translations.get(variant.id)});
  if(entry.divisor){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(entry.divisor));}
  if(entry.external){const end=BigInt(entry.frames)*1000000000000n/BigInt(rate);
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,
      transitionCount:end/25000n,knownUntilPs:end}),true);}
  else if(!entry.instructions){
    // Keep both variants' queued digital and analog input work identical.
    if(entry.physical){c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
    else{c.injectPins({at:777n,mask:4,levels:4});c.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  }
  return c;
}
function snapshot(c){return {state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  flash:c.rom.slice(),eeprom:c.eeprom.slice(),irqFrames:Array.from(c.irqFrames)};}
const stableSnapshot=(snap,index)=>({...snap,diagnostics:snap.diagnostics.map((value,n)=>n===index?null:value)});
function execute(c,entry,count){
  const checkpoints=[],raw=[],snapshots=[],eventHintIndex=c._fieldIndex.overflowAt;let ms=0;
  if(entry.instructions){const start=performance.now(),retired=c.run(count);ms=performance.now()-start;
    assert.equal(retired,count);
    if(entry.registerSpan){
      const loops=Math.floor(count/31),tail=Math.min(30,count%31);
      assert.equal(c.cyc,count+loops);
      for(let r=0;r<8;r++)assert.equal(c.r[16+r],(loops*(r<6?4:3)+Math.floor((tail+7-r)/8))&255);
    }else{
      assert.equal(c.cyc,count+Math.floor((count-2)/4));
      assert.equal(c.r[18],Math.floor((count+1)/4)&255);assert.equal(c.r[20],Math.floor((count-1)/4)&255);
    }
    snapshots.push(snapshot(c));
  }else for(let offset=0;offset<count;offset+=blockFrames){
    const n=Math.min(blockFrames,count-offset),start=performance.now(),pcm=c.capturePhysical(n,rate,entry.channels);
    ms+=performance.now()-start;raw.push(bytes(pcm));snapshots.push(snapshot(c));
    if(entry.divisor)assert.ok(pcm.every(v=>v===-1));
    checkpoints.push({frames:offset+n,architectureSha256:digest(snapshots.at(-1)),
      chipAndStableDiagnosticsSha256:digest(stableSnapshot(snapshots.at(-1),eventHintIndex)),
      eventHint:String(snapshots.at(-1).diagnostics[eventHintIndex]),rawSha256:hash(bytes(pcm))});
  }
  for(const snap of snapshots)assert.equal(snap.state.deviceFault,0,entry.id);
  const pins=entry.physical?c.drainPinsPs():c.drainPins();
  return {raw:Buffer.concat(raw),snapshots,pins,eventHintIndex,record:{ms,checkpoints,finalState:c.state(),
    finalEventHint:String(c.overflowAt),chipAndStableDiagnosticsSha256:digest(stableSnapshot(snapshots.at(-1),eventHintIndex)),
    rawSha256:hash(Buffer.concat(raw)),architectureSha256:digest(snapshots.at(-1)),remainingPinsSha256:digest(pins),
    translatedBytes:c.transpiledBytes.length,translatedSha256:hash(c.transpiledBytes),translationCacheHit:c.translationCacheHit}};
}
function compare(actual,expected,label,allowConservativeEventHint=false){
  assert.ok(actual.raw.equals(expected.raw),label+' raw PCM');
  assert.equal(actual.eventHintIndex,expected.eventHintIndex);
  let policyDifferences=0;
  if(allowConservativeEventHint){
    assert.equal(actual.snapshots.length,expected.snapshots.length);
    for(let n=0;n<actual.snapshots.length;n++){
      const a=actual.snapshots[n],b=expected.snapshots[n],index=actual.eventHintIndex;
      if(a.diagnostics[index]!==b.diagnostics[index]){
        assert.equal(a.diagnostics[index],b.diagnostics[index]-1,label+' exact ceil-to-floor scheduling hint change');
        policyDifferences++;
      }
      assert.deepEqual(stableSnapshot(a,index),stableSnapshot(b,index),label+' chip state and all other diagnostics');
    }
  }else assert.deepEqual(actual.snapshots,expected.snapshots,label+' full state/registers/IO/RAM/Flash/EEPROM/IRQ frames');
  assert.deepEqual(actual.pins,expected.pins,label+' remaining pins');
  return policyDifferences;
}
const out=resolve(root,values.out),started=performance.now();
const report={schema:'micromusic-planned-optimizations-benchmark-v2',createdAt:new Date().toISOString(),
  git:{head:gitText(['rev-parse','HEAD']),status:gitText(['status','--short']),baselineCommit:gitText(['rev-parse',baselineRef])},
  host:{node:process.version,v8:process.versions.v8,flags:process.execArgv,platform:platform(),release:release(),
    arch:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length},
  provenance:{changedInputs,baselineCompilerSha256:hash(baselineCompiler),candidateCompilerSha256:hash(source(compilerPath)),
    baselineCompilerRelocation:'Only two static import specifiers use absolute file URLs; both dependency sources equal the original Git versions.',
    runtimes:Object.fromEntries(variants.map(v=>[v.id,{sha256:hash(v.binary),bytes:v.binary.length,
    sourceInputs:v.manifest.inputs,compilerVersion:v.manifest.compilerVersion,flags:v.manifest.flags,imports:[],memoryPages:2}])),
    supportingSources:Object.fromEntries(['web-player/scripts/benchmark-planned-optimizations.mjs',compilerPath,
      'web-player/lib/attiny13a-runtime.js','web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-phases.js',
      'web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-runtime.js',
      'web-player/tests/fixtures/attiny13a-system-firmware.mjs'].map(path=>[path,hash(source(path))]))},
  parameters:{frames,instructions,trials,rate,blockFrames,clockFrames:1200},
  method:{timing:'Serial uninstrumented capturePhysical (1024-frame blocks) or run(N) calls only. Fresh reset instance for every run. Explicit WASM module compilation, construction, input submission, retained-output concatenation, snapshots, assertions and hashing are outside timers. Public API batch copying and any engine tiering during those calls remain included.',
    order:'One discarded run per case/variant, then rotate the three variants and reverse on odd trials. Warmup is min(4096,frames) or min(100000,instructions). No forced GC, affinity or V8 flags.',
    attribution:'baseline=original native+original compiler; native-only=current native+original compiler; candidate=current native+current compiler. All modules are generated and compiled before warmup, then bound as precompiled modules to fresh native memory outside execution timers.',
    coldTranslation:'Generation and WASM compilation times are single startup observations per case/variant, outside execution timers. They are retained as diagnostics, not stable cold-start performance estimates.',
    parity:'All chip state, registers/IO/SRAM/Flash/EEPROM/IRQ frames, raw Float32 PCM and remaining pins match at each checkpoint. Only the private overflowAt scheduling hint may change against the old runtime, validated as exactly old ceil minus new floor (0 or1); each raw hint and its difference count are retained. Native-only versus candidate and cross-trial baseline checks require exact complete diagnostics too. Kernel counts/registers/cycles and constant-low PCM are additional checks.',
    scope:'Firmware: 250ms by default, compatible clock and fixed-ps resumable CPU. Kernels: three-ALU and thirty-ALU loops for direct throughput; short-loop internal20MHz and finite 20MHz CLKI /1,/256 at25ms; every source edge still serviced.',
    limits:'Node host timing with CPU, peripherals, native pin/audio integration and JS batch copying coupled. No DSP filtering or browser latency guarantee. Scheduling, tiering and GC may affect samples.'},results:[]};
const legacyBinary=readFileSync(resolve(root,'web-player/wasm/avr.wasm'));
assert.equal(hash(legacyBinary),hash(git(['show',`${baselineRef}:web-player/wasm/avr.wasm`])));
const ordinaryAbis=[['legacy',new WebAssembly.Module(legacyBinary)],['full',candidate.module]]
  .map(([name,module])=>[name,runtimeABI(new WebAssembly.Instance(module).exports)]);
report.defaultTranslationValidation=catalog.map(entry=>{
  const image=parseHex(entry.flashHex),targets={};
  for(const [name,abi] of ordinaryAbis){
    const previous=baselineTranspile(image,abi),current=transpileAVR(image,abi);
    assert.deepEqual(current.bytes,previous.bytes,entry.id+' ordinary '+name+' compiler parity');
    targets[name]={sha256:hash(current.bytes),bytes:current.bytes.length};
  }
  return {id:entry.id,flashSha256:hash(image),targets};
});
for(const entry of cases){
  console.log('Three-way '+entry.id);
  entry.translations=new Map();
  for(const v of variants){
    const abi=runtimeABI(new WebAssembly.Instance(v.module).exports,{resumable:!!entry.options.resumable});
    const generationStart=performance.now(),generated=v.compiler(entry.binary,abi,entry.options);
    generated.generationMs=performance.now()-generationStart;
    const compileStart=performance.now();generated.module=new WebAssembly.Module(generated.bytes);
    generated.compileMs=performance.now()-compileStart;
    entry.translations.set(v.id,generated);
  }
  if(!entry.options.resumable)assert.deepEqual(entry.translations.get('candidate').bytes,
    entry.translations.get('native-only').bytes,'ordinary emitted code remains byte-identical');
  const count=entry.instructions??entry.frames,warmup=Math.min(count,entry.instructions?100000:4096);
  for(const v of variants)execute(construct(entry,v),entry,warmup);
  const row={id:entry.id,frames:entry.frames,instructions:entry.instructions,channels:entry.channels,
    options:entry.options,flashSha256:hash(entry.binary),translations:Object.fromEntries(variants.map(v=>{
      const t=entry.translations.get(v.id);return[v.id,{sha256:hash(t.bytes),bytes:t.bytes.length,
        generationMs:t.generationMs,wasmCompileMs:t.compileMs,stats:t.manifest.stats}];})),runs:[],eventHintPolicyComparisons:[]};let reference;
  for(let trial=0;trial<trials;trial++){
    const completed={},order=[...variants.slice(trial%3),...variants.slice(0,trial%3)];
    if(trial%2)order.reverse();
    for(const [position,v] of order.entries()){
      const c=construct(entry,v);assert.equal(c.translationCacheHit,false,'explicit precompiled binding');
      const result=execute(c,entry,count);completed[v.id]=result;
      row.runs.push({trial,position,variant:v.id,...result.record});
    }
    const changedCandidate=compare(completed.candidate,completed.baseline,`${entry.id}/${trial}`,true);
    const changedNative=compare(completed['native-only'],completed.baseline,`${entry.id}/${trial}/native-only`,true);
    compare(completed.candidate,completed['native-only'],`${entry.id}/${trial}/compiler-only-exact`);
    row.eventHintPolicyComparisons.push({trial,candidate:changedCandidate,nativeOnly:changedNative});
    if(reference)compare(completed.baseline,reference,entry.id+' baseline determinism');else reference=completed.baseline;
  }
  row.summary=Object.fromEntries(variants.map(v=>[v.id,stats(row.runs.filter(r=>r.variant===v.id).map(r=>r.ms))]));
  row.summary.pairedSpeedup=stats(Array.from({length:trials},(_,trial)=>{
    const time=id=>row.runs.find(r=>r.variant===id&&r.trial===trial).ms;return time('baseline')/time('candidate');}));
  for(const [name,before,after] of [['nativeSpeedup','baseline','native-only'],['compilerSpeedup','native-only','candidate']])
    row.summary[name]=stats(Array.from({length:trials},(_,trial)=>{
      const time=id=>row.runs.find(r=>r.variant===id&&r.trial===trial).ms;return time(before)/time(after);}));
  row.summary.medianRatio=row.summary.baseline.median/row.summary.candidate.median;
  row.validation={rawPcmByteEquality:true,chipStateAndStableDiagnosticsEquality:true,remainingPinTraceEquality:true,
    nativeOnlyCandidateFullStateEquality:true,conservativeEventHintPolicy:true,
    crossTrialDeterminism:true,checkpointsCompared:3*trials*Math.max(1,Math.ceil((entry.frames??0)/blockFrames))};
  report.results.push(row);report.timingsComplete=report.results.length===cases.length;report.complete=false;
  report.elapsedMs=performance.now()-started;
  mkdirSync(dirname(out),{recursive:true});writeFileSync(out,JSON.stringify(report,replacer,2)+'\n');
}
// Keep every CLK/PWM pin event in a separate untimed comparison, while ADC3
// samples the actual PB3 clock waveform. Audio capture consumes its pin ring.
const traceImage=flash({instructions:[avr.rjmp(0,0)]});
const traceOptions={resumable:true,fastIdle:false,fuseLow:0x70,
  clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
const traceCores=variants.map(v=>{
  const abi=runtimeABI(new WebAssembly.Instance(v.module).exports,{resumable:true});
  const generated=v.compiler(traceImage,abi,traceOptions);
  generated.module=new WebAssembly.Module(generated.bytes);
  return new ATtiny13A(traceImage,null,{...traceOptions,runtimeModule:v.module,precompiled:generated});
});
for(const c of traceCores){
  for(const [io,value] of [[IO.DDRB,3],[IO.OCR0A,3],[IO.OCR0B,1],[IO.TCCR0A,0xa3],
    [IO.TCCR0B,1],[IO.ADMUX,3],[IO.ADCSRA,0xe0]])c.writeIO(io,value);
  c.setAnalogPs({at:111111n,pin:2,microvolts:1234567});
  assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:35000n,
    transitionCount:2000n,knownUntilPs:60000000n}),true);
}
const traceEvents=traceCores.map(c=>c.drainPinsPs()),traceCheckpoints=[];
for(let end=12000000n;end<=60000000n;end+=12000000n){
  traceCores.forEach((c,i)=>{c.runUntilPs(end);traceEvents[i].push(...c.drainPinsPs());});
  for(let i=1;i<traceCores.length;i++){
    assert.deepEqual(snapshot(traceCores[i]),snapshot(traceCores[0]),'untimed ADC3/PWM/CLK full state');
    assert.deepEqual(traceEvents[i],traceEvents[0],'every CLK/PWM pin event');
    assert.equal(traceCores[i].state().deviceFault,0);
  }
  traceCheckpoints.push({timePs:end.toString(),architectureSha256:digest(snapshot(traceCores[1]))});
}
assert.equal(traceEvents[0].filter(e=>e.timePs>0n).length>=2000,true);
for(const mask of [1,2])assert.ok(traceEvents[0].some(e=>(e.levels&mask)!==0),'PWM output went high');
assert.equal(traceCores[0].data[32+IO.ADCSRA]&0x10,0x10,'ADC3 conversion completed');
report.pinTraceValidation={everyPinEventEqual:true,adcChannel:3,sourceTransitions:2000,
  pinEvents:traceEvents[0].length,traceSha256:digest(traceEvents[0]),checkpoints:traceCheckpoints};
report.complete=true;report.elapsedMs=performance.now()-started;
writeFileSync(out,JSON.stringify(report,replacer,2)+'\n');
console.table(report.results.map(r=>({case:r.id,before_ms:r.summary.baseline.median.toFixed(2),
  after_ms:r.summary.candidate.median.toFixed(2),native:r.summary.nativeSpeedup.median.toFixed(3)+'x',
  compiler:r.summary.compilerSpeedup.median.toFixed(3)+'x',combined:r.summary.pairedSpeedup.median.toFixed(3)+'x'})));
console.log('All paired PCM/state checks passed: '+relative(root,out));
