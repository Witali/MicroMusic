import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr} from './helpers/avr-test-state.mjs';
const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false};
const program=[avr.ldi(16,255),avr.ldi(17,1),avr.add(16,17),[rr(0x1c00,18,17)],
  avr.ldi(24,255),avr.ldi(25,127),[0x9601],avr.ldi(20,128),[0x9405|(20<<4)],
  [rr(0x2c00,21,20)],[0x9402|(21<<4)],[0xfa00|(21<<4)|3],[0xf800|(22<<4)|5],
  [rr(0x0800,23,17)],[rr(0x0400,24,25)],avr.eor(26,26),avr.inc(27)];
const image=flash({instructions:[avr.rjmp(0,16)]},{at:16,instructions:[...program,avr.rjmp(33,33)]});
const make=(extra={})=>{const c=new ATtiny13A(image,null,{...options,...extra});c.clock(8);c.pc=16;return c;};
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
test('constant-heavy ALU blocks preserve full flags and cycles for all256 input SREG values',()=>{
  const a=make(),b=make();
  for(let flags=0;flags<256;flags++){
    for(const c of [a,b]){c._call('avr_reset',0,0);c.clock(8);c.pc=16;c.sreg=flags;for(let n=0;n<32;n++)c.r[n]=(flags+n*17)&255;}
    assert.equal(a._execute('block',Infinity,64),program.length);for(let n=0;n<program.length;n++)b.step();assert.deepEqual(snapshot(a),snapshot(b),'flags'+flags);
  }
});
test('constant chains expose exact state on short runs and all half-phase/1ps observation boundaries',()=>{
  for(const optimizePhaseLocals of [false,true])for(const count of [1,2,3,8,program.length]){
    const a=make({optimizePhaseLocals}),b=make({optimizePhaseLocals});
    a.run(count);for(let n=0;n<count;n++)b.step();assert.deepEqual(snapshot(a),snapshot(b));
  }
  for(let half=1n;half<=36n;half++)for(const delta of [-1n,0n,1n]){
    const a=make(),b=make(),end=a.state().timePs+half*50000n+delta;
    a.runUntilPs(end);for(let at=b.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;b.runUntilPs(at);}
    assert.deepEqual(snapshot(a),snapshot(b));
  }
});
test('new block entries reload host-edited registers and SREG with a cached CPU module',()=>{
  const a=make(),b=make({cacheTranslation:false});
  for(const value of [0,127,128,255]){
    for(const c of [a,b]){c.pc=16;c.r[18]=value;c.sreg=value;}
    a.run(program.length);for(let n=0;n<program.length;n++)b.step();assert.deepEqual(snapshot(a),snapshot(b));
  }
});
