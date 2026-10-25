// Equal-policy, four-label controls. Production sources/artifacts are read only.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {cpus,platform,release} from 'node:os';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';
import {AT13_MASK as MASK,AT13_VECTOR as VECTOR} from '../lib/attiny13a-registers.js';
import {controlLabels,controlSchedule,controlRatios,statistics} from './lib/runtime-control-design.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'baseline-ref':{type:'string',default:'4f09550'},
  'change-set':{type:'string',default:'long-internal-span'},
  'validate-only':{type:'boolean'},
  trials:{type:'string',default:'8'},warmups:{type:'string',default:'4'},
  frames:{type:'string',default:'12000'},instructions:{type:'string',default:'1000000'},
  'kernel-frames':{type:'string',default:'1200'},
  case:{type:'string',multiple:true},out:{type:'string',default:'build/benchmarks/runtime-controls.json'}}});
const integer=(v,min,max)=>{const n=Number(v);assert.ok(Number.isInteger(n)&&n>=min&&n<=max);return n;};
const trials=integer(values.trials,8,32),schedule=controlSchedule(trials),warmups=integer(values.warmups,1,8),
  frames=integer(values.frames,1024,48000),kernelFrames=integer(values['kernel-frames'],1200,48000),
  instructions=integer(values.instructions,1000,10000000),rate=48000,block=1024;
const sha=v=>createHash('sha256').update(v).digest('hex');
const stringify=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n,2)+'\n';
const text=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:4*1024*1024});
const baseline=values['baseline-ref'],binaryPath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const old={binary:git(['show',baseline+':'+binaryPath]),manifest:JSON.parse(git(['show',baseline+':'+manifestPath]))},
  current={binary:readFileSync(resolve(root,binaryPath)),manifest:JSON.parse(text(manifestPath))};
for(const [kind,version] of Object.entries({old,current})){
  assert.equal(sha(version.binary),version.manifest.artifacts['attiny13a.wasm']);
  assert.equal(version.binary.length,version.manifest.bytes);
  for(const [path,expected] of Object.entries(version.manifest.inputs))
    assert.equal(sha(kind==='old'?git(['show',baseline+':'+path]).toString().replaceAll('\r\n','\n'):text(path)),expected,kind+'/'+path);
  version.module=new WebAssembly.Module(version.binary);assert.deepEqual(WebAssembly.Module.imports(version.module),[]);
  assert.equal(new WebAssembly.Instance(version.module).exports.memory.buffer.byteLength,131072);
}
for(const key of ['exports','flags','compilerVersion','sources'])assert.deepEqual(old.manifest[key],current.manifest[key],key);
const changedInputs=Object.keys(current.manifest.inputs).filter(path=>old.manifest.inputs[path]!==current.manifest.inputs[path]);
const changeSet=values['change-set'];assert.ok(['long-internal-span','service-inlining','clock-identity','clock-multiply','clock-delay','ns-remainder','watchdog-period','watchdog-lazy'].includes(changeSet));
assert.deepEqual(changedInputs,changeSet==='long-internal-span'?
  ['web-player/native/peripherals/device.c','web-player/native/peripherals/device.h']:
  changeSet.startsWith('clock-')?['web-player/native/peripherals/device_clock.h']:
  changeSet.startsWith('watchdog-')?['web-player/native/peripherals/device.c','web-player/native/devices/attiny13a/clki_board.inc']:['web-player/native/peripherals/device.c']);
const hostSources=['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-phases.js',
  'web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-runtime.js','web-player/lib/attiny13a-runtime.js'];
for(const path of hostSources)assert.equal(text(path),git(['show',baseline+':'+path]).toString().replaceAll('\r\n','\n'),path+' unchanged');
const variants=controlLabels.map(id=>({id,...id.startsWith('old')?old:current}));
assert.equal(variants[0].module,variants[1].module);assert.equal(variants[2].module,variants[3].module);
assert.notEqual(old.module,current.module);
const table=hz=>{const result=Array(128).fill(0);result[0]=hz;return result;};
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const catalogs=['web-player/firmware.json','web-player/hq4-firmware.json'].map(path=>JSON.parse(text(path)));
const catalog=catalogs.flatMap(row=>row.entries),aliases=Object.assign({},...catalogs.map(row=>row.aliases));
const cases=[];
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-auto']){
  const entry=catalog.find(row=>row.id===(aliases[id]??id));assert.ok(entry);const binary=parseHex(entry.flashHex);assert.equal(sha(binary),entry.flashSha256);
  for(const physical of [false,true])cases.push({id:id+'-'+(physical?'physical':'compatible'),
    binary,eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):null,frames,channels:entry.audioChannels||1,physical,
    options:{oscillatorHz:entry.cpuHz||9600000,optimizeFlags:true,
      ...physical?{resumable:true,osccalHz:table(entry.cpuHz||9600000),nvmClockProfile:1,nvmCalibrationReferenceHz:entry.cpuHz||9600000}:{}}});
}
for(const physical of [false,true])cases.push({id:'kernel-'+(physical?'physical':'compatible')+'-direct',binary:kernel,instructions,physical,
  options:{oscillatorHz:9600000,fuseLow:0x72,...physical?{resumable:true,osccalHz:table(9600000)}:{}}});
for(const divisor of [1,256])cases.push({id:'kernel-clki-20m-div'+divisor,binary:kernel,frames:kernelFrames,channels:1,physical:true,external:true,divisor,
  options:{oscillatorHz:20000000,resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}});
cases.push({id:'kernel-internal-20m-div1',binary:kernel,frames:kernelFrames,channels:1,physical:true,divisor:1,
  options:{oscillatorHz:20000000,resumable:true,fuseLow:0x72,osccalHz:table(20000000)}});
for(const id of ['kernel-internal-20m-div1','kernel-clki-20m-div1'])
  cases.push({...cases.find(row=>row.id===id),id:id+'-adc-active',adcEnabled:true});
const wdtVector=VECTOR.WDT; // ATtiny13A vector indices already equal AVR word PCs.
const watchdogKernel=flash({instructions:[avr.rjmp(0,16)]},
  {at:wdtVector,instructions:[avr.rjmp(wdtVector,64)]},
  {at:16,instructions:[avr.sei(),avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(22,19)]},
  {at:64,instructions:[avr.reti()]});
for(const id of ['kernel-internal-20m-div1','kernel-clki-20m-div1'])
  cases.push({...cases.find(row=>row.id===id),id:id+'-watchdog-active',binary:watchdogKernel,watchdogEnabled:true});
const selected=values.case?cases.filter(row=>values.case.includes(row.id)):cases;
if(values.case)assert.equal(selected.length,values.case.length,'unknown or duplicate case');assert.ok(selected.length);
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
function construct(item,variant){
  const c=new ATtiny13A(item.binary,item.eeprom,{...item.options,runtimeModule:variant.module,precompiled:item.generated});
  assert.equal(sha(c.transpiledBytes),item.translationSha256);
  assert.equal(c.pinObservation.mask,63);assert.equal(c.pinObservation.retainDuringAudio,false);
  if(item.previousCPUmodule)assert.notEqual(c._translatedModule,item.previousCPUmodule,'precompiled constructor creates a fresh CPU Module');
  item.previousCPUmodule=c._translatedModule;
  if(item.divisor){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(item.divisor));}
  if(item.adcEnabled){c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,0xe7);}
  if(item.watchdogEnabled)c.writeIO(IO.WDTCR,MASK.WDTIE);
  if(item.external){
    const end=BigInt(item.frames)*1000000000000n/BigInt(rate);
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,transitionCount:end/25000n,knownUntilPs:end}),true);
  }else if(!item.instructions){
    if(item.physical){c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
    else{c.injectPins({at:777n,mask:4,levels:4});c.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  }
  return c;
}
function execute(c,item){
  let ms=0;const snapshots=[],pcm=[];
  if(item.instructions){
    const start=performance.now(),retired=c.run(item.instructions);ms=performance.now()-start;
    assert.equal(retired,item.instructions);assert.equal(c.cyc,item.instructions+Math.floor((item.instructions-2)/4));
    assert.equal(c.r[18],Math.floor((item.instructions+1)/4)&255);assert.equal(c.r[20],Math.floor((item.instructions-1)/4)&255);
    snapshots.push(snapshot(c));
  }else for(let offset=0;offset<item.frames;offset+=block){
    const n=Math.min(block,item.frames-offset),start=performance.now(),raw=c.capturePhysical(n,rate,item.channels);ms+=performance.now()-start;
    if(item.external)assert.ok(raw.every(value=>value===-1));
    pcm.push(Buffer.from(raw.buffer,raw.byteOffset,raw.byteLength));snapshots.push(snapshot(c));
  }
  snapshots.forEach(row=>assert.equal(row.state.deviceFault,0));
  if(item.divisor)assert.equal(snapshots.at(-1).state.clockDivisor,item.divisor,'actual completed CPU divisor must match the case label');
  if(item.adcEnabled)assert.equal(c.data[32+IO.ADCSRA]&0x90,0x90,'active ADC completes conversions');
  if(item.watchdogEnabled){assert.ok(c.irqCount>0,'active watchdog executes its ISR');assert.equal(c.data[32+IO.WDTCR]&MASK.WDTIE,MASK.WDTIE);}
  const raw=Buffer.concat(pcm),pins=item.physical?c.drainPinsPs():c.drainPins();
  return {raw,snapshots,pins,record:{ms,rawSha256:sha(raw),architectureSha256:sha(stringify(snapshots)),
    pinSha256:sha(stringify(pins)),checkpoints:snapshots.length,finalState:c.state()}};
}
function same(actual,expected){
  assert.ok(actual.raw.equals(expected.raw));assert.deepEqual(actual.snapshots,expected.snapshots);assert.deepEqual(actual.pins,expected.pins);
}
const out=resolve(root,values.out);mkdirSync(dirname(out),{recursive:true});
const support=[...hostSources,'web-player/scripts/benchmark-runtime-controls.mjs','web-player/scripts/lib/runtime-control-design.mjs',
  'web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const report={schema:'micromusic-runtime-identical-controls-v1',createdAt:new Date().toISOString(),complete:false,
  mode:values['validate-only']?'validation':'timing',
  git:{head:git(['rev-parse','HEAD']).toString().trim(),baseline:git(['rev-parse',baseline]).toString().trim(),status:git(['status','--short']).toString().trim()},
  host:{node:process.version,v8:process.versions.v8,flags:process.execArgv,platform:platform(),release:release(),cpu:cpus()[0]?.model},
  parameters:{trials,warmups,frames,kernelFrames,instructions,rate,block,schedule,changeSet},
  provenance:{changedInputs,runtimes:Object.fromEntries(variants.map(v=>[v.id,{sha256:sha(v.binary),bytes:v.binary.length,inputs:v.manifest.inputs}])),
    sourceSha256:Object.fromEntries(support.map(path=>[path,sha(text(path))]))},
  method:{identity:'oldA/oldB use one native Module object; newA/newB use another. All labels use identical options, full default trace, generated CPU bytes and ABI. Fresh instances and memories for every run.',
    compilation:'CPU lowering happens once per case; the unmodified precompiled loader creates a fresh CPU Module on each construction, asserted by object identity. Construction/compilation, input setup, snapshots, hashing and checks are outside execution timers.',
    warmup:'Each label receives the same number of discarded full-workload warmups in recorded Williams order (position-balanced when warmups is4 or8). Warmups are retained and checked against the same exact reference; no stable-tiering guarantee is inferred.',
    order:'Williams four-label design and reversed rows; every label occupies every position equally and every directed adjacent pair occurs equally often. Runs are serial. No affinity, GC or CPU-frequency control.',
    comparison:'Exact PCM bytes, all CPU/device state and diagnostics, SRAM/Flash/EEPROM/IRQ and complete host tail after every batch. No observer omission or diagnostic normalization.',
    interpretation:'oldA/oldB and newA/newB are null controls. Cross-version ratio is geometric mean of the two old elapsed times divided by geometric mean of the two new times within each trial. This is coupled Node execution; it does not isolate exclusive subsystem costs or prove a C-source cause.'},results:[]};
for(const item of selected){
  console.log('4-way '+item.id);
  const abi=runtimeABI(new WebAssembly.Instance(old.module).exports,{resumable:!!item.options.resumable});
  assert.deepEqual(abi,runtimeABI(new WebAssembly.Instance(current.module).exports,{resumable:!!item.options.resumable}));
  item.generated=transpileAVR(item.binary,abi,item.options);item.translationSha256=sha(item.generated.bytes);
  const other=transpileAVR(item.binary,abi,item.options);assert.deepEqual(item.generated.bytes,other.bytes);
  const row={id:item.id,options:item.options,frames:item.frames,instructions:item.instructions,channels:item.channels,
    ...(item.watchdogEnabled?{watchdogEnabled:true}:{}),
    flashSha256:sha(item.binary),translationSha256:item.translationSha256,translationBytes:item.generated.bytes.length,warmups:[],runs:[]};
  let reference;
  if(values['validate-only']){
    for(const [position,label]of ['oldA','newA'].entries()){
      const result=execute(construct(item,variants.find(v=>v.id===label)),item);
      if(reference)same(result,reference);else reference=result;
      row.runs.push({trial:0,position,variant:label,...result.record});
    }
  }else{
  for(let pass=0;pass<warmups;pass++)for(const [position,label] of schedule[pass].entries()){
    const result=execute(construct(item,variants.find(v=>v.id===label)),item);
    if(reference)same(result,reference);else reference=result;
    row.warmups.push({pass,position,variant:label,...result.record});
  }
  for(let trial=0;trial<trials;trial++)for(const [position,label] of schedule[trial].entries()){
    const result=execute(construct(item,variants.find(v=>v.id===label)),item);same(result,reference);
    row.runs.push({trial,position,variant:label,...result.record});
  }
  row.summary={...Object.fromEntries(controlLabels.map(id=>[id,statistics(row.runs.filter(run=>run.variant===id).map(run=>run.ms))])),
    ratios:controlRatios(row.runs,trials)};
  }
  row.validation={exactWarmupAndTimedState:true,exactPcmAndPins:true,sameRuntimeModuleInsidePairs:true,identicalCPUBytesAndABI:true,
    freshCPUmodulePerConstruction:true,checkpointsCompared:(row.warmups.length+row.runs.length-1)*reference.snapshots.length};
  report.results.push(row);report.complete=report.results.length===selected.length;writeFileSync(out,stringify(report));
}
if(!values['validate-only'])console.table(report.results.map(row=>({case:row.id,oldIdentity:row.summary.ratios.oldIdentity.median.toFixed(3),
  newIdentity:row.summary.ratios.newIdentity.median.toFixed(3),crossVersion:row.summary.ratios.crossVersion.median.toFixed(3)})));
console.log('Exact controls passed: '+out);
