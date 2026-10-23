import {test} from 'node:test';
import assert from 'node:assert/strict';
import {deviceProfile,DEFAULT_DEVICE} from '../lib/devices/profiles.js';
import {AT13_DATA,AT13_MEMORY,AT13_CONST} from '../lib/attiny13a-registers.js';
import {transpileAVR,runtimeABI} from '../lib/avr-transpiler.js';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
const image=sequential([avr.ldi(16,42),avr.inc(16)]);

test('ATtiny13A target geometry is an immutable device profile derived from manufacturer definitions',()=>{
  const p=deviceProfile();assert.equal(p.name,DEFAULT_DEVICE);assert.ok(Object.isFrozen(p));assert.ok(Object.isFrozen(p.legacy));
  assert.equal(p.flashBytes,AT13_MEMORY.FLASHEND+1);assert.equal(p.flashWords,p.flashBytes/2);
  assert.equal(p.ramStart,AT13_MEMORY.RAMSTART);assert.equal(p.ramEnd,AT13_MEMORY.RAMEND);
  assert.equal(p.sreg,AT13_DATA.SREG);assert.equal(p.stackPointer,AT13_DATA.SPL);assert.equal(p.ioStart,AT13_CONST.IO_DATA_OFFSET);
});

test('default and explicit device selection emit identical firmware code and execute through its runtime',()=>{
  const a=transpileAVR(image,abi),b=transpileAVR(image,abi,{device:'ATtiny13A'});
  assert.deepEqual(a.bytes,b.bytes);assert.deepEqual(a.manifest,b.manifest);
  const c=new ATtiny13A(image,null,{device:'ATtiny13A'});c.run(2);assert.equal(c.r[16],43);
});

test('unregistered device names fail before using an incompatible cached or supplied CPU module',()=>{
  assert.throws(()=>deviceProfile('ATmega328P'),/Unsupported AVR device profile/);
  assert.throws(()=>transpileAVR(image,abi,{device:'ATmega328P'}),/Unsupported AVR device profile/);
  const c=new ATtiny13A(image);
  assert.throws(()=>new ATtiny13A(image,null,{device:'ATmega328P',precompiled:{bytes:c.transpiledBytes,manifest:c.transpilation}}),/Unsupported AVR device profile/);
});
