// Untimed historical-byte audit and retained-pin audio comparison.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {parseArgs} from 'node:util';
import {ATtiny13A,runtimeModule,getRuntimeBytes} from '../lib/attiny13a.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
import {parseHex} from '../lib/hex.js';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{baseline:{type:'string',default:'3a73d96b'},
  out:{type:'string',default:'build/sram-blocks-verification.json'}}});
const sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString():x,2)+'\n';
const read=p=>readFileSync(resolve(root,p)),source=p=>read(p).toString('utf8').replaceAll('\r\n','\n');
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:8*1024*1024});
const baseline=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
const historical=p=>git('show',baseline+':'+p).toString('utf8').replaceAll('\r\n','\n');
const changed=['avr-transpiler.js','avr-transpiled-runtime.js','avr-persistent-cache.js','attiny13a-runtime.js','attiny13a-package.js','emulation-configurations.js'].map(p=>'web-player/lib/'+p);
for(const [p,expected] of Object.entries(AVR_CACHE_SOURCES)){
  assert.equal(sha(source(p)),expected,p+' current identity');
  if(!changed.includes(p))assert.equal(source(p),historical(p),p+' unchanged dependency');
}
const oldSource=historical('web-player/lib/avr-transpiler.js').replace(/from '([^']+)'/g,(_,p)=>{
  const url=new URL(p,new URL('../lib/avr-transpiler.js',import.meta.url));
  const path=fileURLToPath(url).slice(root.length).replaceAll('\\','/');
  assert.equal(source(path),historical(path),path+' historical import');return 'from '+JSON.stringify(url.href);
});
const before=(await import('data:text/javascript;base64,'+Buffer.from(oldSource).toString('base64'))).transpileAVR;
for(const p of ['web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm'])assert.deepEqual(read(p),git('show',baseline+':'+p),p+' unchanged native artifact');
const e=new WebAssembly.Instance(runtimeModule).exports,abi=runtimeABI(e),phaseABI=runtimeABI(e,{resumable:true});
const legacyABI=runtimeABI(new WebAssembly.Instance(new WebAssembly.Module(read('web-player/wasm/avr.wasm'))).exports);
const catalogs=['web-player/firmware.json','web-player/hq4-firmware.json'];
const catalog=catalogs.flatMap(p=>JSON.parse(source(p)).entries);
const out=resolve(root,values.out);mkdirSync(dirname(out),{recursive:true});
const support=['web-player/scripts/verify-sram-blocks.mjs',...catalogs];
const report={schema:'micromusic-sram-block-verification-v1',complete:false,baseline,
  compilerIdentity:AVR_CACHE_COMPILER_ID,sourceSha256:{...AVR_CACHE_SOURCES,...Object.fromEntries(support.map(p=>[p,sha(source(p))]))},
  runtimeSha256:sha(getRuntimeBytes()),defaultModules:[],audio:[]};
const save=()=>writeFileSync(out,json(report));save();
for(const entry of catalog){
  const profile=resolveAVRProfile(entry.device),image=parseHex(entry.flashHex,profile.flashBytes);
  const modes=[['legacy',legacyABI,{}],...profile.id==='attiny13a'?
    [['full',abi,{}],['resumable',phaseABI,{resumable:true}],['bounded-phase-locals',phaseABI,{resumable:true,boundedRegions:true,optimizePhaseLocals:true}]]:[]];
  for(const [mode,runtime,policy] of modes){
    const options={device:profile.name,...policy},old=before(image,runtime,options),current=transpileAVR(image,runtime,options);
    assert.ok(WebAssembly.validate(current.bytes));assert.deepEqual(current.bytes,old.bytes,entry.id+' '+mode+' default bytes');
    report.defaultModules.push({id:entry.id,mode,bytes:current.bytes.length,sha256:sha(current.bytes)});
  }
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-tiny'])for(const external of [false,true]){
  const entry=catalog.find(e=>e.id===id);assert.ok(entry);
  const image=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null,hz=entry.cpuHz||9600000;
  const osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const options={oscillatorHz:hz,resumable:true,fastIdle:false,nvmClockProfile:1,nvmCalibrationReferenceHz:hz,
    ...external?{fuseLow:0x78,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz}};
  const cores=[false,true].map(sramBlocks=>new ATtiny13A(image,eeprom,{...options,sramBlocks}));
  // CLKI itself is observed on PB3: drain every sample to retain all source
  // transitions within the native1024-event ring instead of masking that pin.
  const frames=4096,rate=48000,chunk=external?1:128,end=BigInt(frames)*1000000000000n/BigInt(rate);
  const highPs=1000000000000n/(2n*BigInt(hz)),lowPs=highPs+1n;
  for(const c of cores){
    c.observePins(63,{retainDuringAudio:true});
    if(external)assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs,lowPs,
      transitionCount:2n*(end/(highPs+lowPs)),knownUntilPs:end}),true);
    c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});
  }
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  for(let at=0;at<frames;at+=chunk){
    const raw=cores.map(c=>c.capturePhysical(chunk,rate,entry.audioChannels||1));assert.deepEqual(...raw);
    pcm.update(new Uint8Array(raw[0].buffer,raw[0].byteOffset,raw[0].byteLength));
    const traces=cores.map(c=>c.drainPinsPs());assert.deepEqual(...traces);pinCount+=traces[0].length;pins.update(json(traces[0]));
    assert.deepEqual(...cores.map(snapshot));assert.equal(cores[1].state().deviceFault,0);
  }
  assert.ok(pinCount>0&&cores[1].state().irqs>0,'active IRQ and retained pin history');
  report.audio.push({id,clock:external?'clki':'internal',frames,rate,chunk,options,...external?{highPs,lowPs}:{},checkpoints:frames/chunk,pinCount,
    irqs:cores[1].state().irqs,pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex'),stateSha256:sha(json(snapshot(cores[1])))});save();
  console.log(JSON.stringify({id,external,pinCount,irqs:cores[1].state().irqs}));
}
report.complete=true;save();
