// Compare exact historical/current generated CPU bytes; native runtime is shared.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {transpileAVR,runtimeABI} from '../lib/avr-transpiler.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
import {controlLabels,controlSchedule,controlRatios} from './lib/runtime-control-design.mjs';
import {avr,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{baseline:{type:'string',default:'da3f6504'},measure:{type:'boolean'},
  output:{type:'string',default:'build/neutral-region-evidence.json'},
  'full-tap':{type:'string'},'shared-tap':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n');
const hash=b=>createHash('sha256').update(b).digest('hex');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:4*1024*1024});
const baseline=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
const historical=p=>git('show',baseline+':'+p).toString().replaceAll('\r\n','\n');
const url=s=>'data:text/javascript;base64,'+Buffer.from(s).toString('base64');
const compilerPath='web-player/lib/avr-transpiler.js',regionsPath='web-player/lib/avr-wasm-regions.js';
const oldRegions=url(historical(regionsPath)),dependencies=[];
const oldSource=historical(compilerPath).replace(/from '([^']+)'/g,(_,path)=>{
  if(path==='./avr-wasm-regions.js')return 'from '+JSON.stringify(oldRegions);
  const absolute=new URL(path,new URL('../lib/avr-transpiler.js',import.meta.url));
  const relative=fileURLToPath(absolute).slice(root.length).replaceAll('\\','/');
  assert.equal(historical(relative),text(relative),'Unchanged compiler dependency: '+relative);
  dependencies.push(relative);return 'from '+JSON.stringify(absolute.href);
});
const {transpileAVR:before}=await import(url(oldSource));
for(const path of ['web-player/lib/avr-phase-locals.js','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm'])
  assert.equal(hash(git('show',baseline+':'+path)),hash(read(path)),'Unchanged support: '+path);
const native=read('web-player/wasm/attiny13a.wasm'),exports=new WebAssembly.Instance(runtimeModule).exports;
const legacyABI=runtimeABI(new WebAssembly.Instance(new WebAssembly.Module(read('web-player/wasm/avr.wasm'))).exports);
const abi=runtimeABI(exports),phaseABI=runtimeABI(exports,{resumable:true});
const catalogBytes=read('web-player/firmware.json'),catalog=JSON.parse(catalogBytes),sizes=[];
for(const entry of catalog.entries){
  const profile=resolveAVRProfile(entry.device),image=parseHex(entry.flashHex,profile.flashBytes);
  const modes=[['legacy',legacyABI,{}],...(profile.id==='attiny13a'?
    [['full',abi,{}],['resumable',phaseABI,{resumable:true}],
      ['bounded-phase-locals',phaseABI,{resumable:true,boundedRegions:true,optimizePhaseLocals:true}]]:[])];
  for(const [mode,runtime,policy]of modes){
    const options={device:profile.name,...policy},a=before(image,runtime,options),b=transpileAVR(image,runtime,options);
    assert.ok(WebAssembly.validate(a.bytes)&&WebAssembly.validate(b.bytes));
    if(!policy.boundedRegions)assert.deepEqual(a.bytes,b.bytes,entry.id+' '+mode);
    assert.ok(b.bytes.length<=a.bytes.length);
    sizes.push({id:entry.id,mode,before:a.bytes.length,after:b.bytes.length,saved:a.bytes.length-b.bytes.length,
      beforeSha256:hash(a.bytes),afterSha256:hash(b.bytes)});
  }
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  eeprom:c.eeprom.slice(),rom:c.rom.slice(),irq:Array.from(c.irqFrames)});
const audio=[];
const workloads=['rhythmic','lumiere-stereo','alicia'].map(id=>catalog.entries.find(row=>row.id===id));
workloads.push({id:'neutral-kernel',cpuHz:9600000,kernel:true,
  image:flash({instructions:[avr.nop(),avr.ldi(16,0xab),[0x2f10],[0x0198],[0x9542],avr.rjmp(5,0)]})});
for(const entry of workloads){
  assert.ok(entry);const {id}=entry,image=entry.image??parseHex(entry.flashHex),channels=entry.audioChannels||1;
  const options={...nominalVerificationDeviceOptions(entry.cpuHz),fastBlocks:true,boundedRegions:true,
    optimizePhaseLocals:true,cacheTranslation:false,...entry.kernel?{fuseLow:0xf2,fuseStartupProfile:0}:{}};
  const generated=[before,transpileAVR].map(fn=>fn(image,phaseABI,options));
  const make=side=>new ATtiny13A(image,null,{...options,precompiled:generated[side]});
  const cores=[make(0),make(1)];for(const c of cores)c.observePins(63,{retainDuringAudio:true});
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  const advance=c=>entry.kernel?(assert.equal(c.run(8192),8192),new Float32Array()):c.capturePhysical(256,48000,channels);
  for(let n=0;n<16;n++){
    const samples=cores.map(advance);assert.deepEqual(...samples);
    pcm.update(new Uint8Array(samples[0].buffer,samples[0].byteOffset,samples[0].byteLength));
    const traces=cores.map(c=>c.drainPinsPs());assert.deepEqual(...traces);pinCount+=traces[0].length;
    pins.update(JSON.stringify(traces[0],(_,v)=>typeof v==='bigint'?v+'n':v));assert.deepEqual(...cores.map(snapshot));
    assert.equal(cores[1].state().deviceFault,0);
  }
  const state=cores[1].state();if(!entry.kernel)assert.ok(state.irqs>0&&pinCount>0);
  const result={id,...entry.kernel?{instructions:131072,synthetic:true}:{frames:4096,rate:48000},
    irqs:state.irqs,pinCount,pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex')};
  if(values.measure){
    // Fully serial, balanced four-label controls. Construction, warmup, pin
    // draining and snapshots are outside timing; native pin capture is inside.
    const schedule=controlSchedule(8),runs=[];
    for(let trial=-1;trial<8;trial++)for(const [position,variant]of (trial<0?controlLabels:schedule[trial]).entries()){
      const c=make(variant.startsWith('old')?0:1);c.observePins(63,{retainDuringAudio:true});
      if(entry.kernel)c.run(32768);
      else for(let n=0;n<16;n++){c.capturePhysical(256,48000,channels);c.drainPinsPs();}
      c.drainPinsPs();let ms=0;
      const pcm=createHash('sha256'),trace=[],states=[];
      for(let n=0;n<16;n++){
        const at=performance.now(),samples=advance(c);ms+=performance.now()-at;
        pcm.update(new Uint8Array(samples.buffer,samples.byteOffset,samples.byteLength));
        trace.push(...c.drainPinsPs());states.push(snapshot(c));
      }
      assert.equal(c.state().deviceFault,0);if(!entry.kernel)assert.ok(c.state().irqs>0);
      // Each same-span timed result must also preserve complete state/pins.
      const observation={pcmSha256:pcm.digest('hex'),states,trace};
      if(!result.timingReference)result.timingReference=observation;
      else assert.deepEqual(observation,result.timingReference);
      if(trial>=0)runs.push({trial,position,variant,ms});
    }
    delete result.timingReference;result.runs=runs;result.ratios=controlRatios(runs,8);
    result.warmup=entry.kernel?{instructions:32768}:{frames:4096,rate:48000};
  }
  audio.push(result);
}
const report={schema:'micromusic-neutral-regions-v1',baselineCommit:baseline,compilerIdentity:AVR_CACHE_COMPILER_ID,
  native:{bytes:native.length,sha256:hash(native)},node:process.version,v8:process.versions.v8,
  sources:Object.fromEntries([compilerPath,regionsPath,'web-player/scripts/verify-neutral-regions.mjs',
    'web-player/tests/avr-neutral-regions.test.mjs','web-player/lib/avr-phase-locals.js',
    'web-player/lib/avr-transpiled-runtime.js','web-player/lib/attiny13a-runtime.js',
    'web-player/scripts/lib/runtime-control-design.mjs','web-player/tests/fixtures/attiny13a-system-firmware.mjs',
    ...dependencies].map(p=>[p,hash(text(p))])),
  baselineSources:Object.fromEntries([compilerPath,regionsPath].map(p=>[p,hash(historical(p))])),
  catalogSha256:hash(catalogBytes),sizes,audio,executionSpeedMeasured:!!values.measure,
  ...(values.measure?{timingDesign:'Serial balanced eight-trial/four-label controls. Fresh instances use exact old/new CPU bytes with one unchanged native module. Construction and equal warmup excluded; music warms4096frames through fuse startup. Each measured256frame/8192instruction span excludes hashing, complete snapshots and trace draining. Every timed run retains exact same-span PCM/state/pins. Coupled execution time, not exclusive subsystem or real-time acceptance.'}:{}),
  meaning:'One SREG load/store omitted only for flag-independent bounded regions; IRQ I guard retained. Exact historical/current CPU bytecode comparison uses the same native and JS wrapper. Software evidence only; no silicon or real-time claim.'};
for(const [name,option]of [['fullSuite','full-tap'],['sharedSuite','shared-tap']])if(values[option]){
  const bytes=read(values[option]),tap=bytes.toString();
  const counts=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(key=>{
    const match=tap.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(match,'Incomplete TAP '+key);
    return [key,Number(match[1])];
  }));
  assert.ok(counts.tests>0&&counts.tests===counts.pass);assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  report[name]={...counts,tapSha256:hash(bytes)};
}
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({artifacts:sizes.length,changed:sizes.filter(row=>row.saved).length,
  savedBytes:sizes.filter(row=>row.saved).map(row=>row.saved),activeIrqParityCases:audio.filter(row=>row.irqs>0).length,
  timing:audio.map(row=>({id:row.id,ratios:row.ratios}))}));
