import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {normalizeBandgapProfile,validateBandgapOptions} from '../lib/devices/attiny13a-bandgap-profile.js';
import {packageConfiguration} from '../lib/attiny13a-package.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

const image=Uint8Array.of(0xff,0xcf),profile={domain:'physical-ns-v1',startupNs:37};
const comparatorTimingProfile={domain:'physical-ns-v1',propagationNs:37,bandgapStartupNs:0};
const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
const physical={resumable:true,osccalHz,comparatorTimingProfile};
const capabilities=['avr_device_configure_bandgap','avr_device_bandgap_enabled','avr_device_bandgap_active',
  'avr_device_bandgap_powered','avr_device_bandgap_ready','avr_device_bandgap_owners','avr_device_bandgap_deadline_ps'];
const max=0xffffffffffffffffn;

test('bandgap profile normalizes exact own data fields and explicit uint32 endpoints',()=>{
  assert.equal(normalizeBandgapProfile(null),null);
  const input=Object.assign(Object.create(null),profile),normalized=normalizeBandgapProfile(input);
  assert.deepEqual(normalized,profile);assert.notEqual(normalized,input);
  input.startupNs=99;assert.equal(normalized.startupNs,37);
  for(const startupNs of [0,-0,0xffffffff])assert.deepEqual(normalizeBandgapProfile({...profile,startupNs}),
    {...profile,startupNs:startupNs===0?0:startupNs});
});

const malformed=[['missing profile',undefined],['array',[]],['scalar',1],['boolean',false],
  ['missing startup',{domain:profile.domain}],['missing domain',{startupNs:37}],
  ['wrong domain',{...profile,domain:'cpu-half-v1'}],['extra field',{...profile,extra:0}],
  ['inherited fields',Object.create(profile)],['symbol field',{...profile,[Symbol('extra')]:1}],
  ['hidden extra',Object.defineProperty({...profile},'extra',{value:1})],
  ['accessor field',{domain:profile.domain,get startupNs(){throw Error('Profile getter must not be called');}}]];
for(const value of [-1,1.5,NaN,Infinity,0x100000000,'1',null])malformed.push(['startup '+String(value),{...profile,startupNs:value}]);
for(const [name,value] of malformed)test('invalid bandgap profile: '+name,()=>{
  assert.throws(()=>normalizeBandgapProfile(value),/Invalid bandgapProfile/);
});

test('invalid bandgap source/startup ownership fails before WASM instantiation',()=>{
  const original=WebAssembly.Instance;
  try{
    WebAssembly.Instance=class{constructor(){assert.fail('Invalid profile reached instantiation');}};
    for(const [,value] of malformed.filter(([,value])=>value!==undefined))
      assert.throws(()=>new ATtiny13A(image,null,{...physical,bandgapProfile:value}),/bandgapProfile/);
    for(const options of [{},{resumable:true},{...physical,resumable:false},{...physical,osccalHz:null},
      {...physical,comparatorTimingProfile:null},
      {...physical,comparatorTimingProfile:{...comparatorTimingProfile,bandgapStartupNs:1}},
      {...physical,bandgapStartupHalf:1}]){
      assert.throws(()=>new ATtiny13A(image,null,{...options,bandgapProfile:profile}),/bandgapProfile|comparatorTimingProfile/);
      assert.throws(()=>packageConfiguration({...options,bandgapProfile:profile}),/bandgapProfile|comparatorTimingProfile|physical time/);
    }
  }finally{WebAssembly.Instance=original;}
});

test('bandgap option validation accepts both explicit physical sources with one startup owner',()=>{
  const external={resumable:true,comparatorTimingProfile,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1},fuseLow:0x70};
  for(const options of [physical,external]){
    assert.doesNotThrow(()=>validateBandgapOptions(profile,options));
    assert.deepEqual(packageConfiguration({...options,bandgapProfile:profile}).bandgapProfile,profile);
  }
});

test('genuine historical runtimes reject a selected shared reference before native reset',async()=>{
  const modules=[];
  for(const version of [1,3]){
    const fixture=JSON.parse(await readFile(new URL(`./fixtures/attiny13a-runtime-v${version}.json`,import.meta.url),'utf8'));
    const bytes=gunzipSync(Buffer.from(fixture.data,'base64'));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),fixture.sha256);
    modules.push(await WebAssembly.compile(bytes));
  }
  const saved=JSON.parse(await readFile(new URL('./fixtures/attiny13a-package-v6-comparator.json',import.meta.url),'utf8'));
  const bytes=gunzipSync(Buffer.from(saved.data,'base64'));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),saved.sha256);
  const pkg=JSON.parse(bytes);modules.push(await WebAssembly.compile(Buffer.from(pkg.assets.runtime.data,'base64')));
  for(const module of modules){
    const original=WebAssembly.Instance;let resets=0;
    try{
      WebAssembly.Instance=class{constructor(module,imports){const {exports}=new original(module,imports);
        return {exports:{...exports,avr_reset(...args){resets++;return exports.avr_reset(...args);}}};
      }};
      assert.throws(()=>new ATtiny13A(image,null,{...physical,bandgapProfile:profile,runtimeModule:module}),/Runtime has no shared bandgap profile/);
      assert.equal(resets,0);
    }finally{WebAssembly.Instance=original;}
  }
});

test('runtime requires every shared-reference observer before reset',()=>{
  const original=WebAssembly.Instance;
  const exports=new original(runtimeModule).exports;
  for(const name of capabilities)assert.equal(typeof exports[name],'function',name);
  for(const omitted of capabilities){
    let resets=0;
    try{
      WebAssembly.Instance=class{constructor(module,imports){const {exports}=new original(module,imports),copy={...exports};
        delete copy[omitted];copy.avr_reset=(...args)=>{resets++;return exports.avr_reset(...args);};
        return {exports:copy};
      }};
      assert.throws(()=>new ATtiny13A(image,null,{...physical,bandgapProfile:profile}),/Runtime has no shared bandgap profile/);
      assert.equal(resets,0);
    }finally{WebAssembly.Instance=original;}
  }
});

test('enabled ownerless bandgap state is explicit; reference acquisition uses the physical startup',()=>{
  const external={resumable:true,fuseLow:0x70,comparatorTimingProfile,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
  for(const options of [physical,external])for(const startupNs of [0,37,0xffffffff]){
    const c=new ATtiny13A(image,null,{...options,bandgapProfile:{...profile,startupNs}});
    const initial=c.state().bandgap;
    assert.deepEqual(Object.keys(initial).sort(),['active','deadlinePs','owners','powered','ready']);
    assert.equal(initial.owners,0);assert.equal(initial.active,false);assert.equal(initial.ready,false);
    assert.equal(initial.deadlinePs,max);assert.equal(c._exports.avr_device_bandgap_enabled(),1);
    assert.equal(typeof initial.powered,'boolean');
    if(options.clkiProfile)c.injectClkiPs({edges:[],knownUntilPs:1000000n});
    c.writeIO(IO.ACSR,0x40);
    assert.equal(c.state().bandgap.active,true);assert.ok(c.state().bandgap.owners>0);
    assert.equal(c.state().bandgap.ready,startupNs===0);
    if(startupNs){
      assert.equal(c.state().bandgap.deadlinePs,BigInt(startupNs)*1000n);
      if(startupNs===37){
        c.runUntilPs(36999n);assert.equal(c.state().bandgap.ready,false);
        c.runUntilPs(37000n);assert.equal(c.state().bandgap.ready,true);
      }
    }
    c.writeIO(IO.ACSR,0);
    assert.equal(c.state().bandgap.owners,0);assert.equal(c.state().bandgap.active,false);
    assert.equal(c.state().bandgap.ready,false);assert.equal(c.state().bandgap.deadlinePs,max);
  }
});

test('null shared profile preserves independent v6 comparator startup and public snapshot shape',()=>{
  const options={...physical,comparatorTimingProfile:{...comparatorTimingProfile,bandgapStartupNs:83}};
  const a=new ATtiny13A(image,null,options),b=new ATtiny13A(image,null,{...options,bandgapProfile:null});
  for(const c of [a,b]){c.writeIO(IO.ACSR,0x40);c.runUntilPs(1000000n);assert.equal(Object.hasOwn(c.state(),'bandgap'),false);}
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.deepEqual(a.transpiledBytes,b.transpiledBytes);
});
