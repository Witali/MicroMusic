import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('device-startup',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
static uint8_t data[160],flash[1024],eeprom[64];
int configure(int key,int value) { return device_configure(key,value); }
int init(void) { return device_init(data,flash,eeprom); }
int read_io(int io) { return device_read(io); }
void write_io(int io,int value) { device_write(io,value,255); }
void cycles(int n) { device_advance(n); }
void enter(void) { device_control(1,0,0); }
int phase(void) { return device_sleep_phase(); }
int halted(void) { return device_halted(); }
int starting(void) { return device_starting(); }
int held(void) { return device_reset_held(); }
int requested(void) { return device_reset_requested(); }
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
uint64_t now(void) { return device_base_half(); }
uint64_t ready(void) { return device_startup_deadline(); }
uint64_t wait_until(uint64_t t) { return device_wait_until(t); }
int pins(uint64_t at,int mask,int levels) { return device_inject_digital(at,mask,levels); }
void reset(int source) { device_reset(source); }
int eeprom_byte(int address) { return eeprom[address]; }
int flash_byte(int address) { return flash[address]; }
uint64_t generation(void) { return device_flash_generation(); }
void spm(int address) { device_control(2,address,0); }
`);
function board({profile=1,fuseLow=0x72,fuseHigh=0xff,oscillator=1000000,watchdog=128000,
  manualStartup=0}={}){
  const c=create();
  for(const [key,value] of [[1,oscillator],[2,watchdog],[5,fuseLow],[6,fuseHigh],
    [12,manualStartup],[17,profile]])assert.equal(c.configure(key,value),1);
  assert.equal(c.init(),1);return c;
}
function finishReset(c){const at=c.ready();c.wait_until(at);assert.equal(c.now(),at);
  assert.equal(c.starting(),0);assert.equal(c.halted(),0);assert.equal(c.fault(),0);return at;}
function resetDeadline(now,{oscillator=1000000,watchdog=128000,pulses=0,wdt=false}={}){
  const frequency=BigInt(oscillator)*2n,rate=BigInt(watchdog),pulse=wdt?2n:0n;
  const phase=((now+pulse)*rate)%frequency;
  const delay=pulses?(BigInt(pulses)*frequency-phase+rate-1n)/rate:0n;
  return now+pulse+delay+40n;
}

test('default zero-startup digital fixture remains available; profile accepts only0/1',()=>{
  const untouched=create();assert.equal(untouched.init(),1);assert.equal(untouched.halted(),0);
  assert.equal(untouched.ready(),0n);assert.equal(untouched.configure(17,2),0);
  assert.equal(untouched.configure(17,-1),0);
  const off=board({profile:0,fuseLow:0x7e});assert.equal(off.halted(),0);
  off.reset(8);assert.equal(off.starting(),0);assert.equal(off.ready(),off.now());
});
test('enabled profile rejects reserved SUT11 on all clock sources',()=>{
  for(let source=0;source<4;source++){
    const c=create();c.configure(17,1);c.configure(5,0x7c|source);
    assert.equal(c.init(),0);assert.equal(c.fault(),1);assert.equal(c.detail(),8);
  }
});
test('all CKSEL sources use6CK startup plus14CK reset; CKDIV8 does not stretch source CK',()=>{
  for(const source of [0,1,2,3])for(const divided of [false,true]){
    const c=board({fuseLow:(divided?0x60:0x70)|source});
    assert.equal(c.ready(),40n);assert.equal(c.starting(),1);assert.equal(c.halted(),1);
    c.cycles(10);assert.equal(c.now(),0n,'CPU cannot charge instructions during reset stretch');
    c.write_io(0x17,63);assert.equal(c.read_io(0x17),0,'I/O writes remain held reset');
    c.wait_until(39n);assert.equal(c.starting(),1);assert.equal(c.halted(),1);
    finishReset(c);assert.equal(c.now(),40n);
  }
});
test('SUT01/10 count512/8192 independent watchdog pulses, not hardcoded milliseconds',()=>{
  for(const [sut,pulses] of [[1,512],[2,8192]])for(const watchdog of [64000,128000,173111]){
    const c=board({fuseLow:0x72|(sut<<2),watchdog});
    const expected=resetDeadline(0n,{pulses,watchdog});assert.equal(c.ready(),expected);
    c.wait_until(expected-1n);assert.equal(c.starting(),1);finishReset(c);
  }
});
test('RSTDISBL raises only internal-source SUT00 reset timeout to512 watchdog pulses',()=>{
  for(const source of [0,1,2,3]){
    const c=board({fuseLow:0x70|source,fuseHigh:0xfe});
    assert.equal(c.ready(),source?8040n:40n);finishReset(c);
  }
});
test('reset deadlines retain asynchronous watchdog phase across repeated resets',()=>{
  const options={oscillator:999983,watchdog:123457,pulses:512};
  const c=board({...options,fuseLow:0x76});finishReset(c);c.cycles(7);
  for(const source of [1,2,4,8]){
    const now=c.now();c.reset(source);
    assert.equal(c.ready(),resetDeadline(now,{...options,wdt:source===8}));finishReset(c);
    c.cycles(3);
  }
});
test('external RESET starts timeout on release and reassertion restarts it',()=>{
  const c=board({fuseLow:0x76});finishReset(c);const first=c.now()+3n;
  c.pins(first,32,0);c.cycles(4);assert.equal(c.now(),first);assert.equal(c.requested(),2);
  c.reset(2);assert.equal(c.held(),1);assert.equal(c.starting(),0);
  assert.equal(BigInt.asUintN(64,c.ready()),0xffffffffffffffffn);
  const release=first+200n;c.pins(release,32,32);c.wait_until(release);
  assert.equal(c.held(),0);assert.equal(c.starting(),1);
  assert.equal(c.ready(),resetDeadline(release,{pulses:512}));
  const reassert=release+9n;c.pins(reassert,32,0);c.wait_until(reassert+100n);
  assert.equal(c.now(),reassert);assert.equal(c.requested(),2);c.reset(2);
  const again=reassert+50n;c.pins(again,0,0);c.wait_until(again);
  assert.equal(c.ready(),resetDeadline(again,{pulses:512}));finishReset(c);
});
test('watchdog reset adds one sourceCK pulse and watchdog counter remains reset through startup',()=>{
  const c=board({fuseLow:0x5a}); // WDTON programmed, SUT10, no CKDIV8.
  finishReset(c);assert.equal(c.requested(),0);assert.equal(c.read_io(0x21)&8,8);
  c.cycles(16000);assert.equal(c.requested(),8);const at=c.now();c.reset(8);
  assert.equal(c.ready(),resetDeadline(at,{pulses:8192,wdt:true}));
  finishReset(c);assert.equal(c.requested(),0);assert.equal(c.read_io(0x34)&8,8);
  const numerator=2048n*2000000n-(c.now()*128000n)%2000000n;
  const timeout=(numerator+127999n)/128000n;
  c.cycles(Number((timeout-1n)/2n));assert.equal(c.requested(),0);
  c.cycles(1);assert.equal(c.requested(),8);
});
test('already-active EEPROM programming completes while CPU is held in fuse startup',()=>{
  const c=board({fuseLow:0x7a});finishReset(c);
  c.write_io(0x1e,4);c.write_io(0x1d,0x5a);c.write_io(0x1c,4);c.cycles(1);
  c.write_io(0x1c,2);const at=c.now();c.reset(2);assert.equal(c.starting(),1);
  c.wait_until(at+6799n);assert.equal(c.eeprom_byte(4),0);assert.equal(c.starting(),1);
  c.wait_until(at+6800n);assert.equal(c.eeprom_byte(4),0x5a);assert.equal(c.starting(),1);
  finishReset(c);
});
test('already-active Flash erase preserves its deadline and invalidation during reset startup',()=>{
  const c=board({fuseLow:0x7a,fuseHigh:0xef});finishReset(c);
  c.write_io(0x37,3);c.spm(0);const at=c.now();c.reset(2);
  c.wait_until(at+8999n);assert.equal(c.flash_byte(0),0);assert.equal(c.generation(),0n);
  c.wait_until(at+9000n);assert.equal(c.flash_byte(0),255);assert.equal(c.generation(),1n);
  assert.equal(c.starting(),1);finishReset(c);
});
test('Power-down adds6sourceCK wake startup; Idle and ADC noise modes retain their oscillator',()=>{
  for(const fuseLow of [0x72,0x62,0x7a])for(const mode of [0,1,2]){
    const c=board({fuseLow});finishReset(c);
    c.pins(c.now(),2,2);c.write_io(0x3b,0x40);c.write_io(0x35,0x20|(mode<<3));
    c.cycles(1);c.enter();assert.equal(c.phase(),1);
    const at=c.now()+3n;c.pins(at,2,0);c.wait_until(at);assert.equal(c.phase(),mode===2?2:3);
    const startup=mode===2?12n:0n,extra=fuseLow===0x62?64n:8n;
    if(startup){c.wait_until(at+startup-1n);assert.equal(c.phase(),2);
      c.wait_until(at+startup);assert.equal(c.phase(),3);}
    c.wait_until(at+startup+extra-1n);assert.equal(c.halted(),1);
    c.wait_until(at+startup+extra);assert.equal(c.halted(),0);assert.equal(c.fault(),0);
  }
});
test('explicit longer wake startup overlaps fuse startup and reset interrupts Power-down',()=>{
  const c=board({manualStartup:50});finishReset(c);
  c.pins(c.now(),2,2);c.write_io(0x3b,0x40);c.write_io(0x35,0x30);c.enter();
  const at=c.now()+5n;c.pins(at,2,0);c.wait_until(at+12n);assert.equal(c.phase(),2);
  c.wait_until(at+50n);assert.equal(c.phase(),3);c.wait_until(at+58n);assert.equal(c.phase(),0);
  c.pins(c.now(),2,2);c.enter();assert.equal(c.phase(),1);
  c.reset(8);assert.equal(c.phase(),0);assert.equal(c.starting(),1);finishReset(c);
});
test('BOD recovery overlaps the6CK fuse wake startup before the four CPU cycles',()=>{
  const c=board({fuseHigh:0xfd});finishReset(c);
  c.pins(c.now(),2,2);c.write_io(0x3b,0x40);c.write_io(0x35,0x30);
  c.write_io(0x30,3);c.cycles(1);c.write_io(0x30,2);c.cycles(1);c.enter();
  const at=c.now()+5n;c.pins(at,2,0);c.wait_until(at+119n);assert.equal(c.phase(),2);
  c.wait_until(at+120n);assert.equal(c.phase(),3);
  c.wait_until(at+128n);assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});
