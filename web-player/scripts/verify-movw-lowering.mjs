// Historical/current CPU emission comparison with one unchanged native device.
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
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{baseline:{type:'string',default:'6f95e913'},
  output:{type:'string',default:'build/movw-lowering-evidence.json'},
  'full-tap':{type:'string'},'shared-tap':{type:'string'}}});
const read=p=>readFileSync(resolve(root,p));
const normalized=p=>read(p).toString('utf8').replaceAll('\r\n','\n');
const hash=b=>createHash('sha256').update(b).digest('hex');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:4*1024*1024});
const baseline=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
const historical=p=>git('show',baseline+':'+p).toString('utf8').replaceAll('\r\n','\n');
const compilerPath='web-player/lib/avr-transpiler.js',dependencies=[];
for(const [path,expected]of Object.entries(AVR_CACHE_SOURCES)){
  assert.equal(hash(normalized(path)),expected,'Current source identity: '+path);
  if(path!==compilerPath)assert.equal(historical(path),normalized(path),'Unchanged source graph: '+path);
}
const oldSource=historical(compilerPath).replace(/from '([^']+)'/g,(_,path)=>{
  const absolute=new URL(path,new URL('../lib/avr-transpiler.js',import.meta.url));
  const relative=fileURLToPath(absolute).slice(root.length).replaceAll('\\','/');
  assert.equal(historical(relative),normalized(relative),'Unchanged compiler dependency: '+relative);
  dependencies.push(relative);return 'from '+JSON.stringify(absolute.href);
});
const {transpileAVR:before}=await import('data:text/javascript;base64,'+Buffer.from(oldSource).toString('base64'));
for(const path of ['web-player/lib/avr-phase-locals.js','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm'])
  assert.equal(hash(git('show',baseline+':'+path)),hash(read(path)),'Unchanged support: '+path);
const native=read('web-player/wasm/attiny13a.wasm');
const exports=new WebAssembly.Instance(runtimeModule).exports;
const legacyABI=runtimeABI(new WebAssembly.Instance(new WebAssembly.Module(read('web-player/wasm/avr.wasm'))).exports);
const abi=runtimeABI(exports),phaseABI=runtimeABI(exports,{resumable:true});
function bodies(bytes){
  let p=8;
  const u32=()=>{let n=0;for(let s=0;s<35;s+=7){const b=bytes[p++];n+=(b&127)*2**s;if(!(b&128))return n;}throw Error('Invalid WASM');};
  while(p<bytes.length){
    const id=bytes[p++],size=u32(),end=p+size;
    if(id===10)return Array.from({length:u32()},()=>{
      const size=u32(),body=bytes.subarray(p,p+size);p+=size;return body;
    });
    p=end;
  }
  throw Error('Missing code section');
}
const catalogPaths=['web-player/firmware.json','web-player/hq4-firmware.json'];
const catalog=catalogPaths.flatMap(p=>JSON.parse(read(p)).entries),sizes=[];
for(const entry of catalog){
  const profile=resolveAVRProfile(entry.device),image=parseHex(entry.flashHex,profile.flashBytes);
  const modes=[['legacy',legacyABI,{}],...(profile.id==='attiny13a'?
    [['full',abi,{}],['resumable',phaseABI,{resumable:true}],
      ['bounded-phase-locals',phaseABI,{resumable:true,boundedRegions:true,optimizePhaseLocals:true}]]:[])];
  for(const [mode,runtime,policy]of modes){
    const options={device:profile.name,...policy},a=before(image,runtime,options),b=transpileAVR(image,runtime,options);
    assert.ok(WebAssembly.validate(a.bytes)&&WebAssembly.validate(b.bytes));
    assert.deepEqual(a.manifest,b.manifest,'Unchanged manifest '+entry.id+' '+mode);
    const oldBodies=bodies(a.bytes),newBodies=bodies(b.bytes),m=a.manifest;
    assert.equal(oldBodies.length,newBodies.length);
    let unchangedBodies=0;
    for(let n=0;n<oldBodies.length;n++){
      const affected=n<m.mapping.length?m.mapping[n].name==='MOVW':n<m.mapping.length+m.blocks.length?
        Array.from({length:m.blocks[n-m.mapping.length].instructions},(_,j)=>
          m.mapping[(m.blocks[n-m.mapping.length].start+j)%m.mapping.length]).some(i=>i.name==='MOVW'):false;
      if(!affected){assert.deepEqual(oldBodies[n],newBodies[n],'Unchanged function '+n);unchangedBodies++;}
    }
    assert.ok(b.bytes.length<=a.bytes.length,entry.id+' '+mode+' grew');
    sizes.push({id:entry.id,mode,before:a.bytes.length,after:b.bytes.length,saved:a.bytes.length-b.bytes.length,
      unchangedBodies,
      beforeSha256:hash(a.bytes),afterSha256:hash(b.bytes)});
  }
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  eeprom:c.eeprom.slice(),rom:c.rom.slice(),irq:Array.from(c.irqFrames)});
const audio=[];
for(const id of ['rhythmic','lumiere-stereo','alicia'])for(const mode of ['compatible','physical']){
  const entry=catalog.find(row=>row.id===id);assert.ok(entry);
  const image=parseHex(entry.flashHex),channels=entry.audioChannels||1;
  const options={...(mode==='physical'?nominalVerificationDeviceOptions(entry.cpuHz):{cpuHz:entry.cpuHz}),
    fastBlocks:true,cacheTranslation:false,...(mode==='physical'?{boundedRegions:true,optimizePhaseLocals:true}:{})};
  const generated=[before,transpileAVR].map(fn=>fn(image,mode==='physical'?phaseABI:abi,options));
  const cores=generated.map(precompiled=>new ATtiny13A(image,null,{...options,precompiled}));
  const modules=cores.map(c=>c._translatedModule);
  assert.ok(modules.every(m=>m instanceof WebAssembly.Module));
  for(const c of cores)c.observePins(63,{retainDuringAudio:true});
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  for(let n=0;n<16;n++){
    const samples=cores.map(c=>c.capturePhysical(256,48000,channels));assert.deepEqual(...samples);
    for(let side=0;side<cores.length;side++)assert.equal(cores[side]._translatedModule,modules[side],
      'Reference CPU module rebound during capture');
    pcm.update(new Uint8Array(samples[0].buffer,samples[0].byteOffset,samples[0].byteLength));
    const traces=cores.map(c=>mode==='physical'?c.drainPinsPs():c.drainPins());
    assert.deepEqual(...traces);pinCount+=traces[0].length;
    pins.update(JSON.stringify(traces[0],(_,v)=>typeof v==='bigint'?v+'n':v));
    assert.deepEqual(...cores.map(snapshot));assert.equal(cores[1].state().deviceFault,0);
  }
  const state=cores[1].state();assert.ok(state.irqs>0&&pinCount>0);
  audio.push({id,mode,frames:4096,rate:48000,checkpoints:16,irqs:state.irqs,pinCount,
    policy:{fastBlocks:true,optimizeFlags:options.optimizeFlags??true,
      boundedRegions:options.boundedRegions??false,optimizePhaseLocals:options.optimizePhaseLocals??false},
    pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex')});
}
const report={schema:'micromusic-movw-lowering-v1',baselineCommit:baseline,
  compilerIdentity:AVR_CACHE_COMPILER_ID,native:{bytes:native.length,sha256:hash(native)},
  compilerSourceGraph:AVR_CACHE_SOURCES,
  node:process.version,v8:process.versions.v8,
  sources:Object.fromEntries([compilerPath,'web-player/scripts/verify-movw-lowering.mjs',
    'web-player/tests/avr-movw-lowering.test.mjs','web-player/lib/avr-phase-locals.js',
    'web-player/lib/avr-transpiled-runtime.js','web-player/lib/attiny13a-runtime.js',
    ...dependencies].map(p=>[p,hash(normalized(p))])),
  baselineSources:{[compilerPath]:hash(historical(compilerPath))},
  catalogs:Object.fromEntries(catalogPaths.map(p=>[p,hash(read(p))])),sizes,audio,
  executionSpeedMeasured:false,
  meaning:'Word copy lowers uncached MOVW register traffic only. One unchanged native module and current JS wrapper execute exact old/new CPU bytecode. Register-cached regions retain their local path. Software evidence only, with no speed, silicon, real-time or complete stage5 claim.'};
for(const [name,option]of [['fullSuite','full-tap'],['sharedSuite','shared-tap']])if(values[option]){
  const bytes=read(values[option]),tap=bytes.toString();
  const counts=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(key=>{
    const match=tap.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(match,'Incomplete TAP '+key);
    return [key,Number(match[1])];
  }));
  assert.ok(counts.tests>0&&counts.tests===counts.pass);
  assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  report[name]={...counts,tapSha256:hash(bytes)};
}
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({artifacts:sizes.length,changed:sizes.filter(row=>row.saved).length,
  savedBytes:sizes.filter(row=>row.saved).map(row=>row.saved),activeIrqParityCases:audio.length}));
