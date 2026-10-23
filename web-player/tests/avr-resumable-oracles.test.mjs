// Real generated instruction continuations, real C/WASM device/phase backend.
// Wall deadlines split execution; no hand-maintained CPU/scheduler mirror.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {makePhaseProbe,phaseTrace,replaceAfterRead,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const halfPs=50000n;
const options={oscillatorHz:10000000,osccalHz:Array.from({length:128},(_,n)=>n===0?10000000:0),
  resumable:true,factoryOsccal96:0,nvmClockProfile:1,nvmCalibrationReferenceHz:10000000};
const make=binary=>makePhaseProbe(binary,options);
const events=(core,kind)=>phaseTrace(core).filter(e=>e.kind===kind);
const phase=core=>core.state().cpuPhase;
function until(core,at){
  const before=phase(core).retired,done=core.runUntilPs(at);
  assert.equal(core.state().timePs,at);assert.equal(core.state().deviceFault,0);
  assert.equal(done,Number(phase(core).retired-before),'Count retirements rather than attempted resumes');return done;
}
const retired=(core,count)=>assert.equal(phase(core).retired,BigInt(count));
const resetAt=(core,at)=>core.injectPinsPs({at,mask:32,levels:0});

for(const [name,instruction,readHalf] of [
  ['IN',avr.in(16,IO.SPL),1n],['LDS',avr.lds(16,32+IO.SPL),3n],['LD X+',[0x910d],3n],
])test(`${name}: WAIT preserves the earlier bus latch and commits only at the final half edge`,()=>{
  const c=make(sequential([instruction]));c.r[16]=0x5a;c.r[26]=32+IO.SPL;
  replaceAfterRead(c,IO.SPL,0x9e);
  assert.equal(until(c,readHalf*halfPs),0);assert.equal(c.r[16],0x5a);assert.equal(c.pc,0);
  assert.equal(phase(c).active,1);retired(c,0);
  assert.equal(events(c,E.READ).length,1);assert.equal(events(c,E.READ)[0].value,0x9f);
  assert.equal(events(c,E.READ)[0].timePs,readHalf*halfPs);assert.equal(c.sp,0x9e);
  assert.equal(until(c,(readHalf+1n)*halfPs-1n),0);assert.equal(c.r[16],0x5a);
  assert.equal(events(c,E.READ).length,1);assert.equal(phase(c).remainingHalves,1n);
  assert.equal(until(c,(readHalf+1n)*halfPs),1);assert.equal(c.r[16],0x9f);
  assert.equal(c.r[26],32+IO.SPL+(name==='LD X+'?1:0));assert.equal(c.pc,name==='LDS'?2:1);
  assert.equal(phase(c).active,0);assert.equal(events(c,E.READ).length,1);retired(c,1);
  assert.ok(events(c,E.PHASE_EXIT).some(e=>e.status===0),'The native clock really returned WAIT');
});

for(const [name,opcode] of [['ST -X',0x930e],['PUSH',0x930f]])test(`${name}: partial C2 wait retains source/address without early stores`,()=>{
  const c=make(sequential([[opcode]]));c.r[16]=0x5a;c.r[26]=0x70;c.data[0x6f]=0xa5;c.data[0x9f]=0xc3;
  until(c,4n*halfPs-1n);assert.equal(c.r[26],0x70);assert.equal(c.sp,0x9f);
  assert.equal(c.data[0x6f],0xa5);assert.equal(c.data[0x9f],0xc3);assert.equal(c.pc,0);retired(c,0);
  until(c,4n*halfPs);retired(c,1);assert.equal(c.pc,1);
  if(name==='PUSH'){assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],0x5a);}
  else{assert.equal(c.r[26],0x6f);assert.equal(c.data[0x6f],0x5a);}
});

// C2/C3 stack accesses retain the existing explicit digital-profile convention,
// not an additional assertion about undocumented silicon internals.
for(const [name,opcode] of [['RCALL',0xd000],['ICALL',0x9509]])test(`${name}: C2 and C3 stack commits survive separate host pauses exactly once`,()=>{
  const c=make(flash({at:255,instructions:[[opcode]]}));c.pc=255;c.r[30]=20;
  c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
  until(c,4n*halfPs);assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],0);assert.equal(c.data[0x9e],0x5a);
  assert.equal(c.pc,255);retired(c,0);
  until(c,6n*halfPs-1n);assert.equal(c.sp,0x9e);assert.equal(c.data[0x9e],0x5a);retired(c,0);
  until(c,6n*halfPs);assert.equal(c.sp,0x9d);assert.equal(c.data[0x9f],0);assert.equal(c.data[0x9e],1);
  assert.equal(c.pc,name==='RCALL'?256:20);assert.equal(phase(c).active,0);retired(c,1);
});

for(const [name,opcode] of [['RET',0x9508],['RETI',0x9518]])test(`${name}: each popped byte remains latched across the following wait`,()=>{
  const c=make(sequential([[opcode]]));c.sp=0x9d;c.data[0x9e]=1;c.data[0x9f]=0x23;
  until(c,4n*halfPs);assert.equal(c.sp,0x9e);assert.equal(c.pc,0);assert.equal(c.sreg,0);
  c.data[0x9e]=0x7f; // A debugger changes already-popped SRAM; the latch stays1.
  until(c,6n*halfPs);assert.equal(c.sp,0x9f);assert.equal(c.pc,0);assert.equal(c.sreg,0);
  c.data[0x9f]=0xff; // Likewise, the low byte already read was0x23.
  until(c,8n*halfPs-1n);assert.equal(c.pc,0);retired(c,0);
  until(c,8n*halfPs);assert.equal(c.pc,0x123);assert.equal(c.sp,0x9f);
  assert.equal(c.sreg,name==='RETI'?128:0);retired(c,1);
});

test('LPM consumes RFLB only once and retains the result through fractional C3 waits',()=>{
  const c=make(sequential([[0x9105]]));c.r[16]=0xa5;c.r[30]=0;
  c.writeIO(IO.SPMCSR,9);clearPhaseProbe(c);
  for(const at of [1n,halfPs-1n,halfPs,5n*halfPs,6n*halfPs-1n]){
    until(c,at);assert.equal(c.r[16],0xa5);assert.equal(c.r[30],0);assert.equal(c.pc,0);retired(c,0);
    const reads=events(c,E.LPM);assert.equal(reads.length,1);assert.equal(reads[0].timePs,0n);assert.equal(reads[0].value,0x7a);
  }
  until(c,6n*halfPs);assert.equal(c.r[16],0x7a);assert.equal(c.r[30],1);retired(c,1);
  assert.equal(events(c,E.LPM).length,1);assert.equal(c.readIO(IO.SPMCSR),0);
});

test('EEPE write happens once before resumable stall clocks and is not replayed',()=>{
  const c=make(sequential([avr.out(IO.EECR,16)]));c.r[16]=2;
  c.writeIO(IO.EEARL,4);c.writeIO(IO.EEDR,42);c.writeIO(IO.EECR,4);clearPhaseProbe(c);
  until(c,2n*halfPs-1n);assert.equal(events(c,E.WRITE).length,0);retired(c,0);
  until(c,2n*halfPs);assert.equal(events(c,E.WRITE).length,1);assert.equal(c.pc,0);retired(c,0);
  for(const at of [3n*halfPs,5n*halfPs,6n*halfPs-1n]){
    until(c,at);assert.equal(events(c,E.WRITE).length,1);assert.equal(c.eeprom[4],255);retired(c,0);
  }
  until(c,6n*halfPs);assert.equal(c.pc,1);assert.equal(c.cyc,3);retired(c,1);
  const writes=events(c,E.WRITE);assert.equal(writes.length,1);assert.equal(writes[0].timePs,2n*halfPs);
  assert.equal(c.readIO(IO.EECR)&2,2);assert.equal(c.eeprom[4],255);
});

test('last edge at the exact deadline retires its result and zero-time trailing stage',()=>{
  const c=make(sequential([avr.ldi(16,0x5a)]));c.r[16]=1;
  until(c,2n*halfPs-1n);assert.equal(c.r[16],1);assert.equal(c.pc,0);retired(c,0);
  until(c,2n*halfPs);assert.equal(c.r[16],0x5a);assert.equal(c.pc,1);retired(c,1);
  assert.equal(phase(c).active,0);assert.equal(phase(c).remainingHalves,0n);
  assert.equal(until(c,2n*halfPs),0);retired(c,1);
  assert.ok(events(c,E.PHASE_EXIT).some(e=>e.argument===0&&e.status===1&&e.timePs===2n*halfPs));
});

test('OUT commits its physical pin at the exact boundary without an extra host call',()=>{
  const c=make(sequential([avr.out(IO.PORTB,16)]));c.r[16]=1;c.writeIO(IO.DDRB,1);clearPhaseProbe(c);
  until(c,2n*halfPs-1n);assert.equal(c.state().pins.levels&1,0);assert.equal(events(c,E.WRITE).length,0);
  until(c,2n*halfPs);assert.equal(c.state().pins.levels&1,1);assert.equal(c.pc,1);retired(c,1);
  const writes=events(c,E.WRITE);assert.equal(writes.length,1);assert.equal(writes[0].timePs,2n*halfPs);
  until(c,2n*halfPs);assert.equal(events(c,E.WRITE).length,1);
});

for(const [name,opcode,oldFlags,newFlags] of [['CLI',0x94f8,128,0],['SEI',0x9478,0,128],['SET',0x9468,0,64]])
  test(`${name}: pending flags are not visible until the completing clock edge`,()=>{
    const c=make(sequential([[opcode]]));c.sreg=oldFlags;
    until(c,2n*halfPs-1n);assert.equal(c.sreg,oldFlags);retired(c,0);
    until(c,2n*halfPs);assert.equal(c.sreg,newFlags);retired(c,1);
  });

test('reset wins a tie with OUT completion and discards stale saved locals',()=>{
  const c=make(sequential([avr.out(IO.PORTB,16)]));c.r[16]=1;c.writeIO(IO.DDRB,1);clearPhaseProbe(c);
  resetAt(c,2n*halfPs);until(c,halfPs);assert.equal(phase(c).active,1);
  until(c,2n*halfPs);assert.equal(c.pc,0);assert.equal(c.sp,0x9f);assert.equal(c.sreg,0);
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,true);assert.equal(phase(c).active,0);retired(c,0);
  assert.equal(events(c,E.WRITE).length,0);assert.equal(c.readIO(IO.PORTB),0);
  assert.ok(events(c,E.PHASE_EXIT).some(e=>e.status===-1&&e.error===0));
});

test('reset at C3 preserves the earlier low call byte and cancels high byte/PC retirement',()=>{
  const c=make(flash({at:255,instructions:[[0xd000]]}));c.pc=255;c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
  resetAt(c,6n*halfPs);until(c,4n*halfPs);assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],0);
  until(c,6n*halfPs);assert.equal(c.data[0x9f],0);assert.equal(c.data[0x9e],0x5a);
  assert.equal(c.pc,0);assert.equal(c.sp,0x9f);assert.equal(phase(c).active,0);retired(c,0);
});

test('reset after IN sampling discards the old latch and release starts a fresh instruction',()=>{
  const c=make(sequential([avr.in(16,IO.SPL)]));c.r[16]=0x5a;
  resetAt(c,2n*halfPs);until(c,halfPs);assert.equal(events(c,E.READ).length,1);
  until(c,2n*halfPs);assert.equal(c.r[16],0x5a);assert.equal(phase(c).active,0);retired(c,0);
  c.injectPinsPs({at:3n*halfPs,mask:32,levels:32});until(c,3n*halfPs);
  assert.equal(c.state().resetHeld,false);c.sp=0x9e;
  until(c,5n*halfPs);assert.equal(c.r[16],0x9e);assert.equal(c.pc,1);retired(c,1);
  assert.deepEqual(events(c,E.READ).map(e=>e.value),[0x9f,0x9e]);
});

test('mid-instruction waits and ready checks do not decrement the interrupt delay',()=>{
  const c=make(sequential([[0x9601]]));c.r[24]=20;c.irqDelay=3;
  for(const at of [1n,halfPs,2n*halfPs,3n*halfPs,4n*halfPs-1n]){
    until(c,at);assert.equal(c.irqDelay,3);assert.equal(c.r[24],20);retired(c,0);
    for(let n=0;n<3;n++)assert.equal(c._exports.avr_device_ready(),1);
    assert.equal(c.irqDelay,3);
  }
  until(c,4n*halfPs);assert.equal(c.r[24],21);assert.equal(c.irqDelay,2);retired(c,1);
});

test('pending IRQ resumes C2/C3/C4 entry without retiring extra instructions',()=>{
  const c=make(sequential([avr.nop()]));c.sreg=128;c.writeIO(IO.EECR,8);clearPhaseProbe(c);
  c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
  until(c,2n*halfPs);retired(c,1);assert.equal(phase(c).active,2);assert.equal(c.pc,1);assert.equal(c.irqCount,0);
  until(c,6n*halfPs);retired(c,1);assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],1);assert.equal(c.data[0x9e],0x5a);
  until(c,8n*halfPs);retired(c,1);assert.equal(c.sp,0x9d);assert.equal(c.data[0x9e],0);assert.equal(c.pc,1);
  until(c,10n*halfPs);retired(c,1);assert.equal(c.pc,4);assert.equal(c.irqCount,1);assert.equal(c.frameCount,1);
  assert.equal(phase(c).active,0);assert.equal(c.inIRQ,true);
});

test('reset wins an IRQ C3 tie, retaining its low byte without a phantom ISR frame',()=>{
  const c=make(sequential([avr.nop()]));c.sreg=128;c.writeIO(IO.EECR,8);clearPhaseProbe(c);
  c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;resetAt(c,8n*halfPs);
  until(c,6n*halfPs);assert.equal(phase(c).active,2);assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],1);
  until(c,8n*halfPs);assert.equal(c.data[0x9e],0x5a);assert.equal(c.sp,0x9f);assert.equal(c.pc,0);
  assert.equal(c.inIRQ,false);assert.equal(c.irqCount,0);assert.equal(c.frameCount,0);
  assert.equal(phase(c).active,0);assert.equal(c.state().resetCount,1);retired(c,1);
});
