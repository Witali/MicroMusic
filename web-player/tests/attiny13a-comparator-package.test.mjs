import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {createPackage,decodePackage,packageConfiguration,PACKAGE_VERSION} from '../lib/attiny13a-package.js';
import {createCachedDeviceCore} from '../lib/avr-persistent-cache.js';

const image=Uint8Array.of(0xff,0xcf),runtime=getRuntimeBytes();
const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
const physical={resumable:true,osccalHz};
const profile={domain:'physical-ns-v1',propagationNs:37,bandgapStartupNs:83};
const plain=new ATtiny13A(image),phased=new ATtiny13A(image,null,physical);
const input=core=>({flash:image,runtime,translated:core.transpiledBytes,manifest:core.transpilation});
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
const hash=value=>createHash('sha256').update(value).digest('hex');
function reseal(pkg){const {integrity,...payload}=pkg;pkg.integrity={algorithm:'SHA-256',sha256:hash(canonical(payload))};return pkg;}

// Alter only valid export descriptors to test the package's capability boundary.
function changeComparatorExport(bytes,{remove=false,wrongSignature=false}={}){
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
    const name='avr_device_configure_comparator',donor=entries.find(e=>e.name==='avr_reset');
    const changed=entries.filter(e=>!remove||e.name!==name);
    if(wrongSignature){const target=changed.find(e=>e.name===name);assert.ok(target,'Current runtime must expose comparator configuration');target.index=donor.index;}
    const body=[...u32(changed.length)];
    for(const e of changed){const name=encoder.encode(e.name);body.push(...u32(name.length),...name,e.kind,...u32(e.index));}
    const result=Uint8Array.from([...bytes.subarray(0,start),7,...u32(body.length),...body,...bytes.subarray(end)]);
    assert.equal(WebAssembly.validate(result),true);return result;
  }
  assert.fail('Missing runtime export section');
}

test('v6 package preserves explicit physical comparator configuration and reconstruction',async()=>{
  assert.equal(PACKAGE_VERSION,6);
  const external={resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
  for(const clock of [physical,external]){
    const configuration={...clock,comparatorTimingProfile:profile};
    const pkg=await createPackage({...input(phased),configuration});
    const decoded=await decodePackage(pkg);
    assert.equal(pkg.version,6);assert.deepEqual(decoded.options.comparatorTimingProfile,profile);
    assert.notEqual(decoded.options.comparatorTimingProfile,decoded.configuration.comparatorTimingProfile);
    const restored=await ATtiny13A.fromPackage(pkg);
    assert.deepEqual(restored._translationOptions.comparatorTimingProfile,profile);
    if(clock.clkiProfile)assert.equal(restored.injectClkiPs({edges:[],knownUntilPs:1000000n}),true);
    restored.runUntilPs(1000000n);assert.equal(restored.state().timePs,1000000n);
    decoded.options.comparatorTimingProfile.propagationNs=999;
    assert.equal(decoded.configuration.comparatorTimingProfile.propagationNs,37);
  }
});

test('v6 null profile does not require the comparator capability export',async()=>{
  const oldRuntime=changeComparatorExport(runtime,{remove:true});
  const pkg=await createPackage({...input(plain),runtime:oldRuntime});
  assert.equal(pkg.configuration.comparatorTimingProfile,null);
  const c=await ATtiny13A.fromPackage(pkg);c.run(2);assert.equal(c.state().deviceFault,0);
});

for(const kind of ['missing','wrong-signature'])test('package rejects '+kind+' comparator capability before instantiation',async()=>{
  const changed=changeComparatorExport(runtime,{remove:kind==='missing',wrongSignature:kind==='wrong-signature'});
  const configuration={...physical,comparatorTimingProfile:profile};
  const original=WebAssembly.Instance;
  try{
    WebAssembly.Instance=class{constructor(){assert.fail('Invalid package reached instantiation');}};
    await assert.rejects(createPackage({...input(phased),runtime:changed,configuration}),/runtime export mismatch: avr_device_configure_comparator/);
    const pkg=await createPackage({...input(phased),configuration});
    pkg.assets.runtime={encoding:'base64',bytes:changed.length,sha256:hash(changed),data:Buffer.from(changed).toString('base64')};
    await assert.rejects(decodePackage(reseal(pkg)),/runtime export mismatch: avr_device_configure_comparator/);
  }finally{WebAssembly.Instance=original;}
});

test('resealed v6 profiles cannot bypass physical/resumable or legacy-unit validation',async()=>{
  const original=await createPackage({...input(phased),configuration:{...physical,comparatorTimingProfile:profile}});
  for(const patch of [{resumable:false},{osccalHz:null},{comparatorPropagationHalf:1},{bandgapStartupHalf:1},
    {comparatorTimingProfile:{domain:profile.domain,propagationNs:0}},
    {comparatorTimingProfile:{...profile,extra:0}},
    {comparatorTimingProfile:{...profile,bandgapStartupNs:0x100000000}}]){
    const pkg=structuredClone(original);Object.assign(pkg.configuration,patch);
    await assert.rejects(decodePackage(reseal(pkg)),/comparatorTimingProfile|physical time/);
  }
  const missing=structuredClone(original);delete missing.configuration.comparatorTimingProfile;
  await assert.rejects(decodePackage(reseal(missing)),/configuration fields/);
});

test('historical v1-v5 configuration schemas remain exact and reject the later comparator field',async()=>{
  const original=await createPackage(input(plain));
  const introduced={osccalHz:2,nvmClockProfile:2,nvmCalibrationReferenceHz:2,powerResetProfile:3,
    resetInputProfile:4,resumable:5,clkiProfile:5,comparatorTimingProfile:6};
  for(let version=1;version<=5;version++){
    const old=structuredClone(original);old.version=version;
    for(const [name,since] of Object.entries(introduced))if(version<since)delete old.configuration[name];
    const decoded=await decodePackage(reseal(old));assert.equal(decoded.options.comparatorTimingProfile,undefined);
    for(const value of [null,profile]){
      const bad=structuredClone(old);bad.configuration.comparatorTimingProfile=value;
      await assert.rejects(decodePackage(reseal(bad)),/unknown configuration comparatorTimingProfile/);
    }
  }
});

test('persistent cache distinguishes physical comparator delays and restores their configuration',async()=>{
  const rows=new Map(),store={get:key=>structuredClone(rows.get(key)??null),
    put(key,value){rows.set(key,structuredClone(value));return true;},delete:key=>rows.delete(key)};
  const make=timing=>createCachedDeviceCore({Core:ATtiny13A,flash:image,runtimeBytes:runtime,store,
    options:{...physical,comparatorTimingProfile:timing}});
  const first=await make(profile),hit=await make({...profile});
  assert.equal(first.persistentTranslationCache.stored,true);assert.equal(hit.persistentTranslationCache.hit,true);
  assert.deepEqual(hit._translationOptions.comparatorTimingProfile,profile);
  for(const changed of [{...profile,propagationNs:38},{...profile,bandgapStartupNs:84},null]){
    const c=await make(changed);assert.equal(c.persistentTranslationCache.hit,false);
    assert.notEqual(c.persistentTranslationCache.key,first.persistentTranslationCache.key);
  }
  const normalized=packageConfiguration({...physical,comparatorTimingProfile:profile});
  assert.deepEqual(normalized.comparatorTimingProfile,profile);assert.notEqual(normalized.comparatorTimingProfile,profile);
});
