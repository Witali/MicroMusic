import assert from 'node:assert/strict';
import {CPU,avrInstruction} from 'avr8js';
import {tickAvr} from './avr_tick.mjs';
function fixture(words) {
  const program=new Uint16Array(32);program.set(words);program[16]=0x9518;
  const cpu=new CPU(program,2048);cpu.SP=0x8ff;
  const irq={address:16,flagRegister:0x35,flagMask:1,enableRegister:0x36,enableMask:1};
  cpu.queueInterrupt(irq);
  return cpu;
}
function step(cpu) {const enabled=cpu.interruptsEnabled;avrInstruction(cpu);tickAvr(cpu,enabled);}
for(const instruction of [0x9478,0xbf0f]) { // SEI and OUT SREG,r16
  const cpu=fixture([instruction,0,0]);cpu.data[16]=0x80;
  let event=false;cpu.addClockEvent(()=>{event=true;},1);
  step(cpu);assert.equal(cpu.pc,1);assert.equal(cpu.SP,0x8ff);assert.ok(event);
  step(cpu);assert.equal(cpu.pc,16);assert.equal(cpu.SP,0x8fd);
  assert.equal(cpu.cycles,6);assert.equal(cpu.data[0x8ff],2);
  cpu.queueInterrupt({address:16,flagRegister:0x35,flagMask:1});
  step(cpu);assert.equal(cpu.pc,2,'RETI must return before another pending IRQ');
  step(cpu);assert.equal(cpu.pc,16,'Execute one foreground instruction after RETI');
}
// GCC prologue changes SP across a page, restoring SREG before the SPL write.
const cpu=fixture([0xbfde,0xbf0f,0xbfcd]);
cpu.data[29]=7;cpu.data[28]=200;cpu.data[16]=0x80;
step(cpu);step(cpu);assert.equal(cpu.pc,2);assert.equal(cpu.SP,0x7ff);
step(cpu);assert.equal(cpu.pc,16);assert.equal(cpu.SP,0x7c6);
assert.equal(cpu.data[0x7c8],3,'IRQ uses the completed SP value');
assert.equal(cpu.data[0x7ff],0,'No write through the transient stack pointer');
console.log('PASS: SEI, SREG restore, RETI, pending IRQ, live clock events, four-cycle entry, cross-page SP update');
