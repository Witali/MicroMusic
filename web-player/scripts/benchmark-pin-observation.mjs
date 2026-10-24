// Native PCM isolation and optional external-history attribution. No timed hooks.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {cpus,platform,arch,release} from 'node:os';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'baseline-ref':{type:'string',default:'d41ba7a'},
  'eager-dir':{type:'string'},
  trials:{type:'string',default:'8'},frames:{type:'string',default:'12000'},
  instructions:{type:'string',default:'1000000'},
  out:{type:'string',default:'build/benchmarks/pin-observation.json'}}});
const integer=(value,min,max)=>{const n=Number(value);assert.ok(Number.isInteger(n)&&n>=min&&n<=max);return n;};
const trials=integer(values.trials,2,32),frames=integer(values.frames,1024,48000),
  instructions=integer(values.instructions,1000,10000000),rate=48000,blockFrames=1024;
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const replacer=(_key,value)=>typeof value==='bigint'?value.toString():value;
const digest=value=>sha(JSON.stringify(value,replacer));
const source=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const gitText=args=>git(args).toString().trim();
const baselineRef=values['baseline-ref'],nativePath='web-player/wasm/attiny13a.wasm',
  manifestPath='web-player/wasm/device-build.json';
for(const path of ['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-phases.js',
  'web-player/lib/devices/profiles.js','web-player/lib/devices/attiny13a-profile.js'])
  assert.equal(source(path),git(['show',`${baselineRef}:${path}`]).toString().replaceAll('\r\n','\n'),path+' unchanged compiler');
const previous={binary:git(['show',`${baselineRef}:${nativePath}`]),
  manifest:JSON.parse(git(['show',`${baselineRef}:${manifestPath}`]))};
const current={binary:readFileSync(resolve(root,nativePath)),manifest:JSON.parse(source(manifestPath))};
for(const [name,v] of Object.entries({baseline:previous,candidate:current})){
  assert.equal(sha(v.binary),v.manifest.artifacts['attiny13a.wasm']);assert.equal(v.binary.length,v.manifest.bytes);
  for(const [path,expected] of Object.entries(v.manifest.inputs)){
    const text=name==='baseline'?git(['show',`${baselineRef}:${path}`]).toString().replaceAll('\r\n','\n'):source(path);
    assert.equal(sha(text),expected,name+'/'+path);
  }
  v.module=new WebAssembly.Module(v.binary);assert.deepEqual(WebAssembly.Module.imports(v.module),[]);
  assert.equal(new WebAssembly.Instance(v.module).exports.memory.buffer.byteLength,131072);
}
for(const key of ['compilerVersion','sources'])assert.deepEqual(current.manifest[key],previous.manifest[key],key);
const added=['avr_device_pin_trace_config','avr_device_pin_trace_configuration'];
assert.deepEqual(current.manifest.exports.filter(name=>!previous.manifest.exports.includes(name)),added);
assert.ok(previous.manifest.exports.every(name=>current.manifest.exports.includes(name)));
const withoutExports=flags=>flags.filter(flag=>!flag.startsWith('-Wl,--export='));
assert.deepEqual(withoutExports(current.manifest.flags),withoutExports(previous.manifest.flags));
assert.deepEqual(Object.keys(current.manifest.inputs),Object.keys(previous.manifest.inputs));
const changedInputs=Object.keys(current.manifest.inputs).filter(path=>current.manifest.inputs[path]!==previous.manifest.inputs[path]);
assert.deepEqual(changedInputs,['web-player/native/avr-device.inc','web-player/native/peripherals/device.c',
  'web-player/native/peripherals/device.h','web-player/native/devices/attiny13a/clki_board.inc']);
const variants=[{id:'baseline',...previous}];
if(values['eager-dir']){
  const folder=resolve(root,values['eager-dir']),manifest=JSON.parse(readFileSync(resolve(folder,'device-build.json'))),
    binary=readFileSync(resolve(folder,'attiny13a.wasm')),
    retained=JSON.parse(source('web-player/reports/pin-observation-20261024/initial-native-manifest.json'));
  assert.deepEqual(manifest,retained,'exact retained eager checkpoint');
  assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.equal(binary.length,manifest.bytes);
  for(const [path,expected] of Object.entries(manifest.inputs))
    assert.equal(sha(readFileSync(resolve(folder,path),'utf8').replaceAll('\r\n','\n')),expected,'eager/'+path);
  for(const key of ['compilerVersion','sources','flags','exports'])assert.deepEqual(manifest[key],current.manifest[key],key);
  const module=new WebAssembly.Module(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
  assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
  variants.push({id:'eager-full',binary,manifest,module});
}
variants.push({id:'candidate-full',...current},{id:'candidate-audio',...current,audioOnly:true});
const stats=values=>{const a=[...values].sort((x,y)=>x-y),mean=a.reduce((x,y)=>x+y,0)/a.length;
  return {median:a.length%2?a[a.length>>1]:(a[a.length/2-1]+a[a.length/2])/2,min:a[0],max:a.at(-1),mean,
    standardDeviation:Math.sqrt(a.reduce((n,v)=>n+(v-mean)**2,0)/(a.length-1))};};
const table=hz=>{const a=Array(128).fill(0);a[0]=hz;return a;};
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),
  avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const catalog=['web-player/firmware.json','web-player/hq4-firmware.json'].flatMap(path=>JSON.parse(source(path)).entries);
const cases=[];
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-auto'])for(const physical of [false,true]){
  const entry=catalog.find(e=>e.id===id);assert.ok(entry,id);const hz=entry.cpuHz||9600000;
  const binary=parseHex(entry.flashHex);assert.equal(sha(binary),entry.flashSha256);
  cases.push({id:id+(physical?'-physical':'-compatible'),binary,
    eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):null,frames,channels:entry.audioChannels||1,physical,
    options:{oscillatorHz:hz,fastIdle:true,optimizeFlags:true,
      ...physical?{resumable:true,osccalHz:table(hz),nvmClockProfile:1,nvmCalibrationReferenceHz:hz}:{}}});
}
for(const physical of [false,true])cases.push({id:'kernel-'+(physical?'physical':'compatible')+'-direct',
  binary:kernel,instructions,physical,options:{oscillatorHz:9600000,fastIdle:false,fuseLow:0x72,
    ...physical?{resumable:true,osccalHz:table(9600000)}:{}}});
for(const external of [false,true])for(const divisor of external?[1,256]:[1])
  cases.push({id:'kernel-'+(external?'clki':'internal')+'-20m-div'+divisor,binary:kernel,
    frames:1200,channels:1,physical:true,external,divisor,
    options:{oscillatorHz:20000000,resumable:true,fastIdle:false,fuseLow:external?0x70:0x72,
      ...external?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz:table(20000000)}}});
for(const id of ['kernel-internal-20m-div1','kernel-clki-20m-div1'])
  cases.push({...cases.find(v=>v.id===id),id:id+'-adc-active',adcEnabled:true});
function construct(entry,variant){
  const c=new ATtiny13A(entry.binary,entry.eeprom,{...entry.options,runtimeModule:variant.module,
    precompiled:entry.translations.get(variant.id)});
  if(variant.audioOnly)c.observePins(0,{retainDuringAudio:false});
  if(entry.divisor){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(entry.divisor));}
  if(entry.adcEnabled){c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,0xe7);}
  if(entry.external){const end=BigInt(entry.frames)*1000000000000n/BigInt(rate);
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,
      transitionCount:end/25000n,knownUntilPs:end}),true);
  }else if(!entry.instructions){
    if(entry.physical){c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
    else{c.injectPins({at:777n,mask:4,levels:4});c.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  }
  return c;
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  flash:c.rom.slice(),eeprom:c.eeprom.slice(),irqFrames:Array.from(c.irqFrames)});
function execute(c,entry,count){
  const raw=[],snapshots=[],checkpoints=[];let ms=0;
  if(entry.instructions){const start=performance.now(),retired=c.run(count);ms=performance.now()-start;
    assert.equal(retired,count);assert.equal(c.cyc,count+Math.floor((count-2)/4));
    assert.equal(c.r[18],Math.floor((count+1)/4)&255);assert.equal(c.r[20],Math.floor((count-1)/4)&255);
    snapshots.push(snapshot(c));
  }else for(let offset=0;offset<count;offset+=blockFrames){
    const n=Math.min(blockFrames,count-offset),start=performance.now(),pcm=c.capturePhysical(n,rate,entry.channels);
    ms+=performance.now()-start;const bytes=Buffer.from(pcm.buffer,pcm.byteOffset,pcm.byteLength);raw.push(bytes);
    snapshots.push(snapshot(c));if(entry.divisor)assert.ok(pcm.every(v=>v===-1));
    checkpoints.push({frames:offset+n,architectureSha256:digest(snapshots.at(-1)),rawSha256:sha(bytes)});
  }
  for(const s of snapshots)assert.equal(s.state.deviceFault,0,entry.id);
  if(entry.adcEnabled)assert.equal(c.data[32+IO.ADCSRA]&0x90,0x90,'enabled ADC completes conversions');
  const pins=entry.physical?c.drainPinsPs():c.drainPins(),output=Buffer.concat(raw);
  return {raw:output,snapshots,pins,record:{ms,checkpoints,finalState:c.state(),rawSha256:sha(output),
    architectureSha256:digest(snapshots.at(-1)),remainingPinsSha256:digest(pins),remainingPins:pins.length,
    translatedSha256:sha(c.transpiledBytes),translatedBytes:c.transpiledBytes.length}};
}
function compare(actual,expected,label,historyOmitted=false){
  assert.ok(actual.raw.equals(expected.raw),label+' exact raw PCM');
  assert.deepEqual(actual.snapshots,expected.snapshots,label+' exact architecture and diagnostics');
  if(!historyOmitted)assert.deepEqual(actual.pins,expected.pins,label+' full host trace');
  else assert.equal(actual.pins.length,0,label+' explicitly unsubscribed history after capture');
}
const out=resolve(root,values.out),started=performance.now();mkdirSync(dirname(out),{recursive:true});
const report={schema:'micromusic-pin-observation-benchmark-v1',createdAt:new Date().toISOString(),
  git:{head:gitText(['rev-parse','HEAD']),status:gitText(['status','--short']),baselineCommit:gitText(['rev-parse',baselineRef])},
  host:{node:process.version,v8:process.versions.v8,flags:process.execArgv,platform:platform(),release:release(),
    arch:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length},
  provenance:{changedInputs,compilerSha256:sha(source('web-player/lib/avr-transpiler.js')),
    runtimes:Object.fromEntries(variants.map(v=>[v.id,{sha256:sha(v.binary),bytes:v.binary.length,inputs:v.manifest.inputs,
      flags:v.manifest.flags,exports:v.manifest.exports,imports:[],memoryPages:2}])),
    supportingSources:Object.fromEntries(['web-player/scripts/benchmark-pin-observation.mjs',
      'web-player/lib/attiny13a-runtime.js','web-player/lib/avr-transpiled-runtime.js',
      'web-player/lib/renderer-device.js','web-player/lib/renderer-package.js',
      'web-player/lib/avr-runtime.js','web-player/tests/fixtures/attiny13a-system-firmware.mjs'].map(path=>[path,sha(source(path))]))},
  parameters:{trials,frames,instructions,rate,blockFrames,clockFrames:1200},
  method:{timing:'Serial uninstrumented run(N) or capturePhysical calls only, including API batch copying. Module generation/compilation, construction, subscription, inputs, hashing, snapshots and comparison are outside timers.',
    order:'One discarded warmup per case/variant, fresh instances, then rotate variants every two trials and reverse on odd trials. With four variants/eight trials, each occupies every position twice. No parallel performance run, affinity, GC control or V8 flags.',
    attribution:'baseline=original runtime; optional eager-full=exact retained initial independent PCM ring with collection at each barrier; candidate-full=independent PCM ring with resumable-phase pressure collection, ordinary eager clock/wait calls and default full trace/legacy audio discard; candidate-audio=same new runtime with explicit host mask0. One unchanged compiler and current host wrapper for all variants.',
    parity:'Exact full chip/CPU state and diagnostics, SRAM/Flash/EEPROM/IRQ, PCM bytes and default full-trace tail at every checkpoint. Audio-only host history is explicitly omitted; before audio starts, queued initialization history is preserved. No deadline or clock-state normalization.',
    limits:'Node coupled CPU/peripheral/pin/PCM execution, no DSP or browser-latency guarantee. Host scheduling, GC and tiering affect timings. Profile samples are not used to assign exclusive subsystem times.'},results:[]};
for(const entry of cases){
  console.log(variants.length+'-way '+entry.id);entry.translations=new Map();
  for(const v of variants){const abi=runtimeABI(new WebAssembly.Instance(v.module).exports,{resumable:!!entry.options.resumable});
    const start=performance.now(),generated=transpileAVR(entry.binary,abi,entry.options);
    const generationMs=performance.now()-start,compile=performance.now();generated.module=new WebAssembly.Module(generated.bytes);
    generated.generationMs=generationMs;generated.compileMs=performance.now()-compile;entry.translations.set(v.id,generated);
  }
  assert.deepEqual(entry.translations.get('candidate-full').bytes,entry.translations.get('candidate-audio').bytes);
  if(values['eager-dir'])assert.deepEqual(entry.translations.get('candidate-full').bytes,entry.translations.get('eager-full').bytes);
  const count=entry.instructions??entry.frames,warm=Math.min(count,entry.instructions?100000:4096);
  for(const v of variants)execute(construct(entry,v),entry,warm);
  const row={id:entry.id,frames:entry.frames,instructions:entry.instructions,channels:entry.channels,options:entry.options,
    adcEnabled:!!entry.adcEnabled,flashSha256:sha(entry.binary),translations:Object.fromEntries(variants.map(v=>{
      const t=entry.translations.get(v.id);return[v.id,{sha256:sha(t.bytes),bytes:t.bytes.length,generationMs:t.generationMs,compileMs:t.compileMs}];})),runs:[]};
  let reference;
  for(let trial=0;trial<trials;trial++){
    const rotation=Math.floor(trial/2)%variants.length,order=[...variants.slice(rotation),...variants.slice(0,rotation)],completed={};
    if(trial%2)order.reverse();
    for(const [position,v] of order.entries()){
      const result=execute(construct(entry,v),entry,count);completed[v.id]=result;
      row.runs.push({trial,position,variant:v.id,...result.record});
    }
    compare(completed['candidate-full'],completed.baseline,entry.id+'/'+trial+'/full');
    if(completed['eager-full'])compare(completed['eager-full'],completed.baseline,entry.id+'/'+trial+'/eager');
    compare(completed['candidate-audio'],completed.baseline,entry.id+'/'+trial+'/audio',!entry.instructions);
    if(reference)compare(completed.baseline,reference,entry.id+'/baseline-determinism');else reference=completed.baseline;
  }
  row.summary=Object.fromEntries(variants.map(v=>[v.id,stats(row.runs.filter(r=>r.variant===v.id).map(r=>r.ms))]));
  for(const [name,before,after] of [['defaultBufferSpeedup','baseline','candidate-full'],
    ['observationSpeedup','candidate-full','candidate-audio'],['combinedSpeedup','baseline','candidate-audio'],
    ...values['eager-dir']?[['pressureSpeedup','eager-full','candidate-full'],['initialBufferSpeedup','baseline','eager-full']]:[]])
    row.summary[name]=stats(Array.from({length:trials},(_,trial)=>{
      const time=id=>row.runs.find(r=>r.variant===id&&r.trial===trial).ms;return time(before)/time(after);}));
  row.validation={exactPcm:true,allArchitectureAndDiagnostics:true,defaultTraceTail:true,
    audioOnlyHistoryOmission:true,crossTrialDeterminism:true,
    stateCheckpointsCompared:(variants.length*trials-1)*Math.max(1,Math.ceil((entry.frames??0)/blockFrames))};
  report.results.push(row);report.complete=report.results.length===cases.length;report.elapsedMs=performance.now()-started;
  writeFileSync(out,JSON.stringify(report,replacer,2)+'\n');
}
console.table(report.results.map(r=>({case:r.id,baseline:r.summary.baseline.median.toFixed(2),
  ...r.summary['eager-full']?{eager:r.summary['eager-full'].median.toFixed(2),pressure:r.summary.pressureSpeedup.median.toFixed(3)+'x'}:{},
  full:r.summary['candidate-full'].median.toFixed(2),audio:r.summary['candidate-audio'].median.toFixed(2),
  default:r.summary.defaultBufferSpeedup.median.toFixed(3)+'x',
  observation:r.summary.observationSpeedup.median.toFixed(3)+'x',combined:r.summary.combinedSpeedup.median.toFixed(3)+'x'})));
console.log('All exact state/PCM checks passed: '+relative(root,out));
