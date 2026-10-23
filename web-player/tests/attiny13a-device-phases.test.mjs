import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const make=binary=>new ATtiny13A(binary,null,{fuseLow:0x7a,wakeStartupHalf:0});
const resetAt=(c,at)=>c.injectPins({at:BigInt(at),mask:32,levels:0});
const resetState=(c,at)=>{
  assert.equal(c.state().baseHalf,BigInt(at));assert.equal(c.state().resetCount,1);
  assert.equal(c.pc,0);assert.equal(c.readIO(IO.SPL),0x9f);
  assert.equal(c.readIO(IO.SREG),0);assert.equal(c.state().resetHeld,true);
};

// Stack C2/C3 phases below are the documented digital-profile convention.
// DS40002307A4.5/4.7.1 and DS40002198A specify ordering and total cycles,
// not a silicon guarantee for each stack-byte access during those cycles.
test('PUSH/POP commit at C2 and a reset at that timestamp wins',()=>{
  for(let at=1;at<=4;at++) {
    const push=make(sequential([[0x930f]]));push.r[16]=0x5a;push.data[0x9f]=0xa5;
    resetAt(push,at);push.step();resetState(push,at);assert.equal(push.data[0x9f],0xa5);
    const pop=make(sequential([[0x910f]]));pop.r[16]=0x5a;pop.data[0x9f]=0xa5;
    pop.writeIO(IO.SPL,0x9e);resetAt(pop,at);pop.step();resetState(pop,at);
    assert.equal(pop.r[16],0x5a);
  }
  const c=make(sequential([[0x930f],[0x911f]]));c.r[16]=0x5a;
  c.step();assert.equal(c.data[0x9f],0x5a);assert.equal(c.readIO(IO.SPL),0x9e);
  c.step();assert.equal(c.r[17],0x5a);assert.equal(c.readIO(IO.SPL),0x9f);
  assert.equal(c.state().cycles,4);
});

for(const kind of ['RCALL','ICALL'])test(`${kind} stack bytes commit separately at C2 and C3`,()=>{
  const opcode=kind==='RCALL'?0xd000:0x9509;
  for(let at=1;at<=6;at++) {
    const c=make(flash({at:255,instructions:[[opcode]]}));c.pc=255;
    c.r[30]=20;c.r[31]=0;c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
    resetAt(c,at);c.step();resetState(c,at);
    assert.equal(c.data[0x9f],at>4?0:0xa5,`low byte at ${at}`);
    assert.equal(c.data[0x9e],0x5a,`high byte at ${at}`);
  }
  const c=make(flash({at:255,instructions:[[opcode]]}));c.pc=255;c.r[30]=20;
  c.step();assert.equal(c.state().cycles,3);assert.equal(c.readIO(IO.SPL),0x9d);
  assert.equal(c.data[0x9f],0);assert.equal(c.data[0x9e],1);
  assert.equal(c.pc,kind==='RCALL'?256:20);
});

for(const opcode of [0x9508,0x9518])test(`${opcode===0x9518?'RETI':'RET'} retires PC and I after C4`,()=>{
  for(let at=1;at<=8;at++) {
    const c=make(sequential([[opcode]]));c.writeIO(IO.SPL,0x9d);
    c.data[0x9e]=1;c.data[0x9f]=0x23;resetAt(c,at);c.step();resetState(c,at);
    assert.equal(c.inIRQ,false);
  }
  const c=make(sequential([[opcode]]));c.writeIO(IO.SPL,0x9d);
  c.data[0x9e]=1;c.data[0x9f]=0x23;c.step();
  assert.equal(c.pc,0x123);assert.equal(c.state().cycles,4);assert.equal(c.readIO(IO.SPL),0x9f);
  assert.equal(c.readIO(IO.SREG),opcode===0x9518?128:0);
});

test('reset during IRQ entry prevents later stack bytes and phantom ISR frames',()=>{
  for(let phase=1;phase<=8;phase++) {
    const c=make(sequential([avr.sei(),avr.nop()]));
    c.writeIO(IO.GIMSK,0x40);c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
    c.step();resetAt(c,4+phase);c.step();resetState(c,4+phase);
    assert.equal(c.data[0x9f],phase>4?2:0xa5,`low byte at IRQ half ${phase}`);
    assert.equal(c.data[0x9e],phase>6?0:0x5a,`high byte at IRQ half ${phase}`);
    assert.equal(c.inIRQ,false);assert.equal(c.irqCount,0);
    assert.equal(c.frameCount,0);
  }
});

test('nested interrupt frames retain four-cycle entry and RETI accounting',()=>{
  const c=make(flash(
    {instructions:[avr.rjmp(0,16)]},{at:1,instructions:[avr.rjmp(1,64),avr.rjmp(2,80)]},
    {at:16,instructions:[avr.sei(),avr.nop(),avr.rjmp(18,18)]},
    {at:64,instructions:[avr.sei(),avr.nop(),avr.reti()]},
    {at:80,instructions:[avr.inc(20),avr.reti()]},
  ));
  c.writeIO(IO.MCUCR,3);c.writeIO(IO.PCMSK,1);c.writeIO(IO.GIMSK,0x60);
  c.injectPins({at:1n,mask:3,levels:3});
  c.run(3);assert.equal(c.pc,1);assert.equal(c.cyc,8);assert.equal(c.frameCount,1);
  c.run(3);assert.equal(c.pc,2);assert.equal(c.cyc,16);assert.equal(c.frameCount,2);
  c.run(3);assert.equal(c.pc,66);assert.equal(c.cyc,23);assert.equal(c.frameCount,1);
  assert.equal(c.maxIRQ,11);assert.equal(c.inIRQ,true);
  c.step();assert.equal(c.pc,18);assert.equal(c.cyc,27);assert.equal(c.frameCount,0);
  assert.equal(c.maxIRQ,23);assert.equal(c.inIRQ,false);assert.equal(c.irqCount,2);
  assert.equal(c.readIO(IO.SPL),0x9f);assert.equal(c.r[20],1);
});

test('ALU and word-register results are not written before their completion edge',()=>{
  for(const [opcode,cycles] of [[0x9503,1],[0x9601,2]]) {
    const c=make(sequential([[opcode]]));c.r[16]=10;c.r[24]=20;c.r[25]=1;
    resetAt(c,2*cycles-1);c.step();resetState(c,2*cycles-1);
    assert.equal(c.r[16],10);assert.equal(c.r[24],20);assert.equal(c.r[25],1);
  }
});

test('indirect predecrement and SRAM store wait for completion',()=>{
  for(const opcode of [0x910e,0x930e]) {
    const c=make(sequential([[opcode]]));c.r[26]=0x70;c.r[16]=0x5a;c.data[0x6f]=0xa5;
    resetAt(c,3);c.step();resetState(c,3);
    assert.equal(c.r[26],0x70);assert.equal(c.r[16],0x5a);assert.equal(c.data[0x6f],0xa5);
  }
});

test('LPM recognizes its command at start but commits data and Z at C3',()=>{
  for(let at=1;at<=6;at++) {
    const c=make(sequential([[0x9105]]));c.r[16]=0xa5;c.r[30]=0x20;
    resetAt(c,at);c.step();resetState(c,at);
    assert.equal(c.r[16],0xa5);assert.equal(c.r[30],0x20);
  }
});

test('OUT PORT then IN PIN requires a separating cycle at both factory and playback divisors',()=>{
  // DS40002307A Figure10-4 explicitly requires OUT;NOP;IN. PINB changes
  // at the end of the immediate IN, after that IN has sampled its old value.
  for(const fuseLow of [0x6a,0x7a]) {
    const c=new ATtiny13A(sequential([avr.ldi(16,1),avr.out(IO.PORTB,16),
      avr.in(17,IO.PINB),avr.in(18,IO.PINB)]),null,{fuseLow});
    c.writeIO(IO.DDRB,1);c.run(4);
    assert.equal(c.r[17]&1,0);assert.equal(c.r[18]&1,1);
    assert.equal(c.cyc,4);assert.equal(c.state().baseHalf,BigInt(fuseLow===0x6a?64:8));
  }
});

test('a reset after IN samples the bus still cancels the destination write',()=>{
  const c=make(sequential([avr.in(16,IO.SPL)]));c.r[16]=0x5a;
  resetAt(c,2);c.step();resetState(c,2);assert.equal(c.r[16],0x5a);
});
