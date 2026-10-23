import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile,mkdtemp,writeFile,copyFile,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {Worker,MessageChannel} from 'node:worker_threads';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage,DEFAULT_CONFIGURATION,PACKAGE_ABI,PACKAGE_FORMAT} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {createRenderer} from '../lib/engines.js';
import {packageEntry} from '../lib/package-entry.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const runtime=new Uint8Array(await readFile(new URL('../wasm/attiny13a.wasm',import.meta.url)));
const abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
async function pack(image,configuration={},eeprom){
  return createPackage({flash:image,eeprom,configuration,runtime,translated:transpileAVR(image,abi).bytes});
}
const gpio=sequential([avr.ldi(16,2),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16)]);
const pkg=await pack(gpio,{factoryOsccal96:73});

async function historicalPackage(version,configuration={}){
  const fixture=JSON.parse(await readFile(new URL(`./fixtures/attiny13a-runtime-v${version}.json`,import.meta.url),'utf8'));
  const runtime=gunzipSync(Buffer.from(fixture.data,'base64'));
  const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
  assert.equal(runtime.length,fixture.bytes);assert.equal(hash(runtime),fixture.sha256);
  const abi=runtimeABI(new WebAssembly.Instance(await WebAssembly.compile(runtime)).exports);
  const generated=transpileAVR(gpio,abi),flash=new Uint8Array(1024).fill(255);flash.set(gpio);
  const assets=Object.fromEntries(Object.entries({flash,eeprom:new Uint8Array(64).fill(255),translated:generated.bytes,runtime})
    .map(([key,value])=>[key,{encoding:'base64',bytes:value.length,sha256:hash(value),data:Buffer.from(value).toString('base64')}]));
  const options={...DEFAULT_CONFIGURATION,...configuration};
  for(const name of version===1?['osccalHz','nvmClockProfile','nvmCalibrationReferenceHz','powerResetProfile','resetInputProfile']:['resetInputProfile'])delete options[name];
  const pkg={format:PACKAGE_FORMAT,version,device:'ATtiny13A',abi:{id:PACKAGE_ABI,layout:abi},configuration:options,manifest:generated.manifest,assets};
  const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  pkg.integrity={algorithm:'SHA-256',sha256:hash(canonical(pkg))};return pkg;
}

test('original v1 runtime loads default legacy options and supplies missing state observers',async()=>{
  const c=await ATtiny13A.fromPackage(await historicalPackage(1));c.run(3);
  assert.equal(c.readIO(IO.PORTB),2);assert.equal(c.state().starting,false);
  assert.equal(c.state().bodDisabled,false);assert.equal(c.state().bodRecovering,false);
  assert.equal(c.state().startupDeadline,c.state().baseHalf);
  assert.deepEqual(c.capturePhysical(3,48000),Float32Array.of(1,1,1));
  assert.equal(c.state().deviceFault,0);
  for(const configuration of [{factoryOsccal96:1},{bodRecoveryNs:70000},{fuseStartupProfile:1}])
    await assert.rejects(ATtiny13A.fromPackage(await historicalPackage(1,configuration)),/Invalid device configuration/);
});

test('original v3 runtime loads without requiring later analog RESET exports',async()=>{
  const c=await ATtiny13A.fromPackage(await historicalPackage(3));c.run(3);
  assert.equal(c.readIO(IO.PORTB),2);assert.equal(c.state().deviceFault,0);
  assert.equal(c._exports.avr_device_reset_input_enabled,undefined);
  assert.equal(c.state().resetInputEnabled,undefined);
  assert.deepEqual(c.capturePhysical(3,48000),Float32Array.of(1,1,1));
});

test('package executes the supplied translation and reproduces explicit initial EEPROM/configuration',async()=>{
  const eeprom=Uint8Array.from({length:64},(_,n)=>n);
  const saved=await pack(gpio,{fuseLow:0x62,factoryOsccal96:73,fuseStartupProfile:1},eeprom);
  const c=await ATtiny13A.fromPackage(saved);
  assert.equal(c instanceof ATtiny13A,true);assert.deepEqual(c.eeprom,eeprom);
  assert.equal(c.readIO(0x31),73);assert.equal(c.state().clockDivisor,8);
  assert.equal(c.state().starting,true);assert.equal(c.state().startupDeadline,40n);
  assert.ok(Buffer.from(c.transpiledBytes).equals(Buffer.from(saved.assets.translated.data,'base64')),'supplied translation bytes');
  assert.deepEqual(c.packageIntegrity,saved.integrity);
  c.runUntil(40n);c.run(3);assert.equal(c.readIO(IO.PORTB),2);assert.equal(c.state().deviceFault,0);
});

test('calibrated clock package executes its supplied CPU and physical audio path',async()=>{
  const osccalHz=Array(128).fill(0);osccalHz[50]=9600000;osccalHz[51]=9696000;
  const image=sequential([avr.ldi(16,51),avr.out(0x31,16),avr.ldi(17,42)]);
  const c=await ATtiny13A.fromPackage(await pack(image,{factoryOsccal96:50,osccalHz}));
  c.run(3);assert.equal(c.r[17],42);assert.equal(c.state().oscillatorHz,9696000);
  c.runUntilPs(1000000n);assert.equal(c.state().deviceFault,0);
  assert.equal(c.capturePhysical(11,48000,2).length,22);
});

test('corrupt package fails before any runtime or translated instance is created',async()=>{
  const bad=structuredClone(pkg);bad.configuration.fuseLow^=16;
  const original=WebAssembly.Instance;
  try {
    WebAssembly.Instance=class {constructor(){assert.fail('unverified instance');}};
    await assert.rejects(ATtiny13A.fromPackage(bad),/SHA-256 mismatch/);
  } finally {WebAssembly.Instance=original;}
});

test('package loader runs with only JavaScript loader files and no default WASM artifacts',async t=>{
  const dir=await mkdtemp(join(tmpdir(),'micromusic-package-loader-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  await mkdir(join(dir,'devices'));
  for(const name of ['avr-runtime.js','avr-transpiler.js','avr-wasm-phases.js','avr-transpiled-runtime.js','attiny13a-runtime.js','attiny13a-package.js','attiny13a-registers.js',
    'devices/profiles.js','devices/attiny13a-profile.js','devices/attiny13a-reset-profile.js'])
    await copyFile(new URL('../lib/'+name,import.meta.url),join(dir,name));
  await writeFile(join(dir,'package.json'),'{"type":"module"}');
  await writeFile(join(dir,'firmware.json'),JSON.stringify(pkg));
  const result=spawnSync(process.execPath,['--input-type=module','-e',
    'import {ATtiny13A} from "./attiny13a-runtime.js";import {readFileSync} from "node:fs";const c=await ATtiny13A.fromPackage(readFileSync("firmware.json","utf8"));c.run(3);if(c.readIO(24)!==2)throw Error("firmware did not run");'],{cwd:dir,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});

test('SPM after package loading invalidates the supplied compiled image before execution',async()=>{
  const ldi=(d,k)=>avr.ldi(d,k)[0],out=(a,v)=>[ldi(16,v),...avr.out(a,16)];
  const words=[ldi(30,0),ldi(31,1),...out(0x37,3),0x95e8];
  for(const [offset,word] of [[0,ldi(20,0x5a)],[2,0xcfff]])words.push(
    ldi(30,offset),ldi(16,word&255),0x2e00,ldi(16,word>>8),0x2e10,...out(0x37,1),0x95e8);
  words.push(ldi(30,0),...out(0x37,5),0x95e8);words.push(0xc000|((128-words.length-1)&0xfff));
  const image=flash({instructions:[words]},{at:128,instructions:[avr.ldi(20,0x11),[0xcfff]]});
  const c=await ATtiny13A.fromPackage(await pack(image,{fuseHigh:0xef,spmCommandCycles:4}));
  const original=c._translatedModule;c.runUntil(200000n);
  assert.notEqual(c._translatedModule,original);assert.equal(c.r[20],0x5a);
  assert.equal(c._exports.avr_device_generation(),2n);assert.equal(c.state().deviceFault,0);
});

test('package renderer preserves physical samples, DSP and controls across batches',async()=>{
  const entry={devicePackage:pkg,pwmHz:37500,audioChannels:1};
  const a=await createRenderer(entry,48000,{},'device'),b=await createRenderer(entry,48000,{},'device');
  a.setAudioControls({cutoff:9000,volume:.3});b.setAudioControls({cutoff:9000,volume:.3});
  const expected=a.render(4096),actual=new Float32Array(4096);
  actual.set(b.render(127));actual.set(b.render(3969),127);
  assert.deepEqual(actual,expected);assert.deepEqual(a.core.state(),b.core.state());
  await assert.rejects(createRenderer(entry,48000,{},'wasm'),/requires the device engine/);
});

test('browser import derives display memory and fuses from the verified package',async()=>{
  const entry=await packageEntry(JSON.stringify(pkg),{name:'test.attiny13a.json'});
  assert.equal(entry.title,'test.attiny13a.json');assert.equal(entry.audioChannels,2);
  assert.equal(entry.deviceConfiguration.factoryOsccal96,73);
  assert.ok(Buffer.from(parseHex(entry.flashHex)).equals(Buffer.from(pkg.assets.flash.data,'base64')));
  assert.ok(Buffer.from(parseHex(entry.eepromHex,64)).equals(Buffer.from(pkg.assets.eeprom.data,'base64')));
  assert.equal(entry.flashSha256,pkg.assets.flash.sha256);
  const renderer=await createRenderer(entry,48000,{},'device');
  assert.equal(renderer.render(128).length,256);
});

function message(target,type){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{target.off('message',receive);reject(Error(type+' timed out'));},10000);
  function receive(data){if(data.type!==type&&data.type!=='error')return;clearTimeout(timer);target.off('message',receive);data.type==='error'?reject(Error(data.message)):resolve(data);}
  target.on('message',receive);
});}
test('real Worker loads the package and restarts it for the audio port',async t=>{
  const worker=new Worker(new URL('./helpers/browser-worker-node.mjs',import.meta.url));t.after(()=>worker.terminate());
  const ports=new MessageChannel();t.after(()=>ports.port1.close());
  const entry={devicePackage:pkg,pwmHz:37500},ready=message(worker,'ready');
  worker.postMessage({type:'init',entry,engine:'device',sampleRate:48000});
  assert.equal((await ready).engine,'device');
  worker.postMessage({type:'audio-port',sampleRate:48000,port:ports.port2},[ports.port2]);
  const samples=message(ports.port1,'samples'),state=message(worker,'state');
  ports.port1.postMessage({type:'need',frames:4096});
  const expected=await createRenderer(entry,48000,{},'device');
  assert.deepEqual((await samples).samples,expected.render(4096));
  assert.deepEqual((await state).state,expected.core.state());
});
