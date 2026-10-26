import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Worker,MessageChannel} from 'node:worker_threads';
import {createRenderer,DEFAULT_ENGINE,DEFAULT_EMULATION_CONFIGURATION} from '../lib/engines.js';
import {EMULATION_CONFIGURATIONS,emulationConfiguration,executionOptions,nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';
import {sameCPU} from './helpers/avr-test-state.mjs';
import {playerApp} from './helpers/player-app.mjs';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const tiny88=JSON.parse(readFileSync(new URL('../firmware-attiny88-16mhz.json',import.meta.url))).entries[0];
const entry=catalog.entries[0],flush=async()=>{await Promise.resolve();await Promise.resolve();};
const init=app=>app.workers.at(-1).messages.find(m=>m.type==='init');
const radio=(app,value)=>app.radios.find(r=>r.value===value);

test('two immutable model presets keep site/WASM as the default and reject unknown names',async()=>{
  assert.equal(DEFAULT_ENGINE,'wasm');assert.equal(DEFAULT_EMULATION_CONFIGURATION,'site');
  assert.deepEqual(Object.keys(EMULATION_CONFIGURATIONS),['site','verification']);
  assert.ok(Object.isFrozen(emulationConfiguration()));assert.ok(Object.isFrozen(EMULATION_CONFIGURATIONS));
  for(const name of ['typo','toString','__proto__',null,{}]){
    assert.throws(()=>emulationConfiguration(name),/Unknown emulation configuration/);
    await assert.rejects(createRenderer(entry,48000,{},undefined,name),/Unknown emulation configuration/);
  }
  const a=nominalVerificationDeviceOptions(),b=nominalVerificationDeviceOptions();a.osccalHz[0]=1;
  assert.equal(b.osccalHz[0],9600000);assert.equal(b.osccalHz.filter(Boolean).length,1);
});

test('verification selects the full resumable physical board and retains exact partial-instruction deadlines',async()=>{
  const r=await createRenderer(entry,48000,{},undefined,'verification'),c=r.core;
  assert.equal(r.engine,'transpiled');assert.equal(r.emulationModel,'physical-device');
  assert.equal(c._translationOptions.resumable,true);assert.equal(c.fastIdle,false);
  assert.equal(c.transpilation.optimizeFlags,false);assert.equal(c.transpilation.maxBlockInstructions,2);
  const start=c.state().startupDeadlinePs;c.runUntilPs(start+1n);
  assert.equal(c.state().timePs,start+1n);assert.equal(c.state().cpuPhase.active,1);
  assert.equal(c.state().deviceFault,0);
  for(const engine of ['js','wasm'])await assert.rejects(createRenderer(entry,48000,{},engine,'verification'),/verification requires/);
});

test('verification physical pin audio is independent of render block partition',async()=>{
  const a=await createRenderer(entry,48000,{},undefined,'verification'),b=await createRenderer(entry,48000,{},undefined,'verification');
  const pieces=[a.render(17),a.render(127),a.render(256)],joined=Float32Array.from(pieces.flatMap(p=>Array.from(p)));
  assert.deepEqual(joined,b.render(400));assert.deepEqual(a.core.data,b.core.data);
  assert.deepEqual(a.core.eeprom,b.core.eeprom);assert.deepEqual(a.core.state(),b.core.state());
  assert.equal(a.core.state().timePs,400n*1000000000000n/48000n);
});

for(const engine of ['js','wasm','transpiled'])test(`Tiny88 ${engine}: verification retains supported music output with wait skipping disabled`,async()=>{
  const a=await createRenderer(tiny88,48000,{},engine,'site'),b=await createRenderer(tiny88,48000,{},engine,'verification');
  assert.equal(a.emulationModel,'music');assert.equal(b.emulationModel,'core-timer-reference');
  assert.equal(b.core.fastIdle,false);assert.equal(b.core.fastBlocks,false);
  for(const n of [17,127,1024]){assert.deepEqual(a.render(n),b.render(n));sameCPU(a.core,b.core);}
  assert.ok(b.core.irqCount>0);assert.equal(b.core.lost+b.core.workLost,0);
});

test('verification packages keep hardware settings and recompile only CPU execution policy',async()=>{
  const runtime=new Uint8Array(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url)));
  const configuration={...nominalVerificationDeviceOptions(8000000),factoryOsccal96:12,fuseStartupProfile:0};
  for(const key of Object.keys(executionOptions('verification')))delete configuration[key];
  configuration.osccalHz[0]=0;configuration.osccalHz[12]=8000000;
  const flash=parseHex(entry.flashHex),abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports,{resumable:true});
  const generated=transpileAVR(flash,abi,{resumable:true}),pkg=await createPackage({flash,configuration,runtime,translated:generated.bytes});
  const c=await ATtiny13A.fromPackage(pkg,{verification:true});
  assert.equal(c.transpilation.optimizeFlags,false);assert.equal(c.fastIdle,false);
  assert.equal(c.state().oscillatorHz,8000000);assert.equal(c.readIO(IO.OSCCAL),12);
  assert.deepEqual(c.packageIntegrity,pkg.integrity);
  const r=await createRenderer({devicePackage:pkg,pwmHz:31250},48000,{},undefined,'verification');
  assert.equal(r.emulationModel,'packaged-device');assert.equal(r.render(17).length,17);
  const oldAbi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
  const compatible=await createPackage({flash,runtime,translated:transpileAVR(flash,oldAbi).bytes});
  await assert.rejects(ATtiny13A.fromPackage(compatible,{verification:true}),/resumable package/);
});

test('page mode selection restarts the worker, persists in URL and restores the site engine',async()=>{
  const app=await playerApp({speech:false});
  assert.equal(init(app).configuration,'site');
  radio(app,'js').checked=true;radio(app,'js').onchange();await flush();
  const old=app.workers.at(-1);app.get('emulation-configuration').value='verification';
  app.get('emulation-configuration').onchange();await flush();
  assert.equal(old.terminated,true);assert.equal(init(app).engine,'transpiled');
  assert.equal(init(app).configuration,'verification');assert.equal(radio(app,'js').disabled,true);
  assert.equal(app.location.searchParams.get('emulation'),'verification');
  app.get('emulation-configuration').value='site';app.get('emulation-configuration').onchange();await flush();
  assert.equal(init(app).engine,'js');assert.equal(radio(app,'js').disabled,false);
  assert.equal(app.location.searchParams.has('emulation'),false);
  const linked=await playerApp({speech:false,configuration:'verification'});
  assert.equal(init(linked).engine,'transpiled');assert.equal(init(linked).configuration,'verification');
});

test('Tiny88 page verification states its peripheral limit and preserves mode through board changes',async()=>{
  const app=await playerApp({speech:false,device:'attiny88',configuration:'verification'});
  assert.equal(init(app).configuration,'verification');assert.equal(init(app).engine,'wasm');
  assert.match(app.get('emulation-note').textContent,/Timer1.*Полная периферия ещё не реализована/);
  app.get('board-select').value='mh-et-live-16mhz';await app.get('board-select').onchange();await flush();
  assert.equal(init(app).configuration,'verification');assert.equal(init(app).entry.cpuHz,16000000);
});

const message=(port,type)=>new Promise((resolve,reject)=>{
  const handler=data=>{if(data.type==='error'){port.off('message',handler);reject(Error(data.message));}
    else if(data.type===type){port.off('message',handler);resolve(data);}};port.on('message',handler);
});
test('real Worker retains verification through audio-port recreation and queued controls',async t=>{
  const worker=new Worker(new URL('./helpers/browser-worker-node.mjs',import.meta.url)),ports=new MessageChannel();
  t.after(()=>worker.terminate());t.after(()=>ports.port1.close());
  const ready=message(worker,'ready');worker.postMessage({type:'init',entry,sampleRate:48000,configuration:'verification'});
  worker.postMessage({type:'controls',controls:{volume:0,cutoff:6000}});
  worker.postMessage({type:'audio-port',port:ports.port2,sampleRate:48000},[ports.port2]);
  assert.equal((await ready).emulationModel,'physical-device');
  const expected=await createRenderer(entry,48000,{volume:0,cutoff:6000},undefined,'verification');
  const state=message(worker,'state'),samples=message(ports.port1,'samples');ports.port1.postMessage({type:'need',frames:64});
  const actual=await samples;assert.deepEqual(actual.samples,expected.render(64));assert.ok(actual.samples.every(x=>x===0));
  assert.deepEqual((await state).state,expected.core.state());
});
