import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-transpiled.js';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

test('translation cache shares compiled code while isolating memory and public diagnostics',()=>{
  const image=sequential([avr.ldi(16,0x5a)]);
  const a=new AVRCore(image),b=new AVRCore(image);
  assert.equal(b.translationCacheHit,true);assert.equal(a._translatedModule,b._translatedModule);
  assert.notEqual(a._exports.memory,b._exports.memory);
  assert.equal(Object.getPrototypeOf(a),Object.getPrototypeOf(b));
  a.transpilation.abi.data=0;a.transpiledBytes.fill(0);a.r[17]=0xaa;
  const c=new AVRCore(image);assert.equal(c.translationCacheHit,true);
  assert.ok(c.transpilation.abi.data>0);assert.equal(WebAssembly.validate(c.transpiledBytes),true);
  assert.equal(c.r[17],0);b.step();c.step();assert.equal(b.r[16],0x5a);assert.equal(c.r[16],0x5a);
});

test('compiler options and runtime identity separate cached translations',()=>{
  const image=sequential([avr.ldi(17,0x6b)]);
  const a=new AVRCore(image),b=new AVRCore(image,null,{optimizeFlags:false});
  assert.notEqual(a._translatedModule,b._translatedModule);
  const disabled=new AVRCore(image,null,{cacheTranslation:false});
  assert.equal(disabled.translationCacheHit,false);assert.notEqual(a._translatedModule,disabled._translatedModule);
  const device=new ATtiny13A(image);assert.notEqual(a._translatedModule,device._translatedModule);
});

test('clock and fuse configuration remain instance-owned with shared generated code',()=>{
  const image=sequential([avr.ldi(18,0x7c)]);
  const a=new ATtiny13A(image,null,{fuseLow:0x7a}),b=new ATtiny13A(image,null,{fuseLow:0x6a});
  assert.equal(b.translationCacheHit,true);assert.equal(a._translatedModule,b._translatedModule);
  a.step();b.step();assert.equal(a.state().baseHalf,2n);assert.equal(b.state().baseHalf,16n);
  assert.equal(a.r[18],0x7c);assert.equal(b.r[18],0x7c);
});

test('Flash changes select fresh code and restoring an exact image can reuse its module',()=>{
  const image=sequential([avr.ldi(19,0x8d)]),c=new ATtiny13A(image);
  const original=c._translatedModule;
  c.rom.set(avr.ldi(19,0x9e).flatMap(w=>[w&255,w>>8]));c._compile();
  assert.notEqual(c._translatedModule,original);c.step();assert.equal(c.r[19],0x9e);
  c.rom.set(image);c._compile();assert.equal(c._translatedModule,original);
  assert.equal(c.translationCacheHit,true);c.pc=0;c.step();assert.equal(c.r[19],0x8d);
});

test('cache evicts old images after eight entries without disturbing live instances',()=>{
  const image=sequential([avr.ldi(20,0xa0)]),first=new AVRCore(image);
  for(let n=1;n<=8;n++)new AVRCore(sequential([avr.ldi(20,0xa0+n)]));
  const again=new AVRCore(image);assert.equal(again.translationCacheHit,false);
  assert.notEqual(first._translatedModule,again._translatedModule);
  first.step();again.step();assert.equal(first.r[20],0xa0);assert.equal(again.r[20],0xa0);
});

test('precompiled code checks the actual runtime ABI before binding',()=>{
  const image=sequential([avr.ldi(21,0xb1)]),a=new AVRCore(image);
  const manifest=structuredClone(a.transpilation);manifest.abi.data++;
  assert.throws(()=>new AVRCore(image,null,{precompiled:{bytes:a.transpiledBytes,manifest}}),/ABI mismatch/);
  const b=new AVRCore(image,null,{precompiled:{bytes:a.transpiledBytes,manifest:a.transpilation}});
  b.step();assert.equal(b.r[21],0xb1);
});
