// DS40002307A 5.6.4/16.3: EE_RDY covers NVM readiness; Flash stalls CPU.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {CLKI_PHASE_POLICY} from '../lib/devices/attiny13a-clki-profile.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr} from './helpers/avr-test-state.mjs';

const PS=1000000000000n,issued=17n*PS/1000000n,complete=issued+4500000000n;
const table=Array(128).fill(0);table[0]=1000000;
const policies=[['verification',executionOptions('verification')],['optimized',{
  fastIdle:false,fastBlocks:true,boundedRegions:true,optimizePhaseLocals:true}]];
function snapshot(c,pins){
  const state=c.state();return {data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),
    pc:c.pc,cycles:c.cyc,sp:c.sp,sreg:c.sreg,irqs:state.irqs,cpuPhase:state.cpuPhase,clki:state.clki,pins};
}
function firmware(timerIRQ){
  const binary=flash({instructions:[avr.rjmp(0,16)]},
    {at:3,instructions:[avr.rjmp(3,64),avr.rjmp(4,80)]},
    {at:16,instructions:[avr.ldi(16,1),avr.out(IO.DDRB,16),avr.ldi(16,250),avr.out(IO.TCNT0,16),
      avr.ldi(16,1),avr.out(IO.TCCR0B,16),avr.ldi(16,timerIRQ?MASK.TOIE0:0),avr.out(IO.TIMSK0,16),
      avr.ldi(16,MASK.EERIE),avr.out(IO.EECR,16),avr.ldi(30,0xc0),avr.ldi(31,3),
      avr.ldi(16,3),avr.out(IO.SPMCSR,16),avr.sei(),[0x95e8],avr.inc(18),avr.rjmp(33,33)]},
    {at:64,instructions:[avr.ldi(16,0),avr.out(IO.TIMSK0,16),avr.inc(20),avr.sbi(IO.PINB,0),avr.reti()]},
    {at:80,instructions:[[rr(0x2c00,21,18)],avr.ldi(16,0),avr.out(IO.EECR,16),avr.inc(22),avr.sbi(IO.PINB,0),avr.reti()]});
  binary[960]=0;binary[965]=0x5a;return binary;
}
const make=(timerIRQ,policy,extra={})=>new ATtiny13A(firmware(timerIRQ),null,{
  oscillatorHz:1000000,osccalHz:table,fuseLow:0x72,fuseHigh:0xef,resumable:true,
  nvmClockProfile:1,nvmCalibrationReferenceHz:1000000,spmCommandCycles:1,...policy,...extra});

function busy(c,timerIRQ){
  assert.equal(c.pc,32);assert.equal(c.sp,0x9f);assert.equal(c.state().irqs,0);
  assert.equal(c.state().pendingIRQs&16,0,'EE_RDY must remain suppressed during Flash programming');
  assert.equal(c.state().pendingIRQs&8,timerIRQ?8:0,'Timer0 remains pending while CPU is halted');
  assert.equal(c.readIO(IO.SPMCSR),3);assert.deepEqual(Array.from(c.r.slice(18,23)),[0,0,0,0,0]);
  assert.equal(c._exports.avr_device_generation(),0n);assert.equal(c.rom[960],0);
}
function finished(c,timerIRQ){
  assert.equal(c.r[18],1);assert.equal(c.r[20],Number(timerIRQ));assert.equal(c.r[22],1);
  assert.equal(c.r[21],Number(timerIRQ),'One main instruction follows Timer0 RETI before EE_RDY');
  assert.equal(c.sp,0x9f);assert.equal(c.pc,33);assert.equal(c.state().irqs,timerIRQ?2:1);
  assert.equal(c.readIO(IO.EECR)&MASK.EERIE,0);assert.equal(c.state().pendingIRQs&16,0);
  assert.equal(c._exports.avr_device_generation(),1n);assert.ok(c.rom.slice(960,992).every(b=>b===255));
  assert.equal(c.state().deviceFault,0);
}
for(const timerIRQ of [false,true])
test(`Flash completion, EE_RDY and Timer0 priority, Timer0 enabled=${timerIRQ}`,()=>{
  const states=[];
  for(const [,policy]of policies){
  const c=make(timerIRQ,policy);c.observePins(1);
  c.runUntilPs(complete-1n);assert.equal(c.state().timePs,complete-1n);busy(c,timerIRQ);
  assert.equal(c.drainPinsPs().filter(e=>e.timePs>=issued).length,0,'No ISR output during the Flash stall');
  c.runUntilPs(complete);assert.equal(c._exports.avr_device_generation(),1n);
  assert.equal(c.state().pendingIRQs&16,16,'The NVM ready level returns at the completion timestamp');
  c.runUntilPs(complete+100000000n);finished(c,timerIRQ);
  const pins=c.drainPinsPs();assert.equal(pins.length,timerIRQ?2:1);
  assert.ok(pins.every(e=>e.timePs>complete));
  states.push(snapshot(c,pins));
  }
  assert.deepEqual(...states,'Exact architectural and pin timing parity');
});

function sourceEdges(count,at=0n,level=1){
  return Array.from({length:count},()=>{at+=level?700000n:300000n;level^=1;return {timePs:at,level};});
}
for(const heldLevel of [0,1])
test(`Flash completes while CLKI is held ${heldLevel}; IRQ effects wait for source phases`,()=>{
  const states=[];
  for(const [,policy]of policies){
  const c=make(true,policy,{fuseLow:0x70,clkiProfile:{phasePolicy:CLKI_PHASE_POLICY,initialLevel:1}});
  c.observePins(1);const resumeAt=complete+10000000n;
  const initial=sourceEdges(heldLevel?80:79);assert.equal(initial.at(-1).level,heldLevel);
  assert.equal(c.injectClkiPs({edges:initial,knownUntilPs:resumeAt}),true);
  c.runUntilPs(complete-1n);busy(c,true);
  const retired=c.state().cpuPhase.retired,cycles=c.cyc,timer=c.readIO(IO.TCNT0);assert.equal(typeof retired,'bigint');
  c.runUntilPs(resumeAt);assert.equal(c.state().timePs,resumeAt);
  assert.equal(c._exports.avr_device_generation(),1n);assert.equal(c.state().pendingIRQs&16,16);
  assert.equal(c.cyc,cycles);assert.equal(c.state().cpuPhase.retired,retired);
  assert.equal(c.readIO(IO.TCNT0),timer,'Timer0 receives no clocks during the source hold');
  assert.equal(c.sp,0x9f);assert.equal(c.state().irqs,0);assert.deepEqual(Array.from(c.r.slice(18,23)),[0,0,0,0,0]);
  assert.equal(c.drainPinsPs().filter(e=>e.timePs>=issued).length,0);
  const resumed=sourceEdges(80,resumeAt,heldLevel);
  assert.equal(c.injectClkiPs({edges:resumed,knownUntilPs:resumed.at(-1).timePs}),true);
  c.runUntilPs(resumed.at(-1).timePs);finished(c,true);
  const pins=c.drainPinsPs();assert.equal(pins.length,2);assert.ok(pins.every(e=>e.timePs>resumeAt));
  states.push(snapshot(c,pins));
  }
  assert.deepEqual(...states,'Exact architectural and pin timing parity');
});
