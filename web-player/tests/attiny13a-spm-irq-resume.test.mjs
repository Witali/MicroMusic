import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {AT13_MASK as MASK,AT13_VECTOR as VECTOR,AT13_MEMORY as MEMORY} from '../lib/attiny13a-registers.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const {ATtiny13A}=await import(process.env.MICROMUSIC_DEVICE_MODULE?
  pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE).href:new URL('../lib/attiny13a.js',import.meta.url).href);
const finished=4500000000n;
const image=flash({instructions:[[0x95e8],avr.rjmp(1,1)]},
  {at:VECTOR.TIM0_OVF,instructions:[avr.rjmp(VECTOR.TIM0_OVF,64)]},
  {at:64,instructions:[avr.inc(24),avr.reti()]},{at:128,instructions:[avr.ldi(19,0x99)]});
function paused(incrementalCompilation,cycles=0,pageHigh=1){
  const c=new ATtiny13A(image,null,{resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fuseHigh:0xef,
    spmCommandCycles:1,nvmClockProfile:1,nvmCalibrationReferenceHz:hz,incrementalCompilation});
  c.r[31]=pageHigh;c.writeIO(IO.TIMSK0,MASK.TOIE0);c.writeIO(IO.TCCR0B,1);c.sreg=MASK.SREG_I;
  c.debugEnabled=true;c.eeprom[3]=0x63;c.writeIO(IO.SPMCSR,3);
  assert.equal(c.runUntilPs(finished+BigInt(cycles)*1000000n+1n),1);
  const state=c.state();assert.equal(state.cpuPhase.active,2);assert.equal(state.cpuPhase.stage,cycles===0?0:cycles===2?1:2);
  assert.equal(state.cpuPhase.retired,1n);assert.equal(state.irqs,0);assert.equal(c.pc,1);
  assert.equal(c._exports.avr_device_generation(),1n);assert.equal(c._generation,0n);
  return c;
}
for(const incrementalCompilation of [false,true])for(const cycles of [0,2,3])for(const entry of ['step','run1','run2'])
  test(`SPM/IRQ continuation resumes ${entry} after C${cycles}, incremental${incrementalCompilation}`,()=>{
    const c=paused(incrementalCompilation,cycles),before=c.cyc;
    const count=entry==='run2'?2:1;
    if(entry==='step')assert.equal(c.step(),undefined);else assert.equal(c.run(count),count);
    const state=c.state();assert.equal(state.cpuPhase.retired,1n+BigInt(count));assert.equal(state.cpuPhase.active,0);
    assert.equal(c.pc,count===1?64:65);assert.equal(c.r[24],count===1?0:1);
    assert.equal(c.cyc-before,4-cycles+2+(count===2?1:0),'Only remaining IRQ cycles plus requested instructions');
    assert.equal(state.timePs,finished+BigInt(6+(count===2?1:0))*1000000n,'Retain the source phase across the 1ps observation');
    assert.equal(state.irqs,1);assert.equal(c.sp,MEMORY.RAMEND-2);
    assert.equal(c.data[MEMORY.RAMEND],1);assert.equal(c.data[MEMORY.RAMEND-1],0);
    assert.equal(c._generation,1n);assert.equal(c.debugEnabled,true);assert.equal(c.eeprom[3],0x63);
    assert.equal(state.deviceFault,0);
  });

for(const incrementalCompilation of [false,true])for(const entry of ['step','run'])
  test(`erased IRQ-vector code faults on this ${entry} call, incremental${incrementalCompilation}`,()=>{
    const c=paused(incrementalCompilation,0,0);
    assert.throws(()=>entry==='step'?c.step():c.run(1),/Unsupported opcode at 0x6/);
    const state=c.state();assert.equal(state.cpuPhase.retired,1n);assert.equal(state.cpuPhase.execPc,VECTOR.TIM0_OVF);
    assert.equal(state.irqs,1);assert.equal(c._generation,1n);assert.equal(c.error,2);
    assert.equal(c.sp,MEMORY.RAMEND-2);assert.equal(c.r[24],0);assert.equal(state.deviceFault,0);
  });

for(const incrementalCompilation of [false,true])test(`run(0) does not finish a paused SPM/IRQ entry, incremental${incrementalCompilation}`,()=>{
  const c=paused(incrementalCompilation),before=c.state(),data=c.data.slice(),module=c._translatedModule;
  assert.equal(c.run(0),0);assert.deepEqual(c.state(),before);assert.deepEqual(c.data,data);
  assert.equal(c._generation,0n);assert.equal(c._translatedModule===module,true);
});

for(const incrementalCompilation of [false,true])for(const entry of ['step','run'])
  test(`RESET cancels the paused SPM/IRQ during ${entry}, incremental${incrementalCompilation}`,()=>{
    const c=paused(incrementalCompilation);c.injectPinsPs({at:finished+500000n,mask:32,levels:0});
    if(entry==='step')c.step();else assert.equal(c.run(1),0);
    const state=c.state();assert.equal(state.cpuPhase.retired,1n);assert.equal(state.cpuPhase.active,0);
    assert.equal(state.resetCount,1);assert.equal(state.resetHeld,true);assert.equal(state.irqs,0);
    assert.equal(c.pc,0);assert.equal(c.sp,MEMORY.RAMEND);assert.equal(c.r[24],0);
    assert.equal(state.timePs,finished+500000n);assert.equal(state.deviceFault,0);
  });
