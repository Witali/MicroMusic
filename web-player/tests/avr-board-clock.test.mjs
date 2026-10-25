import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVR_PROFILES,resolveAVRProfile,AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';
import {Renderer as JSRenderer} from '../lib/renderer-js.js';
import {Renderer as WASMRenderer} from '../lib/renderer.js';
import {AVRMusicTargetCore} from '../lib/avr-attiny88.js';
const rom=words=>Uint8Array.from(words.flat().flatMap(w=>[w&255,w>>8]));
const engines=[['JS',JS],['WASM',WASM]];
const make=(Core,cpuHz,words=[0])=>new Core(rom(words),null,{target:'attiny88',cpuHz});
const same=(a,b)=>{
 assert.deepEqual(a.data,b.data);assert.deepEqual(a.irqFrames,b.irqFrames);
 for(const key of ['pc','cyc','irqCount','overflowAt','timer','writes','leftWrites','duty','dutyLeft',
  'lost','workLost','maxIRQ','minSP','timerTemp','wdtUntil'])assert.equal(a[key],b[key],key);
};

test('board clock profiles reuse immutable chip maps and preserve all default identities',()=>{
 const eight=resolveAVRProfile('attiny88'),sixteen=resolveAVRProfile('attiny88',{cpuHz:16000000});
 assert.equal(eight,AVR_PROFILES.attiny88);assert.equal(resolveAVRProfile(),AVR_PROFILES.attiny13a);
 assert.equal(resolveAVRProfile('tiny88',{cpuHz:8000000}),eight);
 assert.equal(resolveAVRProfile('tiny88',{cpuHz:16000000}),sixteen);
 assert.equal(resolveAVRProfile('attiny13a',{cpuHz:9600000}),AVR_PROFILES.attiny13a);
 assert.equal(sixteen.id,'attiny88');assert.equal(sixteen.cpuHz,16000000);assert.equal(eight.cpuHz,8000000);
 assert.equal(sixteen.system,eight.system);assert.equal(sixteen.timer,eight.timer);
 assert.ok(Object.isFrozen(sixteen));assert.ok(Object.isFrozen(sixteen.system));
 assert.throws(()=>{sixteen.cpuHz=8000000;},TypeError);
 assert.deepEqual(Object.keys(AVR_PROFILES),['attiny13a','attiny88']);
});

test('unsupported or malformed explicit clocks are rejected before execution',()=>{
 for(const target of ['attiny13a','attiny88'])for(const cpuHz of [0,-1,NaN,Infinity,null,'16000000',12000000,20000000]){
  assert.throws(()=>resolveAVRProfile(target,{cpuHz}),/Unsupported AVR clock/);
  for(const [,Core]of engines)assert.throws(()=>new Core(rom([0]),null,{target,cpuHz}),/Unsupported AVR clock/);
 }
 for(const [,Core]of engines){
  assert.throws(()=>new Core(rom([0]),null,{target:'attiny13a',cpuHz:16000000}),/Unsupported AVR clock/);
  assert.equal(new Core(rom([0])).cpuHz,9600000);
  assert.equal(make(Core).cpuHz,8000000);
 }
});

test('legacy ATtiny88 adapter accepts either board clock and still rejects other chips',()=>{
 for(const target of ['tiny88','attiny88'])for(const cpuHz of [8000000,16000000]){
  const c=new AVRMusicTargetCore(rom([0]),null,{target,cpuHz});
  assert.equal(c.target,'tiny88');assert.equal(c.profile.id,'attiny88');assert.equal(c.cpuHz,cpuHz);
 }
 assert.throws(()=>new AVRMusicTargetCore(rom([0]),null,{target:'attiny13a'}),/Unsupported music target/);
});

for(const [name,Core]of engines){
 test(name+': board clocks and per-instance state stay isolated',()=>{
  const eight=make(Core,8000000),sixteen=make(Core,16000000),another=make(Core,16000000);
  assert.equal(sixteen.cpuHz,16000000);assert.equal(sixteen.profile.cpuHz,16000000);
  assert.equal(eight.profile.cpuHz,8000000);assert.equal(another.profile,sixteen.profile);
  assert.notEqual(eight.data.buffer,sixteen.data.buffer);
  assert.notEqual(another.data.buffer,sixteen.data.buffer);
  sixteen.r[17]=91;sixteen.clock(1234);
  assert.equal(another.r[17],0);assert.equal(eight.cyc,0);assert.equal(another.cyc,0);
 });
 test(name+': no-PWM timeout is one requested CPU second at both board clocks',()=>{
  for(const cpuHz of [8000000,16000000]){
   const c=make(Core,cpuHz,[0xcfff]);
   assert.throws(()=>c.nextDuty(),/no PWM for one emulated second/);
   assert.equal(c.cyc,cpuHz+2);
  }
 });
 test(name+': Timer1 IRQ/PWM cycles remain exact while 16MHz halves elapsed seconds',()=>{
  const words=Array(14).fill(0);words[0]=0xcfff;
  words[11]=0x9200|(17<<4);words[12]=0x8a;words[13]=0x9518;
  const cores=[make(Core,8000000,words),make(Core,16000000,words)];
  for(const c of cores){
   c.r[17]=173;c.writeData(0x80,0x21);c.writeData(0x81,9);c.writeData(0x6f,1);c.i=1;
   assert.equal(c.overflowAt,255);assert.equal(c.nextDuty(),173);
   assert.equal(c.irqCount,1);assert.equal(c.cyc,262);assert.equal(c.sp,765);
  }
  same(...cores);assert.equal(cores[1].cyc/cores[1].cpuHz,cores[0].cyc/cores[0].cpuHz/2);
 });
}

const oldCatalog=JSON.parse(readFileSync(new URL('../firmware-attiny88.json',import.meta.url)));
test('JS/native renderers pass CPU frequency metadata into the shared core and preserve PCM parity',()=>{
 const original=oldCatalog.entries.find(e=>e.id==='rhythmic');
 // The unchanged image intentionally runs at each selected clock here. Actual
 // board arrangements have a separate retuned 62500Hz catalog and audit.
 for(const cpuHz of [8000000,16000000]){
  const entry={...original,cpuHz,pwmHz:cpuHz/256};
  const a=new JSRenderer(entry,48000),b=new WASMRenderer(entry,48000);
  assert.equal(a.core.cpuHz,cpuHz);assert.equal(b.core.cpuHz,cpuHz);
  assert.equal(b.core.profile.cpuHz,cpuHz);
  const actual=a.render(4096),expected=b.render(4096);same(a.core,b.core);
  assert.deepEqual(a.core.rawSamples,b.core.rawSamples);
  let error=0;for(let i=0;i<actual.length;i++)error=Math.max(error,Math.abs(actual[i]-expected[i]));
  assert.ok(error<2e-7,'PCM error '+error);
 }
});
