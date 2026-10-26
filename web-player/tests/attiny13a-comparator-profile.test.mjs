import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {ATtiny13A} from '../lib/attiny13a.js';
import {normalizeComparatorTimingProfile,validateComparatorTimingOptions} from '../lib/devices/attiny13a-comparator-profile.js';
import {packageConfiguration} from '../lib/attiny13a-package.js';

const image=Uint8Array.of(0xff,0xcf); // RJMP .
const fixture={domain:'physical-ns-v1',propagationNs:37,bandgapStartupNs:83};
const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
const physical={resumable:true,osccalHz};

test('comparator profile normalizes exact own fields without mutating caller state',()=>{
  assert.equal(normalizeComparatorTimingProfile(null),null);
  const input=Object.assign(Object.create(null),fixture),normalized=normalizeComparatorTimingProfile(input);
  assert.deepEqual(normalized,fixture);assert.notEqual(normalized,input);
  input.propagationNs=99;assert.equal(normalized.propagationNs,37);
  assert.deepEqual(normalizeComparatorTimingProfile({...fixture,propagationNs:-0,bandgapStartupNs:0xffffffff}),
    {...fixture,propagationNs:0,bandgapStartupNs:0xffffffff});
});

const malformed=[
  ['missing profile',undefined],['array',[]],['scalar',1],['boolean',true],
  ['missing propagation',{domain:'physical-ns-v1',bandgapStartupNs:0}],
  ['missing startup',{domain:'physical-ns-v1',propagationNs:0}],
  ['extra field',{...fixture,unused:0}],['wrong domain',{...fixture,domain:'cpu-half-v1'}],
  ['inherited fields',Object.create(fixture)],
  ['symbol field',{...fixture,[Symbol('extra')]:1}],
  ['hidden extra',Object.defineProperty({...fixture},'extra',{value:1})],
  ['accessor field',{...fixture,get propagationNs(){throw Error('Profile getter must not be called');}}],
];
for(const name of ['propagationNs','bandgapStartupNs'])for(const value of [-1,1.5,NaN,Infinity,0x100000000,'1',null])
  malformed.push([name+' '+String(value),{...fixture,[name]:value}]);
for(const [name,value] of malformed)test('invalid comparator profile: '+name,()=>{
  assert.throws(()=>normalizeComparatorTimingProfile(value),/Invalid comparatorTimingProfile/);
});

test('invalid comparator options fail before constructing a WASM instance',()=>{
  const original=WebAssembly.Instance;
  try{
    WebAssembly.Instance=class{constructor(){assert.fail('Invalid profile reached runtime instantiation');}};
    for(const [name,value] of malformed.filter(([,value])=>value!==undefined))
      assert.throws(()=>new ATtiny13A(image,null,{...physical,comparatorTimingProfile:value}),/comparatorTimingProfile/,name);
    for(const options of [{},{resumable:true},{osccalHz},{...physical,resumable:false},
      {...physical,comparatorPropagationHalf:1},{...physical,bandgapStartupHalf:1}]){
      assert.throws(()=>new ATtiny13A(image,null,{...options,comparatorTimingProfile:fixture}),/comparatorTimingProfile/);
      assert.throws(()=>packageConfiguration({...options,comparatorTimingProfile:fixture}),/comparatorTimingProfile|physical time/);
    }
  }finally{WebAssembly.Instance=original;}
});

test('physical comparator option validation accepts both explicit physical clock sources and ideal zero delays',()=>{
  for(const options of [physical,{resumable:true,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}]){
    assert.doesNotThrow(()=>validateComparatorTimingOptions(fixture,options));
    const configuration=packageConfiguration({...options,...(options.clkiProfile?{fuseLow:0x70}:{}),comparatorTimingProfile:fixture});
    assert.deepEqual(configuration.comparatorTimingProfile,fixture);
  }
  assert.deepEqual(packageConfiguration({...physical,comparatorTimingProfile:{...fixture,propagationNs:0,bandgapStartupNs:0}}).comparatorTimingProfile,
    {...fixture,propagationNs:0,bandgapStartupNs:0});
});

test('historical v1/v3 runtime rejection precedes native reset and guest execution',async()=>{
  for(const version of [1,3]){
    const saved=JSON.parse(await readFile(new URL(`./fixtures/attiny13a-runtime-v${version}.json`,import.meta.url),'utf8'));
    const bytes=gunzipSync(Buffer.from(saved.data,'base64'));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),saved.sha256);
    const runtimeModule=await WebAssembly.compile(bytes),original=WebAssembly.Instance;
    let resets=0;
    try{
      WebAssembly.Instance=class{constructor(module,imports){
        const {exports}=new original(module,imports);
        return {exports:{...exports,avr_reset(...args){resets++;return exports.avr_reset(...args);}}};
      }};
      assert.throws(()=>new ATtiny13A(image,null,{...physical,runtimeModule,comparatorTimingProfile:fixture}),/Runtime has no comparator physical timing profile/);
      assert.equal(resets,0,'Unavailable capability must fail before initializing the virtual chip');
    }finally{WebAssembly.Instance=original;}
  }
});

test('current runtime accepts explicit physical comparator delays with internal and external clocks',()=>{
  const external={resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};
  for(const options of [physical,external])for(const delays of [[0,0],[37,83],[0xffffffff,0xffffffff]]){
    const c=new ATtiny13A(image,null,{...options,comparatorTimingProfile:{domain:fixture.domain,propagationNs:delays[0],bandgapStartupNs:delays[1]}});
    assert.equal(c.state().timePs,0n);assert.equal(c.state().deviceFault,0);
    if(options.clkiProfile)assert.equal(c.injectClkiPs({edges:[],knownUntilPs:1000000n}),true);
    c.runUntilPs(1000000n);assert.equal(c.state().timePs,1000000n);assert.equal(c.state().deviceFault,0);
  }
});

test('null comparator profile preserves legacy half-clock options and output',()=>{
  const options={comparatorPropagationHalf:4,bandgapStartupHalf:8};
  const a=new ATtiny13A(image,null,options),b=new ATtiny13A(image,null,{...options,comparatorTimingProfile:null});
  a.runUntil(2000n);b.runUntil(2000n);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);assert.deepEqual(a.drainPins(),b.drainPins());
  assert.deepEqual(a.transpiledBytes,b.transpiledBytes);
});
