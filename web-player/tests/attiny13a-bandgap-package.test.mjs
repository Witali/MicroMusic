import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {createPackage,decodePackage,PACKAGE_VERSION} from '../lib/attiny13a-package.js';
import {createCachedDeviceCore} from '../lib/avr-persistent-cache.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

const image=Uint8Array.of(0xff,0xcf),runtime=getRuntimeBytes();
const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
const comparatorTimingProfile={domain:'physical-ns-v1',propagationNs:37,bandgapStartupNs:0};
const physical={resumable:true,osccalHz,comparatorTimingProfile};
const bandgapProfile={domain:'physical-ns-v1',startupNs:37};
const plain=new ATtiny13A(image),phased=new ATtiny13A(image,null,physical);
const input=core=>({flash:image,runtime,translated:core.transpiledBytes,manifest:core.transpilation});
const hash=value=>createHash('sha256').update(value).digest('hex');
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
function reseal(pkg){const {integrity,...payload}=pkg;pkg.integrity={algorithm:'SHA-256',sha256:hash(canonical(payload))};return pkg;}
const capabilities=['avr_device_configure_bandgap','avr_device_bandgap_enabled','avr_device_bandgap_active',
  'avr_device_bandgap_powered','avr_device_bandgap_ready','avr_device_bandgap_owners','avr_device_bandgap_deadline_ps'];

// Change only valid export descriptors; retain the original WASM code and memory.
function editExport(bytes,name,remove=false){
  let at=8;
  const read=()=>{let value=0,shift=0,b;do{b=bytes[at++];value+=(b&127)*2**shift;shift+=7;}while(b&128);return value;};
  const u32=value=>{const out=[];do{const b=value&127;value=Math.floor(value/128);out.push(b|(value?128:0));}while(value);return out;};
  const encoder=new TextEncoder(),decoder=new TextDecoder();
  while(at<bytes.length){
    const start=at,id=bytes[at++],length=read(),end=at+length;
    if(id!==7){at=end;continue;}
    const count=read(),entries=[];
    for(let n=0;n<count;n++){
      const length=read(),name=decoder.decode(bytes.subarray(at,at+length));at+=length;
      entries.push({name,kind:bytes[at++],index:read()});
    }
    const changed=entries.filter(e=>!remove||e.name!==name);
    if(!remove){
      const target=changed.find(e=>e.name===name);assert.ok(target,'Selected capability must exist: '+name);
      const donor=name==='avr_device_configure_bandgap'?'avr_reset':
        name==='avr_device_bandgap_deadline_ps'?'avr_device_physical_mode':'avr_device_time_ps';
      target.index=changed.find(e=>e.name===donor).index;
    }
    const body=[...u32(changed.length)];
    for(const e of changed){const name=encoder.encode(e.name);body.push(...u32(name.length),...name,e.kind,...u32(e.index));}
    const result=Uint8Array.from([...bytes.subarray(0,start),7,...u32(body.length),...body,...bytes.subarray(end)]);
    assert.equal(WebAssembly.validate(result),true);return result;
  }
  assert.fail('Missing runtime export section');
}

test('v7 package preserves explicit shared-reference ownership and reconstruction in either physical source',async()=>{
  assert.equal(PACKAGE_VERSION,7);
  const external={resumable:true,fuseLow:0x70,comparatorTimingProfile,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
  for(const clock of [physical,external]){
    const configuration={...clock,bandgapProfile},pkg=await createPackage({...input(phased),configuration});
    const decoded=await decodePackage(pkg),restored=await ATtiny13A.fromPackage(pkg);
    const direct=new ATtiny13A(image,null,configuration);
    assert.equal(pkg.version,7);assert.deepEqual(decoded.options.bandgapProfile,bandgapProfile);
    assert.notEqual(decoded.options.bandgapProfile,decoded.configuration.bandgapProfile);
    assert.deepEqual(restored._translationOptions.bandgapProfile,bandgapProfile);
    for(const c of [direct,restored]){
      if(clock.clkiProfile)c.injectClkiPs({edges:[],knownUntilPs:1000000n});
      c.writeIO(IO.ACSR,0x40);c.runUntilPs(1000000n);
    }
    assert.deepEqual(restored.state(),direct.state());assert.deepEqual(restored.data,direct.data);
    decoded.options.bandgapProfile.startupNs=99;assert.equal(decoded.configuration.bandgapProfile.startupNs,37);
  }
});

for(const name of capabilities)for(const remove of [true,false])
test(`v7 selected reference rejects ${remove?'missing':'wrong-signature'} ${name} before instantiation`,async()=>{
  const modified=editExport(runtime,name,remove),configuration={...physical,bandgapProfile};
  const original=WebAssembly.Instance;
  try{
    WebAssembly.Instance=class{constructor(){assert.fail('Invalid capability reached instantiation');}};
    const error=new RegExp('runtime export mismatch: '+name);
    await assert.rejects(createPackage({...input(phased),runtime:modified,configuration}),error);
    const pkg=await createPackage({...input(phased),configuration});
    pkg.assets.runtime={encoding:'base64',bytes:modified.length,sha256:hash(modified),data:Buffer.from(modified).toString('base64')};
    await assert.rejects(decodePackage(reseal(pkg)),error);
  }finally{WebAssembly.Instance=original;}
});

test('resealed v7 reference configuration cannot bypass clock or startup ownership constraints',async()=>{
  const original=await createPackage({...input(phased),configuration:{...physical,bandgapProfile}});
  for(const patch of [{resumable:false},{osccalHz:null},{comparatorTimingProfile:null},
    {comparatorTimingProfile:{...comparatorTimingProfile,bandgapStartupNs:1}},{bandgapStartupHalf:1},
    {bandgapProfile:{domain:bandgapProfile.domain}},{bandgapProfile:{...bandgapProfile,extra:0}},
    {bandgapProfile:{...bandgapProfile,startupNs:0x100000000}}]){
    const pkg=structuredClone(original);Object.assign(pkg.configuration,patch);
    await assert.rejects(decodePackage(reseal(pkg)),/bandgapProfile|comparatorTimingProfile|physical time/);
  }
  const missing=structuredClone(original);delete missing.configuration.bandgapProfile;
  await assert.rejects(decodePackage(reseal(missing)),/configuration fields/);
});

test('v7 null reference does not require the shared-reference capability exports',async()=>{
  let legacy=runtime;
  for(const name of capabilities)legacy=editExport(legacy,name,true);
  const pkg=await createPackage({...input(plain),runtime:legacy});
  assert.equal(pkg.configuration.bandgapProfile,null);
  const c=await ATtiny13A.fromPackage(pkg);c.run(2);assert.equal(Object.hasOwn(c.state(),'bandgap'),false);
});

test('v1-v6 schemas retain their original fields and reject a later bandgap profile',async()=>{
  const original=await createPackage(input(plain));
  const introduced={osccalHz:2,nvmClockProfile:2,nvmCalibrationReferenceHz:2,powerResetProfile:3,
    resetInputProfile:4,resumable:5,clkiProfile:5,comparatorTimingProfile:6,bandgapProfile:7};
  for(let version=1;version<=6;version++){
    const old=structuredClone(original);old.version=version;
    for(const [name,since] of Object.entries(introduced))if(version<since)delete old.configuration[name];
    const decoded=await decodePackage(reseal(old));assert.equal(decoded.options.bandgapProfile,undefined);
    for(const value of [null,bandgapProfile]){
      const bad=structuredClone(old);bad.configuration.bandgapProfile=value;
      await assert.rejects(decodePackage(reseal(bad)),/unknown configuration bandgapProfile/);
    }
  }
});

test('genuine committed v6 package retains independent comparator startup with its original runtime',async()=>{
  const fixture=JSON.parse(await readFile(new URL('./fixtures/attiny13a-package-v6-comparator.json',import.meta.url),'utf8'));
  const bytes=gunzipSync(Buffer.from(fixture.data,'base64'));
  assert.equal(bytes.length,fixture.bytes);assert.equal(hash(bytes),fixture.sha256);
  assert.equal(fixture.source.revision,'d9e31cdacaf1f1f06dc8822e6b564030ab33f6a7');
  assert.equal(fixture.source.compilerIdentity,'194347459330b5d07e70fe857431359b05a09d7f89f0ba0aaaa6fd89dd625e50');
  const decoded=await decodePackage(bytes.toString('utf8'));
  assert.equal(decoded.version,6);assert.equal(decoded.options.bandgapProfile,undefined);
  assert.deepEqual(decoded.options.comparatorTimingProfile,{domain:'physical-ns-v1',propagationNs:37,bandgapStartupNs:83});
  assert.equal(decoded.runtime.length,121019);assert.equal(hash(decoded.runtime),fixture.source.nativeSha256);
  assert.equal(fixture.source.nativeSha256,'4183c8b0d0b71e720307d7d8dc7959b4c880ea78ec8286dbcbb719f944a93000');
  const names=WebAssembly.Module.exports(await WebAssembly.compile(decoded.runtime)).map(e=>e.name);
  assert.equal(names.some(name=>capabilities.includes(name)),false);
  const c=await ATtiny13A.fromPackage(bytes.toString('utf8'));
  assert.equal(Object.hasOwn(c.state(),'bandgap'),false);assert.ok(c.eeprom.every(value=>value===255));
  c.writeIO(IO.ACSR,0x40);c.runUntilPs(312499n);assert.equal(c.readIO(IO.ACSR)&0x30,0);
  c.runUntilPs(312500n);assert.equal(c.readIO(IO.ACSR)&0x30,0x30);
  c.runUntilPs(1000000n);assert.equal(c.r[20],42);
  assert.equal(c.readIO(IO.DDRB)&16,16);assert.equal(c.readIO(IO.PORTB)&16,16);
});

test('persistent cache preserves shared-reference profile and distinguishes startup/ownership changes',async()=>{
  const rows=new Map(),store={get:key=>structuredClone(rows.get(key)??null),
    put(key,value){rows.set(key,structuredClone(value));return true;},delete:key=>rows.delete(key)};
  const make=profile=>createCachedDeviceCore({Core:ATtiny13A,flash:image,runtimeBytes:runtime,store,
    options:{...physical,bandgapProfile:profile}});
  const first=await make(bandgapProfile),hit=await make({...bandgapProfile});
  assert.equal(first.persistentTranslationCache.stored,true);assert.equal(hit.persistentTranslationCache.hit,true);
  assert.deepEqual(hit._translationOptions.bandgapProfile,bandgapProfile);
  assert.deepEqual(hit.state(),first.state());
  for(const profile of [{...bandgapProfile,startupNs:38},null]){
    const c=await make(profile);assert.equal(c.persistentTranslationCache.hit,false);
    assert.notEqual(c.persistentTranslationCache.key,first.persistentTranslationCache.key);
    assert.equal(Object.hasOwn(c.state(),'bandgap'),profile!==null);
  }
});
