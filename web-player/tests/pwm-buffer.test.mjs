import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-transpiled.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {Renderer} from '../lib/renderer-transpiled.js';
import {Renderer as NativeRenderer} from '../lib/renderer.js';
import {parseHex} from '../lib/hex.js';
import {sameCPU,put,out} from './helpers/avr-test-state.mjs';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const speech=JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url)));

for(const entry of [...catalog.entries,...speech.entries])test(entry.id+': WASM PWM buffer preserves every output frame and exact batch-exit CPU state',()=>{
  const rom=parseHex(entry.flashHex),ep=entry.eepromHex?parseHex(entry.eepromHex,64):null,channels=entry.audioChannels||1;
  const actual=new AVRCore(rom,ep),reference=new Reference(rom,ep,{fastIdle:false,fastBlocks:false});
  assert.ok(actual._pwm8.byteOffset+actual._pwm8.byteLength<=actual.transpilation.abi.data||actual._pwm8.byteOffset>=actual.transpilation.abi.data+160);
  assert.equal(actual._pwm8.buffer,actual._exports.memory.buffer);
  for(const count of [0,1,17,4096,4113]){
    const captured=actual.capturePWM(count,channels);assert.equal(captured.length,count);
    for(let i=0;i<count;i++)assert.equal(captured[i],channels===2?reference.nextStereoDuty():reference.nextDuty());
    sameCPU(actual,reference);
  }
});

test('one audio block crosses the JS/WASM boundary per PWM batch, never per PWM frame',()=>{
  const entry=catalog.entries[0],renderer=new Renderer(entry,48000),calls=[],original=renderer.core._execute.bind(renderer.core);
  renderer.core._execute=(name,...args)=>{calls.push([name,...args]);return original(name,...args);};
  renderer.core.nextDuty=()=>{throw Error('Per-frame JS calls must not execute');};
  renderer.render(4096);assert.deepEqual(calls,[['capturePWM',3202,1]]);
  assert.throws(()=>renderer.core.capturePWM(-1),/capture/);assert.throws(()=>renderer.core.capturePWM(1,3),/capture/);
  assert.throws(()=>renderer.render(0),/block size/);
});

for(const rate of [8000,44100,96000])for(const entry of [catalog.entries[0],catalog.entries.find(e=>e.audioChannels===2),speech.entries[0]])
test(`${entry.id}/${rate}: arbitrary audio boundaries preserve resampler phase, PCM and CPU without look-ahead`,()=>{
  const controls={cutoff:4000,volume:.65},a=new Renderer(entry,rate,controls),b=new NativeRenderer(entry,rate,controls);
  for(const count of [1,127,4096,17,8193]){
    const actual=a.render(count),expected=b.render(count);assert.equal(actual.length,expected.length);
    for(let i=0;i<actual.length;i++)assert.ok(Math.abs(actual[i]-expected[i])<2e-7);
    assert.deepEqual(a.core.rawSamples,b.core.rawSamples);sameCPU(a.core,b.core);
  }
});

test('stereo capture rejects missing OC0A writes, rather than duplicating an old left sample',()=>{
  const rom=new Uint8Array(1024).fill(255);put(rom,0,out(0x29));put(rom,1,0xcffe);
  const core=new AVRCore(rom);core.writeIO(0x33,1);
  assert.throws(()=>core.capturePWM(2,2),/one OC0A write/);
});
