import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {ATtiny13A} from '../lib/attiny13a.js';
import {Renderer} from '../lib/renderer-device.js';
import {AVRCore as NativeCore} from '../lib/avr-wasm.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

test('connected runtime has fixed shared memory, no host imports and current source provenance',()=>{
  const report=JSON.parse(readFileSync(new URL('../wasm/device-build.json',import.meta.url)));
  const binary=readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url));
  const hash=value=>createHash('sha256').update(value).digest('hex');
  assert.equal(hash(binary),report.artifacts['attiny13a.wasm']);
  for(const [path,digest] of Object.entries(report.inputs))
    assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),digest,path);
  const module=new WebAssembly.Module(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
  const runtime=new WebAssembly.Instance(module).exports;assert.equal(runtime.memory.buffer.byteLength,131072);
  assert.throws(()=>runtime.memory.grow(1),RangeError);
});

function pwm({ddr=3,a=191,b=63,fastIdle=true}={}){
  const core=new ATtiny13A(sequential([avr.rjmp(0,0)]),null,{fastIdle});
  core.writeIO(0x17,ddr);core.writeIO(0x36,a);core.writeIO(0x29,b);
  core.writeIO(0x2f,0xa3);core.writeIO(0x33,1);return core;
}

test('physical audio integrates DDR-controlled PB0/PB1 transitions, rather than OCR writes',()=>{
  const core=pwm(),samples=core.capturePhysical(32,37500,2);
  for(let n=2;n<32;n++){
    assert.equal(samples[2*n],.5);assert.equal(samples[2*n+1],-.5);
  }
  const disconnected=pwm({ddr:0});
  assert.ok(disconnected.capturePhysical(32,37500,2).every(x=>x===-1));
  assert.equal(core._exports.avr_device_fault(),0);
});

test('bounded native wait acceleration preserves every physical output sample and event boundary',()=>{
  const fast=pwm(),exact=pwm({fastIdle:false});
  const a=fast.capturePhysical(1000,44100,2),b=exact.capturePhysical(1000,44100,2);
  assert.deepEqual(a,b);assert.deepEqual(fast.data,exact.data);
  assert.equal(fast.cyc,exact.cyc);assert.equal(fast.pc,exact.pc);
  assert.equal(fast.state().baseHalf,exact.state().baseHalf);
  assert.ok(fast.idleCycles>0);assert.equal(exact.idleCycles,0);
});

for(const rate of [44100,48000,96000])test(`physical capture preserves phase and CPU state across arbitrary ${rate} Hz batch boundaries`,()=>{
  const a=pwm(),b=pwm(),expected=a.capturePhysical(4217,rate,2),actual=[];
  for(const n of [1,17,2048,2151])actual.push(...b.capturePhysical(n,rate,2));
  assert.deepEqual(Float32Array.from(actual),expected);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
});

test('physical capture crosses JS/WASM once per batch and reports undrained trace overflow',()=>{
  const core=pwm(),calls=[],execute=core._execute.bind(core);
  core._execute=(...args)=>{calls.push(args);return execute(...args);};
  core.capturePhysical(4096,48000,1);assert.deepEqual(calls,[['capturePhysical',4096]]);
  const trace=pwm();assert.throws(()=>trace.runUntil(1000000n),/peripheral fault 9/);
  assert.ok(trace.drainPins().length>0);
});

for(const programming of [false,true])test(`physical capture drains maximum-rate pin transitions inside WASM${programming?' during SPM halt':''}`,()=>{
  const instructions=programming?[avr.ldi(30,0),avr.ldi(31,1),avr.ldi(16,3),avr.out(0x37,16),[0x95e8],avr.rjmp(5,5)]:[avr.rjmp(0,0)];
  const core=new ATtiny13A(sequential(instructions),null,{fuseHigh:0xef,spmCommandCycles:4});
  core.writeIO(0x17,1);core.writeIO(0x36,0);core.writeIO(0x2f,0x42);core.writeIO(0x33,1);
  // CTC TOP0 toggles PB0 at 9.6MHz/2:1200 transitions per8kHz audio frame,
  // exceeding the1024 trace ring if it were drained only after each frame.
  const samples=core.capturePhysical(8,8000,2);
  for(let n=0;n<8;n++){assert.equal(samples[2*n],0);assert.equal(samples[2*n+1],-1);}
  assert.equal(core.state().deviceFault,0);
  assert.equal(core.state().halted,programming);assert.equal(core.state().sleeping,false);
});

const catalog=[...JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url))).entries,
  ...JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url))).entries];
for(const rate of [44100,48000,96000])for(const channels of [1,2])
test(`physical ${channels}-channel DSP matches the native C filter at ${rate} Hz`,()=>{
  const entry=catalog.find(e=>(e.audioChannels||1)===channels),controls={cutoff:9000,volume:.65};
  const renderer=new Renderer(entry,rate,controls),actual=renderer.render(4096);
  const expected=new Float32Array(actual.length);
  for(let ch=0;ch<channels;ch++){
    // avr_filter is the mono diagnostic API; use independent filter state for L/R.
    const native=new NativeCore(Uint8Array.of(0,0));native.configureAudio(rate,37500,controls);
    const input=Float32Array.from({length:4096},(_,n)=>renderer.core.rawSamples[n*channels+ch]);
    const output=native.filterSamples(input);
    for(let n=0;n<output.length;n++)expected[n*channels+ch]=output[n];
  }
  for(let n=0;n<actual.length;n++)assert.ok(Math.abs(actual[n]-expected[n])<2e-7);
});
for(const entry of catalog)test(`${entry.id}: connected device renders physical pins with every peripheral enabled`,()=>{
  const renderer=new Renderer(entry,48000),samples=renderer.render(4096);
  assert.equal(samples.length,4096*(entry.audioChannels||1));
  assert.ok(samples.every(Number.isFinite));
  assert.ok(renderer.core.rawSamples.every(x=>x>=-1&&x<=1));
  assert.equal(renderer.core.state().deviceFault,0);
  assert.ok(renderer.core.state().baseHalf>=1638400n);
});
