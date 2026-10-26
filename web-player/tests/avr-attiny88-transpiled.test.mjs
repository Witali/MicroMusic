import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../lib/avr-transpiled.js';
import {AVRCore as Reference} from '../lib/avr-reference.js?v=20261025-board-um88-pipeline';
import {deviceProfile} from '../lib/devices/profiles.js';
import {AT88_DATA as R,AT88_MEMORY as M} from '../lib/attiny88-registers.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js?v=20261025-board-um88-pipeline';
import {createRenderer} from '../lib/engines.js';
import {sameCPU} from './helpers/avr-test-state.mjs';

test('ATtiny88 lowering uses reproducible, hash-checked official definitions and the shared register map',()=>{
  const result=spawnSync(process.execPath,[fileURLToPath(new URL('../scripts/generate-attiny88-registers.mjs',import.meta.url)),'--check'],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  const p=deviceProfile('ATtiny88'),native=resolveAVRProfile('attiny88');
  assert.equal(p.flashBytes,native.flashBytes);assert.equal(p.ramEnd,native.ramEnd);assert.equal(p.ramStart,native.sramStart);
  for(const [key,name] of [['sreg','SREG'],['spl','SPL'],['sph','SPH'],['clkpr','CLKPR'],['wdt','WDTCSR']])assert.equal(native.system[key],R[name]);
  for(const [key,name] of [['a','TCCR1A'],['b','TCCR1B'],['ocra','OCR1A'],['ocrb','OCR1B'],['timsk','TIMSK1'],['tifr','TIFR1']])assert.equal(native.timer[key],R[name]);
  assert.ok(Object.isFrozen(p));assert.ok(Object.isFrozen(p.legacy));assert.equal(M.flashBytes,8192);
});

function pair(words,pc=0x600){
  const image=new Uint8Array(8192).fill(255);words.forEach((w,n)=>{image[(pc+n)*2]=w;image[(pc+n)*2+1]=w>>8;});
  const options={target:'attiny88',fastIdle:false,fastBlocks:false};
  const a=new AVRCore(image,null,options),b=new Reference(image,null,options);
  for(const core of [a,b])core.pc=pc;
  return[a,b];
}
for(const pointer of [26,28,30])test(`ATtiny88 pointer ${pointer}: both bytes cross page boundaries in step and optimized blocks`,()=>{
  const code=pointer===26?[0x930d,0x912e,0x932c]:pointer===28?[0x9309,0x912a,0x8328]:[0x9301,0x9122,0x8320];
  // ST p+,r16; LD r18,-p; ST p,r18. Address 0x1ff -> 0x200 -> 0x1ff.
  for(const block of [false,true]){
    const [a,b]=pair(code);
    for(const c of [a,b]){c.r[pointer]=255;c.r[pointer+1]=1;c.r[16]=0xa5;}
    if(block){assert.equal(a.runBlock(),true);while(b.cyc<a.cyc)b.step();}
    else for(let n=0;n<3;n++){a.step();b.step();sameCPU(a,b);}
    sameCPU(a,b);assert.equal(a.r[18],0xa5);assert.equal(a.data[0x1ff],0xa5);
    assert.equal(a.r[pointer]|a.r[pointer+1]<<8,0x1ff);
  }
});
test('ATtiny88 calls and stack cross SPL boundaries and preserve a high Flash return PC',()=>{
  const [a,b]=pair([0x930f,0x931f,0x912f,0x913f,0xd001,0xcfff,0x9508]);
  for(const c of [a,b]){c.sp=0x200;c.r[16]=0x12;c.r[17]=0x34;}
  for(let n=0;n<6;n++){a.step();b.step();sameCPU(a,b);}
  assert.equal(a.r[18],0x34);assert.equal(a.r[19],0x12);assert.equal(a.sp,0x200);assert.equal(a.pc,0x605);
});
test('ATtiny88 rejects a conflicting target and isolates its cached CPU from ATtiny13A',()=>{
  const image=Uint8Array.of(0,0);
  const a=new AVRCore(image,null,{target:'attiny88'}),b=new AVRCore(image,null,{device:'ATtiny88',cpuHz:16000000});
  assert.equal(b._translatedModule,a._translatedModule);assert.equal(b.cpuHz,16000000);assert.notEqual(a.data,b.data);
  const tiny=new AVRCore(image);assert.notEqual(tiny._translatedModule,a._translatedModule);
  assert.throws(()=>new AVRCore(image,null,{target:'attiny13a',device:'ATtiny88'}),/Conflicting AVR/);
});

for(const file of ['firmware-attiny88.json','firmware-attiny88-16mhz.json','firmware-attiny88-legacy.json']){
  const catalog=JSON.parse(readFileSync(new URL('../'+file,import.meta.url)));
  for(const entry of catalog.entries)test(`${file} / ${entry.id}: AVR → WASM matches JS audio, SRAM, timers and IRQs`,async()=>{
    const a=await createRenderer(entry,48000,{},'transpiled'),b=await createRenderer(entry,48000,{},'js');
    assert.equal(a.core.transpilation.device,'ATtiny88');assert.equal(a.core.cpuHz,entry.cpuHz);
    for(const count of [1,127,1024,4096]){
      assert.deepEqual(a.render(count),b.render(count),'PCM');assert.deepEqual(a.core.rawSamples,b.core.rawSamples,'PWM');
      sameCPU(a.core,b.core);assert.deepEqual(a.core.state(),b.core.state());
    }
    assert.ok(a.core.irqCount>0);assert.equal(a.core.lost,0);assert.equal(a.core.workLost,0);
  });
}
