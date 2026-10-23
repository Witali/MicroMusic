import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('device-osccal',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
static uint8_t data[160],flash[1024],eeprom[64];
int configure(int byte) { return device_configure(16,byte); }
int init(int low_fuse) { return device_configure(5,low_fuse)&&device_init(data,flash,eeprom); }
int read_cal(void) { return device_read(0x31); }
void write_cal(int byte,int mask) { device_write(0x31,byte,mask); }
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
void poison(int byte) { data[32+0x31]=byte; }
void reset(int source) { device_reset(source); }
int divisor(void) { return device_clkpr_divisor(); }
int frequency(void) { return device_oscillator_hz(); }
`);

test('factory OSCCAL96 is an explicit seven-bit per-chip parameter',()=>{
  const a=create();assert.equal(a.configure(128),0);assert.equal(a.configure(-1),0);
  for(const byte of [0,1,31,63,96,127]){
    const c=create();assert.equal(c.configure(byte),1);assert.equal(c.init(0x7a),1);
    assert.equal(c.read_cal(),byte);assert.equal(c.fault(),0);
  }
});
test('every reset reloads the9.6MHz byte, independent of selected oscillator/divider',()=>{
  for(const fuse of [0x7a,0x79,0x6a,0x7b,0x78]){
    const c=create();c.configure(73);c.init(fuse);assert.equal(c.read_cal(),73);
    for(const source of [1,2,4,8]){c.poison(12);c.reset(source);assert.equal(c.read_cal(),73);}
    assert.equal(c.frequency(),9600000,'Explicit oscillator contract stays unchanged');
    assert.equal(c.divisor(),fuse===0x6a?8:1);assert.equal(c.fault(),0);
  }
});
test('reserved OSCCAL bit7 always reads zero and writes do not affect CAL',()=>{
  const c=create();c.configure(0x35);c.init(0x7a);
  c.write_cal(0xb5,255);assert.equal(c.read_cal(),0x35);
  c.write_cal(0x80,0x80);assert.equal(c.read_cal(),0x35);
  c.write_cal(0,0x80);assert.equal(c.read_cal(),0x35);assert.equal(c.fault(),0);
  c.poison(0xb5);assert.equal(c.read_cal(),0x35);
});
test('CAL changes still fail explicitly without a calibrated frequency table',()=>{
  const c=create();c.configure(0x35);c.init(0x7a);c.write_cal(0x36,255);
  assert.equal(c.fault(),12);assert.equal(c.detail(),0x31);
  assert.equal(c.read_cal(),0x35);assert.equal(c.frequency(),9600000);
});
