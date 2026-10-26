import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createCachedDeviceCore} from '../lib/avr-persistent-cache.js';
import {createIndexedDBTranslationStore} from '../lib/avr-indexeddb-cache.js';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {createDeviceRenderer} from '../lib/renderer-device.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';
import {avr,sequential,flash as segments} from './fixtures/attiny13a-system-firmware.mjs';
const runtimeBytes=getRuntimeBytes(),image=sequential([avr.ldi(20,0x5a)]);
function memoryStore(){
  const rows=new Map();return {rows,reads:0,writes:0,
    get(key){this.reads++;return structuredClone(rows.get(key)??null);},
    put(key,value){this.writes++;rows.set(key,structuredClone(value));return true;},delete:key=>rows.delete(key)};
}
const make=(store,extra={})=>createCachedDeviceCore({Core:ATtiny13A,flash:image,runtimeBytes,store,...extra});
const same=(a,b)=>{
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.deepEqual(a.rom,b.rom);assert.deepEqual(a.eeprom,b.eeprom);
};
const table=()=>{const result=Array(128).fill(0);result[0]=1000000;return result;};

test('generated compiler identity follows all compiler/host sources',()=>{
  const r=spawnSync(process.execPath,[fileURLToPath(new URL('../scripts/generate-avr-cache-identity.mjs',import.meta.url)),'--check'],{encoding:'utf8'});
  assert.equal(r.status,0,r.stderr);assert.match(AVR_CACHE_COMPILER_ID,/^[0-9a-f]{64}$/);
});

test('runtime bytes are independent copies suitable for cache identity checks',()=>{
  const a=getRuntimeBytes(),b=getRuntimeBytes();assert.deepEqual(a,b);
  a.fill(0);assert.deepEqual(getRuntimeBytes(),b);assert.notEqual(a.buffer,b.buffer);
});

test('stored WASM skips translation while isolating every new chip and public diagnostics',async()=>{
  const store=memoryStore(),a=await make(store),b=await make(store);
  assert.equal(a.persistentTranslationCache.status,'miss');assert.equal(a.persistentTranslationCache.stored,true);
  assert.equal(b.persistentTranslationCache.hit,true);assert.ok(b._translationOptions.precompiled);
  assert.notEqual(a._exports.memory,b._exports.memory);assert.equal(store.writes,1);same(a,b);
  a.r[20]=0xa5;a.eeprom[3]=0;b.transpilation.abi.data=0;b.transpiledBytes.fill(0);
  const c=await make(store);assert.equal(c.persistentTranslationCache.hit,true);c.step();
  assert.equal(c.r[20],0x5a);assert.equal(c.eeprom[3],255);assert.ok(c.transpilation.abi.data>0);
});

test('Flash, EEPROM, compiler, runtime, clock/fuses and compiler policy partition the key',async()=>{
  const store=memoryStore(),a=await make(store),key=a.persistentTranslationCache.key;
  const changedRuntime=Uint8Array.from([...runtimeBytes,0,2,1,120]); // Empty custom section named x.
  const eeprom=new Uint8Array(64).fill(255);eeprom[0]=0;
  for(const extra of [
    {flash:sequential([avr.ldi(20,0xa5)])},{eeprom},
    {compilerIdentity:(AVR_CACHE_COMPILER_ID[0]==='0'?'1':'0')+AVR_CACHE_COMPILER_ID.slice(1)},
    {runtimeBytes:changedRuntime},{options:{fuseLow:0x6a}},{options:{optimizeFlags:false}},
    {options:{maxBlockInstructions:2}},{options:{fastIdle:false}},{options:{incrementalCompilation:true}},
    {options:{oscillatorHz:1000000,osccalHz:table(),fuseLow:0x72,resumable:true}},
  ]){
    const c=await make(store,extra);assert.equal(c.persistentTranslationCache.hit,false);
    assert.equal(c.persistentTranslationCache.stored,true);assert.notEqual(c.persistentTranslationCache.key,key);
  }
  assert.equal((await make(store)).persistentTranslationCache.hit,true);
});

test('resumable physical and CLKI packages retain exact policy and clock inputs',async()=>{
  for(const options of [
    {oscillatorHz:1000000,osccalHz:table(),fuseLow:0x72,resumable:true,optimizeFlags:false,optimizePhaseLocals:true,boundedRegions:true},
    {resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}},
  ]){
    const store=memoryStore(),a=await make(store,{options}),b=await make(store,{options});
    assert.equal(b.persistentTranslationCache.hit,true);assert.deepEqual(b.transpilation,a.transpilation);
    if(options.clkiProfile){
      for(const c of [a,b])c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,transitionCount:100n,knownUntilPs:50000000n});
      for(const c of [a,b])c.runUntilPs(3500001n);
    }else for(const c of [a,b])c.runUntilPs(3500001n);
    same(a,b);assert.equal(b.r[20],0x5a);
  }
});

test('corruption and stale executable/recipe records are deleted and rebuilt',async()=>{
  for(const mutate of [
    ()=>'{broken',
    r=>({...r,metadata:'{broken'}),
    r=>{const m=JSON.parse(r.metadata);m.recipe.compilerIdentity='0'.repeat(64);r.metadata=JSON.stringify(m);return r;},
    r=>{r.bytes[0]^=1;return r;},
    r=>{const m=JSON.parse(r.metadata);m.recipe.configuration.fuseLow^=16;r.metadata=JSON.stringify(m);return r;},
    r=>({...r,bytes:new Uint8Array(16*1024*1024+1)}),
  ]){
    const store=memoryStore(),a=await make(store),key=a.persistentTranslationCache.key;
    store.rows.set(key,mutate(store.rows.get(key)));const b=await make(store);
    assert.equal(b.persistentTranslationCache.status,'repaired');assert.equal(b.persistentTranslationCache.stored,true);
    b.step();assert.equal(b.r[20],0x5a);assert.equal((await make(store)).persistentTranslationCache.hit,true);
  }
});

test('valid WASM for the wrong Flash or compiler policy cannot pass validation',async()=>{
  for(const extra of [{flash:sequential([avr.ldi(20,0x33)])},{options:{optimizeFlags:false}}]){
    const store=memoryStore(),a=await make(store),key=a.persistentTranslationCache.key;
    const other=await make(memoryStore(),extra),record=store.rows.get(key),metadata=JSON.parse(record.metadata);
    record.bytes=new Uint8Array(other.transpiledBytes);
    metadata.wasmSha256=Buffer.from(await crypto.subtle.digest('SHA-256',record.bytes)).toString('hex');
    record.metadata=JSON.stringify(metadata);store.rows.set(key,record);
    const b=await make(store);assert.equal(b.persistentTranslationCache.status,'repaired');b.step();assert.equal(b.r[20],0x5a);
  }
});

test('audio preflight rejects invalid inputs before parsing firmware or consulting storage',async()=>{
  const entry={device:'attiny13a',cpuHz:9600000,pwmHz:37500,flashHex:'broken'};
  await assert.rejects(createDeviceRenderer(entry,0),/Invalid audio sample rate/);
  await assert.rejects(createDeviceRenderer(entry,48000,{volume:2}),/Invalid audio configuration/);
  await assert.rejects(createDeviceRenderer({...entry,audioChannels:3},48000),/Unsupported audio channel count/);
});

test('storage failures and explicit bypass retain CPU behavior and real configuration errors',async()=>{
  for(const store of [null,{get(){throw Error('denied');}},
    {get:()=>null,put(){throw Error('quota');}}, {get:()=>null,put:()=>false}]){
    const c=await make(store);assert.equal(c.persistentTranslationCache.hit,false);c.step();assert.equal(c.r[20],0x5a);
  }
  const store=memoryStore(),c=await make(store,{options:{cacheTranslation:false}});
  assert.equal(c.persistentTranslationCache.status,'disabled');assert.equal(store.reads,0);
  await assert.rejects(make(store,{options:{fuseHigh:0xf7}}),/DWEN unprogrammed/);
});

test('Buffer and option mutations during async lookup cannot change the captured inputs',async()=>{
  const store=memoryStore();let release;
  const paused={...store,async get(key){await new Promise(resolve=>{release=resolve;});return store.get(key);}};
  const bytes=Buffer.from(image),ee=Buffer.alloc(64,255),runtime=Buffer.from(runtimeBytes);
  const options={oscillatorHz:1000000,osccalHz:table(),fuseLow:0x72,resumable:true};
  const promise=make(paused,{flash:bytes,eeprom:ee,runtimeBytes:runtime,options});
  // The first cryptographic awaits are pending here; inputs must already be copied.
  bytes.fill(0);ee.fill(0);runtime.fill(0);options.osccalHz[0]=0;
  while(!release)await new Promise(resolve=>setImmediate(resolve));release();
  const c=await promise;c.step();assert.equal(c.r[20],0x5a);assert.equal(c.eeprom[0],255);
  assert.equal(c.state().oscillatorHz,1000000);
});

for(const incrementalCompilation of [false,true])for(const clock of ['compatible','physical','clki'])test(`a persistent ${clock} hit retranslates real self-programmed Flash before execution, incremental${incrementalCompilation}`,async()=>{
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)];
  const target=0x100,newWords=[avr.ldi(20,0x5a)[0],0xcfff];
  const words=[...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of newWords.entries())words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,
    ...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8);
  words.push(avr.rjmp(words.length,target/2)[0]);
  const rom=segments({instructions:[words]},{at:target/2,instructions:[avr.ldi(20,0x11),[0xcfff]]});
  const options={fuseHigh:0xef,spmCommandCycles:4,incrementalCompilation,...(clock==='physical'?{
    oscillatorHz:1000000,osccalHz:table(),fuseLow:0x72,resumable:true,nvmClockProfile:1,nvmCalibrationReferenceHz:1000000,
  }:clock==='clki'?{resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1},
    nvmClockProfile:1,nvmCalibrationReferenceHz:1000000}:{})},store=memoryStore();
  await make(store,{flash:rom,options});const c=await make(store,{flash:rom,options}),original=c._translatedModule;
  assert.equal(c.persistentTranslationCache.hit,true);
  if(clock==='clki')c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,
    transitionCount:40000n,knownUntilPs:20000000000n});
  if(clock==='compatible')c.runUntil(200000n);
  else if(clock==='physical')c.runUntilPs(20000000000n);
  else{
    // Retain and drain the complete CLKI pin history in bounded chunks; do not
    // hide a trace overflow by disabling observation during the flash stall.
    for(let at=200000000n;at<=20000000000n;at+=200000000n){c.runUntilPs(at);c.drainPinsPs();}
  }
  assert.equal(c.r[20],0x5a);assert.notEqual(c._translatedModule,original);
  assert.equal(c._exports.avr_device_generation(),2n);assert.equal(c.state().deviceFault,0);
  if(incrementalCompilation)assert.ok(c.incrementalCompilation.reusedModules>0,'SPM selected the regional compiler after loading a portable cache hit');
  const reset=await make(store,{flash:rom,options});assert.equal(reset.persistentTranslationCache.hit,true);
  assert.equal(reset.rom[target],0x41,'The original immutable image, not another chip\'s modified Flash');
});

test('IndexedDB admission and open/blocked timeouts fail without hanging construction',async()=>{
  assert.equal(createIndexedDBTranslationStore({indexedDB:null}),null);
  assert.throws(()=>createIndexedDBTranslationStore({indexedDB:{},maxEntries:0}),/limits/);
  const silent=createIndexedDBTranslationStore({indexedDB:{open:()=>({})},timeoutMs:10});
  const c=await make(silent);assert.equal(c.persistentTranslationCache.status,'unavailable');c.step();assert.equal(c.r[20],0x5a);
  const blocked=createIndexedDBTranslationStore({indexedDB:{open(){const r={};queueMicrotask(()=>r.onblocked());return r;}},timeoutMs:20});
  const d=await make(blocked);assert.equal(d.persistentTranslationCache.status,'unavailable');await blocked.close();
});
