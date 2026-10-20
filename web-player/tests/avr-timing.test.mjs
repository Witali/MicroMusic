// DS40002307A sections 4.7, 5.3, 11.7, 11.9 and 12. CPU-cycle units.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AVRCore } from '../lib/avr-core.js';

const TCCR0A=0x2f, TCCR0B=0x33, TCNT0=0x32, TIMSK0=0x39, TIFR0=0x38;
const out=(a,r=17)=>0xb800|(r<<4)|(a&15)|((a&48)<<5);
const input=(a,r=17)=>0xb000|(r<<4)|(a&15)|((a&48)<<5);
const make=(...words)=>new AVRCore(Uint8Array.from(words.flatMap(w=>[w&255,w>>8])),null,{fastIdle:false});

for (const [source, divisor] of [[1,1],[2,8],[3,64],[4,256],[5,1024]]) {
  for (const mode of [0,3]) test(`Timer0 mode ${mode}, /${divisor}: counter and overflow boundaries`,()=>{
    const c=make(0); c.writeIO(TCCR0A,mode); c.writeIO(TCCR0B,source);
    const first=(mode===3?255:256)*divisor;
    assert.equal(c.overflowAt,first);
    c.clock(first-1); assert.equal(c.pending,false); assert.equal(c.io[TCNT0],Math.floor((first-1)/divisor));
    c.clock(1); assert.equal(c.pending,true); assert.equal(c.io[TCNT0],mode===3?255:0);
    assert.equal(c.io[TIFR0]&2,2); assert.equal(c.overflowAt,first+256*divisor);
    c.clock(3*256*divisor); assert.equal(c.lost,3); // flag coalesces; it is not an interrupt queue
    c.writeIO(TIFR0,0); assert.equal(c.pending,true);
    c.writeIO(TIFR0,2); assert.equal(c.pending,false); assert.equal(c.io[TIFR0],0);
  });
}

test('Timer0 stop/restart preserves count and the free-running prescaler phase',()=>{
  const c=make(0); c.clock(3); c.writeIO(TCCR0B,2); c.clock(4); assert.equal(c.io[TCNT0],0);
  c.clock(1); assert.equal(c.io[TCNT0],1);
  c.writeIO(TCCR0B,0); c.clock(17); assert.equal(c.io[TCNT0],1); assert.equal(c.overflowAt,Infinity);
  c.writeIO(TCCR0B,2); c.clock(6); assert.equal(c.io[TCNT0],1); c.clock(1); assert.equal(c.io[TCNT0],2);
  c.writeIO(TCCR0B,1); c.clock(1); assert.equal(c.io[TCNT0],3);
});

test('OUT/IN happen at their final CPU cycle; TCNT0 writes reschedule overflow',()=>{
  const c=make(out(TCCR0B),input(TCNT0),out(TCNT0),0);
  c.r[17]=1; c.step(); assert.equal(c.cyc,1); assert.equal(c.io[TCNT0],0); assert.equal(c.overflowAt,257);
  c.step(); assert.equal(c.r[17],1); assert.equal(c.io[TCNT0],1);
  c.r[17]=255; c.step(); assert.equal(c.io[TCNT0],255); assert.equal(c.overflowAt,4);
  c.step(); assert.equal(c.pending,true); assert.equal(c.io[TCNT0],0);
});

test('GTCCR resets or holds the prescaler; PRR stops Timer0 counting',()=>{
  const c=make(0); c.clock(3); c.writeIO(0x28,1); assert.equal(c.io[0x28],0);
  c.writeIO(TCCR0B,2); c.clock(7); assert.equal(c.io[TCNT0],0); c.clock(1); assert.equal(c.io[TCNT0],1);
  c.writeIO(0x28,0x81); c.clock(100); assert.equal(c.io[TCNT0],1); assert.equal(c.timer,false);
  c.writeIO(0x28,0); c.clock(8); assert.equal(c.io[TCNT0],2);
  c.writeIO(0x25,2); c.clock(100); assert.equal(c.io[TCNT0],2);
  c.writeIO(0x25,0); c.clock(8); assert.equal(c.io[TCNT0],3);
});

test('pending overflow is serviced even after timer stops or TIMSK is enabled later',()=>{
  const c=make(out(TIMSK0)); c.writeIO(TCCR0B,1); c.clock(256); c.writeIO(TCCR0B,0);
  c.i=1; c.r[17]=2; c.step(); assert.equal(c.pc,3); assert.equal(c.irqCount,1); assert.equal(c.cyc,261);
  assert.equal(c.pending,false); assert.equal(c.sp,157);
});

test('Timer0 advances through all four interrupt-entry cycles and can set TOV again',()=>{
  const c=make(0); c.writeIO(TCCR0B,1); c.writeIO(TCNT0,254); c.writeIO(TIMSK0,2); c.i=1; c.pending=true;
  c.sreg=0xf3; c.step(); assert.equal(c.cyc,5); assert.equal(c.io[TCNT0],3);
  assert.equal(c.pending,true); assert.equal(c.lost,0); assert.equal(c.pc,3); assert.equal(c.irqCount,1);
  assert.equal(c.sreg,0x73); assert.equal(c.data[159],1); assert.equal(c.data[158],0);
});

test('overflow during a multi-cycle instruction waits for its completion',()=>{
  const c=make(0xcfff); c.writeIO(TCCR0B,1); c.writeIO(TCNT0,255); c.writeIO(TIMSK0,2); c.i=1;
  c.step(); assert.equal(c.irqStart,2); assert.equal(c.cyc,6); assert.equal(c.pc,3);
});

test('nested interrupt return preserves the outer ISR and includes nested time in its duration',()=>{
  const c=make(0,0,0,0x9478,0,0x9518); c.writeIO(TIMSK0,2); c.i=1; c.pending=true;
  c.step(); assert.equal(c.cyc,5); assert.equal(c.irqStart,1); assert.equal(c.sp,157);
  c.step(); c.pending=true; c.step(); // SEI, then one NOP before nested entry
  assert.equal(c.cyc,11); assert.equal(c.irqCount,2); assert.equal(c.sp,155);
  c.pc=5; c.step(); assert.equal(c.inIRQ,true); assert.equal(c.irqStart,1); assert.equal(c.maxIRQ,8);
  c.step(); assert.equal(c.inIRQ,false); assert.equal(c.sp,159); assert.equal(c.pc,1); assert.equal(c.maxIRQ,18);
});

test('EEPROM read stalls apply through OUT and ST to EECR and Timer0 runs during the stall',()=>{
  for (const word of [out(0x1c),0x9201|(17<<4),0x9200|(17<<4)]) {
    const c=make(word,0x1c+32); c.eeprom[63]=0xa5; c.writeIO(0x1e,255); c.r[17]=1; c.r[30]=0x1c+32;
    c.writeIO(TCCR0B,1); c.writeIO(TCNT0,252); c.step();
    assert.equal(c.cyc,word===out(0x1c)?5:6); assert.equal(c.io[TCNT0],(252+c.cyc)&255);
    assert.equal(c.pending,true); assert.equal(c.io[0x1d],0xa5); assert.equal(c.io[0x1c]&1,0); assert.equal(c.io[0x1e],63);
  }
});

test('ST Z+ to I/O shares OUT behavior, including SREG and SPL',()=>{
  for (const [address,value] of [[63,0x73],[61,0x90],[TCNT0,0xa5]]) {
    const c=make(0x9201|(17<<4)); c.r[30]=address+32; c.r[17]=value; c.step();
    assert.equal(c.io[address],value); assert.equal(c.cyc,2);
  }
});

test('unimplemented timer modes, external clock, compare IRQs and EEPROM writes fail explicitly',()=>{
  for (const mode of [1,2,4,5,6,7]) {
    const c=make(0); c.writeIO(TCCR0A,mode&3); assert.throws(()=>c.writeIO(TCCR0B,1|((mode&4)<<1)),/WGM mode/);
  }
  for (const source of [6,7]) assert.throws(()=>make(0).writeIO(TCCR0B,source),/External/);
  assert.throws(()=>make(0).writeIO(TIMSK0,4),/compare interrupts/);
  assert.throws(()=>make(0).writeIO(0x1c,2),/EEPROM programming/);
});

test('clock prescaler unlock lasts four cycles; unsupported peripherals cannot silently start',()=>{
  const c=make(0); c.writeIO(0x26,3); assert.equal(c.io[0x26],0);
  c.writeIO(0x26,128); c.clock(3); c.writeIO(0x26,128); // repeated unlock must not extend the window
  c.clock(1); assert.equal(c.io[0x26],0);
  c.writeIO(0x26,3); assert.equal(c.io[0x26],0);
  c.writeIO(0x26,128); c.clock(1); c.writeIO(0x26,0); assert.equal(c.io[0x26],0);
  c.writeIO(0x26,128); assert.throws(()=>c.writeIO(0x26,3),/CPU clock division/);
  for (const [address,value] of [[0x37,9],[0x21,8],[0x06,128],[0x08,8],[0x3b,32]]) {
    assert.throws(()=>make(0).writeIO(address,value),/not implemented/);
  }
});
