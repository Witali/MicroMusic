// Executable phase oracles for the real generated CPU. The trace is produced
// inside C/WASM bridge wrappers, not callbacks into JS or a second CPU model.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {makePhaseProbe,phaseTrace,replaceAfterRead,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const clocks=(core,kind=E.CLOCK_ENTER)=>phaseTrace(core).filter(e=>e.kind===kind);
const events=(core,kind)=>phaseTrace(core).filter(e=>e.kind===kind);
const resetAt=(core,half)=>core.injectPins({at:BigInt(half),mask:32,levels:0});

for(const [name,instruction,readHalf] of [
  ['IN',avr.in(16,IO.SPL),1n],
  ['LDS',avr.lds(16,32+IO.SPL),3n],
  ['LD X+',[0x910d],3n],
])test(`${name}: one bus read latches a value before its destination/pointer commit`,()=>{
  const c=makePhaseProbe(sequential([instruction]));c.r[16]=0x5a;c.r[26]=32+IO.SPL;
  replaceAfterRead(c,IO.SPL,0x9e);c.step();
  const reads=events(c,E.READ);assert.equal(reads.length,1);
  assert.equal(reads[0].half,readHalf);assert.equal(reads[0].value,0x9f);
  assert.equal(reads[0].r16,0x5a);
  const writes=events(c,E.AFTER_READ);assert.equal(writes.length,1);assert.equal(writes[0].sp,0x9e);
  const completion=clocks(c,E.CLOCK_EXIT).find(e=>e.half===readHalf+1n);
  assert.equal(completion.r16,0x5a,'Destination changes after the completed clock barrier');
  assert.equal(c.r[16],0x9f,'Must retain the earlier read rather than reread the changed SPL');
  assert.equal(c.sp,0x9e);assert.equal(c.r[26],32+IO.SPL+(name==='LD X+'?1:0));
});

test('ST -X and PUSH expose no memory/SP/pointer effect before C2 completes',()=>{
  const st=makePhaseProbe(sequential([[0x930e]]));st.r[26]=0x70;st.r[16]=0x5a;st.data[0x6f]=0xa5;
  st.step();assert.deepEqual(clocks(st).map(e=>e.argument),[4,0]);
  assert.equal(clocks(st,E.CLOCK_EXIT)[0].x,0x70);assert.equal(st.r[26],0x6f);assert.equal(st.data[0x6f],0x5a);
  const push=makePhaseProbe(sequential([[0x930f]]));push.r[16]=0x5a;push.data[0x9f]=0xa5;
  push.step();const before=clocks(push,E.CLOCK_EXIT)[0];
  assert.equal(before.half,4n);assert.equal(before.sp,0x9f);assert.equal(before.stackLow,0xa5);
  assert.equal(push.sp,0x9e);assert.equal(push.data[0x9f],0x5a);
});

// Stack C2/C3 are the existing documented digital-profile convention; the AVR
// manual guarantees ordering/totals, not these exact internal silicon phases.
for(const [name,opcode] of [['RCALL',0xd000],['ICALL',0x9509]])test(`${name}: completed low stack byte survives the next barrier independently`,()=>{
  const c=makePhaseProbe(flash({at:255,instructions:[[opcode]]}));c.pc=255;c.r[30]=20;
  c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;c.step();
  const entering=clocks(c);assert.deepEqual(entering.map(e=>e.argument),[4,2,0]);
  assert.equal(entering[1].half,4n);assert.equal(entering[1].sp,0x9e);
  assert.equal(entering[1].stackLow,0);assert.equal(entering[1].stackHigh,0x5a);
  const exiting=clocks(c,E.CLOCK_EXIT);assert.equal(exiting[1].half,6n);assert.equal(exiting[1].stackHigh,0x5a);
  assert.equal(c.data[0x9e],1);assert.equal(c.sp,0x9d);assert.equal(c.pc,name==='RCALL'?256:20);
});

for(const [name,opcode] of [['RET',0x9508],['RETI',0x9518]])test(`${name}: popped bytes persist until the final PC/flags commit`,()=>{
  const c=makePhaseProbe(sequential([[opcode]]));c.sp=0x9d;c.data[0x9e]=1;c.data[0x9f]=0x23;c.step();
  const entering=clocks(c);assert.deepEqual(entering.map(e=>e.argument),[4,2,2,0]);
  assert.deepEqual(entering.slice(0,3).map(e=>e.sp),[0x9d,0x9e,0x9f]);
  assert.deepEqual(entering.slice(0,3).map(e=>e.sreg),[0,0,0]);
  assert.equal(c.pc,0x123);assert.equal(c.sreg,name==='RETI'?128:0);assert.equal(c.sp,0x9f);
});

test('LPM recognizes RFLB once at start and keeps its read value through C3',()=>{
  const c=makePhaseProbe(sequential([[0x9105]]));c.r[16]=0xa5;c.r[30]=0;
  c.writeIO(IO.SPMCSR,9);clearPhaseProbe(c);c.step();
  const read=events(c,E.LPM);assert.equal(read.length,1);assert.equal(read[0].half,0n);
  assert.equal(read[0].value,0x7a);assert.equal(read[0].r16,0xa5);
  assert.deepEqual(clocks(c).map(e=>e.argument),[6,0]);
  assert.equal(clocks(c,E.CLOCK_EXIT)[0].r16,0xa5);assert.equal(clocks(c,E.CLOCK_EXIT)[0].z,0);
  assert.equal(c.r[16],0x7a);assert.equal(c.r[30],1);assert.equal(c.readIO(IO.SPMCSR),0);
});

test('EEPROM command commits once and its returned stall clocks do not repeat the bus write',()=>{
  const c=makePhaseProbe(sequential([avr.out(IO.EECR,16)]));c.r[16]=2;
  c.writeIO(IO.EEARL,4);c.writeIO(IO.EEDR,42);c.writeIO(IO.EECR,4);clearPhaseProbe(c);c.step();
  const writes=events(c,E.WRITE);assert.equal(writes.length,1);assert.equal(writes[0].argument,IO.EECR);
  assert.equal(writes[0].half,2n);assert.deepEqual(clocks(c).map(e=>e.argument),[2,4]);
  assert.equal(c.cyc,3);assert.equal(c.eeprom[4],255);assert.equal(c.readIO(IO.EECR)&2,2);
});

test('reset after a read discards its destination, while reset after a push retains committed SRAM',()=>{
  const input=makePhaseProbe(sequential([avr.in(16,IO.SPL)]));input.r[16]=0x5a;
  resetAt(input,2);input.step();assert.equal(events(input,E.READ).length,1);
  assert.equal(input.r[16],0x5a);assert.equal(input.pc,0);assert.equal(input.state().resetCount,1);
  const call=makePhaseProbe(flash({at:255,instructions:[[0xd000]]}));call.pc=255;
  call.data[0x9f]=0xa5;call.data[0x9e]=0x5a;resetAt(call,5);call.step();
  assert.deepEqual(clocks(call).map(e=>e.argument),[4,2]);
  assert.equal(call.data[0x9f],0);assert.equal(call.data[0x9e],0x5a);
  assert.equal(call.pc,0);assert.equal(call.sp,0x9f);assert.equal(call.state().baseHalf,5n);
});
