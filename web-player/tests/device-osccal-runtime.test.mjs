import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('device-osccal-runtime',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
static uint8_t data[160],flash[1024],eeprom[64];
int cfg(int key,int value) { return device_configure(key,value); }
int cal(int value,int hz) { return device_configure_osccal_hz(value,hz); }
void clear(void) { device_clear_osccal_hz(); }
int init(void) { return device_init(data,flash,eeprom); }
int physical(void) { return device_physical_mode(); }
int read_io(int io) { return device_read(io); }
void write_io(int io,int value) { device_write(io,value,255); }
void cycles(int n) { device_advance(n); }
void halves(int n) { device_advance_half(n); }
void enter(void) { device_control(1,0,0); }
void reset(int source) { device_reset(source); }
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
int frequency(void) { return device_oscillator_hz(); }
int divisor(void) { return device_clkpr_divisor(); }
int halted(void) { return device_halted(); }
int phase(void) { return device_sleep_phase(); }
int requested(void) { return device_reset_requested(); }
uint64_t now(void) { return device_time_ps(); }
uint64_t half_deadline(uint64_t n) { return device_cpu_half_deadline_ps(n); }
uint64_t budget(uint64_t at) { return device_cpu_halves_until_ps(at); }
uint64_t sample(uint64_t start,uint64_t frame,int rate) { return device_next_sample_ps(start,frame,rate); }
uint64_t wait_until(uint64_t at) { return device_wait_until_ps(at); }
uint64_t ready(void) { return device_startup_deadline_ps(); }
uint64_t virtual_half(void) { return device_virtual_half(); }
int pins(uint64_t at,int mask,int levels) { return device_inject_digital_ps(at,mask,levels); }
int analog(uint64_t at,int pin,int uv) { return device_inject_analog_ps(at,pin,uv); }
void drain(void) { device_clear_pin_events(); }
int event_count(void) { uint32_t n;device_pin_events_ps(&n);return n; }
uint64_t event_time(int i) { uint32_t n;const device_pin_event_ps_t *p=device_pin_events_ps(&n);return p&&i<(int)n?p[i].time_ps:0; }
int event_levels(int i) { uint32_t n;const device_pin_event_ps_t *p=device_pin_events_ps(&n);return p&&i<(int)n?p[i].levels:0; }
int eeprom_byte(int i) { return eeprom[i]; }
int flash_byte(int i) { return flash[i]; }
uint64_t generation(void) { return device_flash_generation(); }
void spm(int z) { device_control(2,z,0); }
uint64_t legacy(int operation) {
 uint32_t n;
 switch(operation){
 case 0:return device_base_half();case 1:return device_wait_until(1);
 case 2:return device_inject_digital(1,1,1);case 3:return device_inject_analog(1,1,1);
 case 4:device_pin_events(&n);return n;case 5:return device_pin_state()!=0;
 default:return device_startup_deadline();
 }
}
`);
const PS=1000000000000n,ceil=(a,b)=>(a+b-1n)/b;
function board({points=[[0,1000000],[1,1500000],[2,1111111]],fuseLow=0x72,
  fuseHigh=0xef,profile=0,nvmProfile=0,reference=0,frequency=1000000}={}){
  const c=create();
  for(const [key,value] of [[1,frequency],[5,fuseLow],[6,fuseHigh],[17,profile],
    [18,nvmProfile],[19,reference]])assert.equal(c.cfg(key,value),1);
  for(const [cal,hz] of points)assert.equal(c.cal(cal,hz),1);
  assert.equal(c.init(),1);assert.equal(c.physical(),1);return c;
}
function idle(c){c.write_io(0x35,0x20);c.enter();}

test('per-instance table validates all128 slots, missing factory entries and frequency mismatch',()=>{
  const c=create();assert.equal(c.cal(128,1),0);assert.equal(c.cal(-1,1),0);
  assert.equal(c.cal(0,1000000001),0);assert.equal(c.cal(0,-1),0);
  c.cal(1,1000000);assert.equal(c.init(),0);assert.equal(c.detail(),9);
  c.cal(0,1);assert.equal(c.init(),0);assert.equal(c.detail(),10);
  c.cfg(18,1);assert.equal(c.cfg(18,2),0);c.cal(0,9600000);
  assert.equal(c.init(),0);assert.equal(c.detail(),11);
});
test('explicit table enables fixed1ps time; legacy timestamp APIs refuse the mixed contract',()=>{
  for(let operation=0;operation<7;operation++){
    const c=board();assert.equal(c.now(),0n);c.legacy(operation);assert.equal(c.fault(),13);
  }
  const c=board();c.clear();assert.equal(c.physical(),1,'Running instance owns a copied table');
  assert.equal(c.init(),1);assert.equal(c.physical(),0);assert.equal(c.legacy(0),0n);
});
test('all128 nonlinear table entries change frequency without inventing intermediate CAL values',()=>{
  const points=Array.from({length:128},(_,cal)=>[cal,1000000+cal*1000+cal%7]);
  const c=board({points});let at=0n,phase=0n;
  for(const [cal,hz] of points){
    c.write_io(0x31,cal|0x80);assert.equal(c.read_io(0x31),cal);assert.equal(c.frequency(),hz);
    const rate=BigInt(hz)*2n,span=ceil(PS-phase,rate);at+=span;phase+=span*rate-PS;
    assert.equal(c.half_deadline(1n),at);c.halves(1);assert.equal(c.now(),at);
    assert.equal(c.virtual_half(),BigInt(cal+1));assert.equal(c.fault(),0);
  }
  const before=c.now();c.reset(8);assert.equal(c.now(),before);
  assert.equal(c.frequency(),1000000);assert.equal(c.read_io(0x31),0);
  assert.equal(c.half_deadline(1n),before+500000n);
});
test('unprovided CAL remains an explicit error; missing entries never interpolate',()=>{
  const c=board({points:[[0,1000000],[127,2000000]]});c.write_io(0x31,64);
  assert.equal(c.fault(),14);assert.equal(c.detail(),64);assert.equal(c.frequency(),1000000);
  assert.equal(c.read_io(0x31),0);
});
test('clock changes preserve fractional phase and CLKPR state across unrelated input timestamps',()=>{
  const c=board({frequency:999983,points:[[0,999983],[1,1733119]]});
  idle(c);c.wait_until(123456789n);let phase=(123456789n*1999966n)%PS;
  assert.equal(c.virtual_half(),123456789n*1999966n/PS);
  c.write_io(0x31,1);const span=ceil(PS-phase,3466238n);
  assert.equal(c.half_deadline(1n),123456789n+span);
  c.halves(1);assert.equal(c.now(),123456789n+span);
  phase+=span*3466238n-PS;
  assert.equal(c.budget(c.now()),0n);assert.equal(c.budget(c.now()+1n),1n);
  assert.equal(c.budget(c.now()+1000000n),ceil(3466238n*1000000n+phase,PS));
  const divided=board({points:[[0,1000000],[1,2000000]]});
  divided.write_io(0x26,128);divided.write_io(0x26,3);divided.cycles(2);
  assert.equal(divided.divisor(),8);const before=divided.now();divided.write_io(0x31,1);
  assert.equal(divided.divisor(),8);assert.equal(divided.half_deadline(1n),before+2000000n);
});
test('external and128kHz clock sources do not acquire the calibrated RC clock',()=>{
  for(const fuseLow of [0x70,0x73]){
    const c=board({fuseLow,points:[[0,9600000],[1,10000000]]});c.write_io(0x31,1);
    assert.equal(c.frequency(),1000000);c.cycles(10);assert.equal(c.now(),10000000n);
    assert.equal(c.read_io(0x31),1);assert.equal(c.fault(),0);
  }
});
test('Timer0 and ADC retain their instruction-clock state while physical periods change',()=>{
  const c=board();c.analog(0n,2,2500000);c.write_io(0x07,1);c.write_io(0x06,0xc0);
  c.write_io(0x33,1);c.cycles(10);assert.equal(c.read_io(0x32),10);
  c.write_io(0x31,1);c.cycles(41);assert.equal(c.read_io(0x06)&0x10,0);
  assert.equal(c.read_io(0x32),51);c.cycles(1);
  assert.equal(c.now(),38000000n);assert.equal(c.read_io(0x32),52);
  assert.equal(c.read_io(0x06)&0x10,0x10);assert.equal(c.read_io(4),0);
  assert.equal(c.read_io(5),2);assert.equal(c.fault(),0);
});
test('digital injections and physical pin buffer retain exact ps timestamps through calibration',()=>{
  const c=board({frequency:10000000,points:[[0,10000000],[1,17000000]]});c.drain();
  c.pins(12345n,4,4);c.pins(100001n,4,0);c.halves(1);assert.equal(c.now(),50000n);
  c.write_io(0x31,1);c.cycles(2);const events=Array.from({length:c.event_count()},(_,i)=>
    [c.event_time(i),c.event_levels(i)&4]);
  assert.deepEqual(events,[[12345n,4],[100001n,0]]);assert.equal(c.fault(),0);
});
test('watchdog timeout stays at16ms while calibration and CLKPR change',()=>{
  const c=board();c.write_io(0x21,0x40);c.cycles(2000);c.write_io(0x31,1);
  c.write_io(0x26,128);c.write_io(0x26,3);c.cycles(2);idle(c);
  c.wait_until(15999999999n);assert.equal(c.read_io(0x21)&128,0);
  c.wait_until(16000000000n);assert.equal(c.read_io(0x21)&128,128);
  assert.equal(c.fault(),0);
});
test('NVM programming requires a declared calibrated programming clock profile',()=>{
  for(const flash of [false,true]){
    const c=board();c.write_io(0x31,1);
    if(flash){c.write_io(0x37,3);c.spm(0);}
    else{c.write_io(0x1e,0);c.write_io(0x1d,0x5a);c.write_io(0x1c,4);c.write_io(0x1c,2);}
    assert.equal(c.fault(),15);assert.equal(c.eeprom_byte(0),0);assert.equal(c.generation(),0n);
  }
});
test('explicit fixed-ns NVM profile retains EEPROM/Flash wall deadlines across CAL changes',()=>{
  const c=board({nvmProfile:1,reference:1000000});
  c.write_io(0x1e,3);c.write_io(0x1d,0x5a);c.write_io(0x1c,4);c.cycles(1);
  c.write_io(0x1c,2);const at=c.now();c.cycles(100);c.write_io(0x31,1);idle(c);
  c.wait_until(at+3399999999n);assert.equal(c.eeprom_byte(3),0);
  c.wait_until(at+3400000000n);assert.equal(c.eeprom_byte(3),0x5a);
  c.reset(2);c.write_io(0x37,3);c.spm(0);const flash=c.now();
  c.wait_until(flash+1000000000n);c.write_io(0x31,2);
  c.wait_until(flash+4499999999n);assert.equal(c.generation(),0n);
  c.wait_until(flash+4500000000n);assert.equal(c.generation(),1n);
  assert.equal(c.flash_byte(0),255);assert.equal(c.fault(),0);
});
test('audio sample deadlines have no CPU-frequency drift and stay exact beyond f64 integer range',()=>{
  const c=board();idle(c);const origin=10000000000000003n;
  assert.equal(c.wait_until(origin),origin);assert.equal(c.now(),origin);
  for(const rate of [44100,48000,96000])for(const frame of [1n,7n,44100n,34359738368n]){
    const expected=origin+frame*PS/BigInt(rate);
    assert.equal(BigInt.asUintN(64,c.sample(origin,frame,rate)),expected);
    c.write_io(0x31,1);assert.equal(BigInt.asUintN(64,c.sample(origin,frame,rate)),expected);
    c.write_io(0x31,0);
  }
  const precise=origin+12345n;c.pins(precise,4,4);assert.equal(c.wait_until(precise),precise);
  assert.equal(c.event_time(c.event_count()-1),precise);assert.equal(c.fault(),0);
});
test('physical fuse startup and RESET release use source frequency while WDT delay stays wall time',()=>{
  const c=board({profile:1,fuseLow:0x76});assert.equal(c.ready(),4020000000n);
  assert.equal(c.wait_until(c.ready()),4020000000n);c.write_io(0x31,1);
  c.pins(c.now()+123n,32,0);c.cycles(1);const assertion=c.now();assert.equal(c.requested(),2);
  c.reset(2);c.pins(assertion+1234567n,32,32);c.wait_until(assertion+1234567n);
  assert.equal(c.frequency(),1000000,'reset reloads factory calibration');
  const release=c.now(),pulsesLeft=512n*PS-(release*128000n)%PS;
  const expected=release+ceil(pulsesLeft,128000n)+20000000n;
  assert.equal(c.ready(),expected);assert.equal(c.wait_until(expected),expected);
  assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});
