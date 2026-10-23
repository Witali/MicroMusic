// Actual100-export device runtime; no mocked clock, queue or CPU model.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage,decodePackage} from '../lib/attiny13a-package.js';
import {CLKI_PHASE_POLICY} from '../lib/devices/attiny13a-clki-profile.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const profile={phasePolicy:CLKI_PHASE_POLICY,initialLevel:0};
const options={resumable:true,fuseLow:0x78,clkiProfile:profile};
const binary=sequential([avr.ldi(16,42)]);
const make=(patch={})=>new ATtiny13A(binary,null,{...options,...patch});
const alternating=count=>Array.from({length:count},(_,n)=>({timePs:BigInt(n+1)*2n,level:(n+1)&1}));
const stage=c=>new Uint8Array(c._exports.memory.buffer,c._exports.avr_device_clki_buffer(),512*16);

test('CLKI selects physical time without an RC table and exposes complete source state',()=>{
  const c=make();assert.equal(c.state().timePs,0n);assert.equal(c.state().deviceFault,0);
  assert.equal(c.transpilation.executionMode,'resumable-v1');
  assert.deepEqual(c.state().clki,{horizonPs:0n,level:0,queued:0,free:512,periodicRemaining:0n,status:'COMPLETE',aligned:false,startupCK:0n});
  for(const patch of [{resumable:false},{fuseLow:0x7a},{clkiProfile:{}},
    {clkiProfile:{...profile,phasePolicy:'unspecified'}},{clkiProfile:{...profile,initialLevel:true}}])
    assert.throws(()=>make(patch),/clkiProfile/);
});

test('optional ideal-digital qualification is explicit and cannot silently use an unsupported runtime',()=>{
  const clkiProfile={...profile,electricalValidation:'datasheet-ideal-v1'};
  const e=new WebAssembly.Instance(runtimeModule).exports;
  if(e.avr_device_configure_clki(2,1))assert.equal(make({clkiProfile}).state().deviceFault,0);
  else assert.throws(()=>make({clkiProfile}),/electrical validation unavailable/);
  for(const electricalValidation of [undefined,null,false,1,'measured'])
    assert.throws(()=>make({clkiProfile:{...profile,electricalValidation}}),/clkiProfile electricalValidation/);
});

test('the whole batch is validated before staging or native queue mutation',()=>{
  const c=make();stage(c).fill(0xa5);const before=stage(c).slice(),state=c.state();
  for(const batch of [
    {edges:[{timePs:1n,level:1},{timePs:2,level:0}],knownUntilPs:3n},
    {edges:[{timePs:1n,level:1},{timePs:1n,level:0}],knownUntilPs:3n},
    {edges:[{timePs:1n,level:1},{timePs:2n,level:1}],knownUntilPs:3n},
    {edges:[{timePs:1n,level:1},{timePs:4n,level:0}],knownUntilPs:3n},
    {edges:[{timePs:1n,level:1,extra:true}],knownUntilPs:3n},
    {edges:Object.assign(Array(2),{0:{timePs:1n,level:1}}),knownUntilPs:3n},
    {edges:[],knownUntilPs:0xffffffffffffffffn},
  ]){
    assert.throws(()=>c.injectClkiPs(batch),/CLKI|timestamp|Timestamp/);
    assert.deepEqual(stage(c),before);assert.deepEqual(c.state(),state);
  }
  assert.throws(()=>c.injectClkiPs({edges:[{timePs:1n,level:0}],knownUntilPs:2n}),/CLKI edge level/);
  assert.deepEqual(stage(c),before);assert.deepEqual(c.state(),state,'Alternating-tail rejection is nonsticky and atomic');
});

test('staging uses exact uint64 ps and zero-filled16-byte edge records',()=>{
  const c=make(),at=9007199254741115n;
  assert.equal(c.injectClkiPs({edges:[{timePs:at,level:1}],knownUntilPs:at+10n}),true);
  const view=new DataView(stage(c).buffer,stage(c).byteOffset,16);
  assert.equal(view.getBigUint64(0,true),at);assert.equal(view.getUint8(8),1);
  assert.ok(stage(c).subarray(9,16).every(v=>v===0));
  assert.equal(c.state().clki.horizonPs,at+10n);assert.equal(c.state().clki.queued,1);
});

test('backpressure rejects an entire batch/horizon and the same batch can be retried after draining',()=>{
  const c=make();assert.equal(c.injectClkiPs({edges:alternating(512),knownUntilPs:1024n}),true);
  const before=c.state(),next={edges:[{timePs:1025n,level:1}],knownUntilPs:2048n};
  assert.equal(c.injectClkiPs(next),false);assert.deepEqual(c.state(),before);
  c.runUntilPs(4n);assert.equal(c.state().clki.free,2);
  assert.equal(c.injectClkiPs(next),true);assert.equal(c.state().clki.horizonPs,2048n);
  assert.equal(c.state().clki.queued,511);assert.equal(c.state().clki.free,1);
});

test('oversized staging batches return backpressure; an empty batch extends a full queue hold',()=>{
  const c=make(),before=c.state();
  assert.equal(c.injectClkiPs({edges:alternating(513),knownUntilPs:1026n}),false);assert.deepEqual(c.state(),before);
  assert.equal(c.injectClkiPs({edges:alternating(512),knownUntilPs:1024n}),true);
  assert.equal(c.injectClkiPs({edges:[],knownUntilPs:2048n}),true);
  assert.equal(c.state().clki.horizonPs,2048n);assert.equal(c.state().clki.free,0);
  assert.throws(()=>c.injectClkiPs({edges:[],knownUntilPs:2047n}),/horizon/);
});

test('unknown horizon returns WAIT_INPUT; a known hold returns WAIT_CLOCK and later edges resume',()=>{
  const c=make();assert.equal(c.runUntilPs(1000000n),0);
  assert.equal(c.state().timePs,0n);assert.equal(c.state().clki.status,'WAIT_INPUT');
  assert.equal(c.injectClkiPs({edges:[{timePs:100000n,level:1},{timePs:150000n,level:0},
    {timePs:200000n,level:1}],knownUntilPs:1000000n}),true);
  assert.equal(c.runUntilPs(1000000n),1);assert.equal(c.r[16],42);
  assert.equal(c.state().timePs,1000000n);assert.equal(c.state().clki.status,'WAIT_CLOCK');
  assert.equal(c.runUntilPs(2000000n),0);assert.equal(c.state().timePs,1000000n);
  assert.equal(c.state().clki.status,'WAIT_INPUT');assert.equal(c.state().deviceFault,0);
});

test('unbounded CPU entrypoints, PB3 injection and host EEPROM transfers reject before effects',()=>{
  const c=make(),before=c.state();
  for(const operation of [()=>c.step(),()=>c.run(1),()=>c.clock(1),()=>c.interrupt(),()=>c.runBlock(100)])
    assert.throws(operation,/Use runUntilPs with bounded CLKI input/);
  for(const operation of [()=>c.injectPinsPs({at:1n,mask:8,levels:8}),
    ()=>c.setAnalogPs({at:1n,pin:3,microvolts:1000000})])assert.throws(operation,/PB3.*CLKI/);
  assert.deepEqual(c.state(),before);
  c.writeIO(IO.EEARL,4);c.writeIO(IO.EEDR,42);c.writeIO(IO.EECR,4);
  const armed=c.data.slice();
  for(const value of [1,2])assert.throws(()=>c.writeIO(IO.EECR,value),/EEPROM transfers/);
  assert.deepEqual(c.data,armed);assert.equal(c.eeprom[4],255);assert.equal(c.state().timePs,0n);
});

test('capture preflights its entire interval, preserving CPU/audio state on insufficient input',()=>{
  const c=make();c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);const before=c.state();
  assert.throws(()=>c.capturePhysical(2,48000),/CLKI WAIT_INPUT/);assert.deepEqual(c.state(),before);
  assert.equal(c._physicalRate,0);assert.equal(c._physicalFrames,0n);
  c.injectClkiPs({edges:[],knownUntilPs:20833333n});
  assert.deepEqual(c.capturePhysical(1,48000),Float32Array.of(1));
  const snapshot=c.state(),frames=c._physicalFrames;
  assert.throws(()=>c.capturePhysical(2,48000),/CLKI WAIT_INPUT/);
  assert.deepEqual(c.state(),snapshot);assert.equal(c._physicalFrames,frames);
  c.injectClkiPs({edges:[],knownUntilPs:62500000n});
  assert.deepEqual(c.capturePhysical(2,48000),Float32Array.of(1,1));
  assert.equal(c.state().timePs,62500000n);assert.equal(c._physicalFrames,3n);assert.equal(c.r[16],0);
});

test('explicit power/RESET profiles accept CLKI physical time without a dummy OSCCAL table',()=>{
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const resetInputProfile={assertThresholdPpm:400000,releaseThresholdPpm:600000,
    assertQualificationNs:50,releaseQualificationNs:30,assertPropagationNs:20,releasePropagationNs:10};
  const c=make({powerResetProfile,resetInputProfile});
  assert.equal(c.state().powerResetEnabled,true);assert.equal(c.state().resetInputEnabled,true);
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().timePs,0n);
});

test('package v5 restores the digital source profile and supplied continuation, but no queued trace',async()=>{
  const original=make();original.injectClkiPs({edges:[{timePs:10n,level:1}],knownUntilPs:20n});
  const pkg=await createPackage({flash:binary,configuration:options,translated:original.transpiledBytes,
    runtime:new Uint8Array(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url)))});
  const decoded=await decodePackage(pkg),loaded=await ATtiny13A.fromPackage(pkg);
  assert.equal(pkg.version,5);assert.equal(decoded.configuration.osccalHz,null);
  assert.deepEqual(decoded.options.clkiProfile,{...profile,electricalValidation:'none'});assert.equal(decoded.options.resumable,true);
  assert.equal(loaded.state().clki.horizonPs,0n);assert.equal(loaded.state().clki.queued,0);
  assert.deepEqual(loaded.transpiledBytes,original.transpiledBytes);
  loaded.injectClkiPs({edges:alternating(8),knownUntilPs:1000n});
  assert.equal(loaded.runUntilPs(1000n),2);assert.equal(loaded.r[16],42);assert.equal(loaded.state().deviceFault,0);
});
