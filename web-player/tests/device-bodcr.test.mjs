import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('device-bodcr',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
static uint8_t data[160], flash[1024], eeprom[64];
int init(int fuse_low,int fuse_high,int recovery_ns,int startup,int oscillator) {
 if (!device_configure(1,oscillator)||!device_configure(5,fuse_low)||
     !device_configure(6,fuse_high)||!device_configure(12,startup)||
     !device_configure(15,recovery_ns)) return 0;
 return device_init(data,flash,eeprom);
}
int read_io(int io) { return device_read(io); }
void write_io(int io,int v,int mask) { device_write(io,v,mask); }
void cycles(int n) { device_advance(n); }
void enter(void) { device_control(1,0,0); }
int phase(void) { return device_sleep_phase(); }
int disabled(void) { return device_bod_disabled(); }
int recovering(void) { return device_bod_recovering(); }
int fault(void) { return device_fault(); }
uint64_t now(void) { return device_base_half(); }
uint64_t wait_until(uint64_t t) { return device_wait_until(t); }
int pins(uint64_t at,int mask,int levels) { return device_inject_digital(at,mask,levels); }
void reset(void) { device_reset(8); }
`);
function board({fuseLow=0x7a,fuseHigh=0xfd,recovery=60000,startup=0,oscillator=9600000}={}){
  const c=create();assert.equal(c.init(fuseLow,fuseHigh,recovery,startup,oscillator),1);return c;
}
const write=(c,value,mask=255)=>c.write_io(0x30,value,mask);
function prepareSleep(c,mode=2){
  c.pins(c.now(),2,2); // INT0 high; no pending level-triggered wake yet.
  c.write_io(0x3b,0x40,255);c.write_io(0x35,0x20|(mode<<3),255);
}
function commit(c){write(c,3);c.cycles(1);write(c,2);}
function sleep(c){c.cycles(1);c.enter();}
function wakeAt(c,when){assert.equal(c.pins(when,2,0),1);c.wait_until(when);}

test('BODCR reset/reserved masks and unarmed BODS writes',()=>{
  const c=board();assert.equal(c.read_io(0x30),0);write(c,0xfc);assert.equal(c.read_io(0x30),0);
  write(c,2);assert.equal(c.read_io(0x30),0);assert.equal(c.disabled(),0);assert.equal(c.fault(),0);
});
test('BODCR first write arms four cycles; BODS readback clears after three',()=>{
  const c=board();write(c,3);assert.equal(c.read_io(0x30),3);
  c.cycles(2);assert.equal(c.read_io(0x30),3);
  c.cycles(1);assert.equal(c.read_io(0x30),1);
  write(c,2);assert.equal(c.read_io(0x30),2); // Valid second write in fourth cycle.
  c.cycles(2);assert.equal(c.read_io(0x30),2);
  c.cycles(1);assert.equal(c.read_io(0x30),0);
});
test('late second write and BODSE-only sequence do not authorize sleep disable',()=>{
  for(const first of [1,3]){
    const c=board();prepareSleep(c);write(c,first);c.cycles(first===3?4:1);write(c,2);
    assert.equal(c.read_io(0x30),0);sleep(c);assert.equal(c.disabled(),0);assert.equal(c.fault(),0);
  }
});
test('writes targeting only reserved bits do not rearm the protection window',()=>{
  const c=board();prepareSleep(c);write(c,3);c.cycles(2);write(c,0xfc,0xfc);
  c.cycles(2);write(c,2);sleep(c);assert.equal(c.disabled(),0);assert.equal(c.fault(),0);
});
test('first write without commit and expired committed window leave BOD enabled',()=>{
  const a=board();prepareSleep(a);write(a,3);sleep(a);assert.equal(a.disabled(),0);
  const b=board();prepareSleep(b);commit(b);b.cycles(2);sleep(b);
  assert.equal(b.read_io(0x30),0);assert.equal(b.disabled(),0);
});
test('valid sequence disables only fuse-enabled BOD in Power-down',()=>{
  for(const fuseHigh of [0xff,0xfd,0xfb,0xf9])for(const mode of [0,1,2]){
    const c=board({fuseHigh});prepareSleep(c,mode);commit(c);sleep(c);
    assert.equal(c.disabled(),Number(fuseHigh!==0xff&&mode===2));
    assert.equal(c.phase(),1);assert.equal(c.fault(),0);
  }
});
test('sleep latches disable independently of later BODS auto-clear',()=>{
  const c=board();prepareSleep(c);commit(c);sleep(c);c.wait_until(c.now()+100n);
  assert.equal(c.read_io(0x30),0);assert.equal(c.disabled(),1);assert.equal(c.phase(),1);
  const wake=c.now()+2n;wakeAt(c,wake);assert.equal(c.disabled(),0);assert.equal(c.recovering(),1);
});
test('default approximate60us recovery is wall time and independent of CKDIV8',()=>{
  for(const fuseLow of [0x7a,0x6a]){
    const c=board({fuseLow});prepareSleep(c);commit(c);sleep(c);assert.equal(c.disabled(),1);
    const wake=c.now()+2n;wakeAt(c,wake);
    assert.equal(c.disabled(),0);assert.equal(c.recovering(),1);assert.equal(c.phase(),2);
    c.wait_until(wake+1151n);assert.equal(c.recovering(),1);assert.equal(c.phase(),2);
    c.wait_until(wake+1152n);assert.equal(c.recovering(),0);assert.equal(c.phase(),3);
    const extra=fuseLow===0x6a?64n:8n;
    c.wait_until(wake+1152n+extra);assert.equal(c.phase(),0);assert.equal(c.fault(),0);
  }
});
test('BOD recovery uses explicit duration and rounds up in fixed oscillator domain',()=>{
  const c=board({oscillator:1000000,recovery:60001});prepareSleep(c);commit(c);sleep(c);
  const wake=c.now()+2n;wakeAt(c,wake);c.wait_until(wake+120n);
  assert.equal(c.recovering(),1);c.wait_until(wake+121n);assert.equal(c.recovering(),0);
  c.wait_until(wake+129n);assert.equal(c.phase(),0);
});
test('longer caller startup overlaps recovery, and explicit zero recovery is supported',()=>{
  const c=board({startup:2000});prepareSleep(c);commit(c);sleep(c);
  const wake=c.now()+2n;wakeAt(c,wake);c.wait_until(wake+1152n);
  assert.equal(c.recovering(),0);assert.equal(c.phase(),2);
  c.wait_until(wake+2000n);assert.equal(c.phase(),3);c.wait_until(wake+2008n);assert.equal(c.phase(),0);
  const d=board({recovery:0});prepareSleep(d);commit(d);sleep(d);
  const at=d.now()+2n;wakeAt(d,at);assert.equal(d.recovering(),0);assert.equal(d.phase(),3);
  d.wait_until(at+8n);assert.equal(d.phase(),0);
});
test('fuse-disabled BOD and other sleep modes do not acquire recovery delay',()=>{
  for(const [fuseHigh,mode] of [[0xff,2],[0xfd,0],[0xfd,1]]){
    const c=board({fuseHigh});prepareSleep(c,mode);commit(c);sleep(c);
    const wake=c.now()+2n;wakeAt(c,wake);assert.equal(c.disabled(),0);assert.equal(c.recovering(),0);
    c.wait_until(wake+8n);assert.equal(c.phase(),0);assert.equal(c.fault(),0);
  }
});
test('reset clears controls, latched disable and recovery; masked writes preserve unselected bits',()=>{
  const c=board();prepareSleep(c);write(c,3);write(c,0,1);assert.equal(c.read_io(0x30),2);
  sleep(c);assert.equal(c.disabled(),1);c.reset();
  assert.equal(c.read_io(0x30),0);assert.equal(c.disabled(),0);assert.equal(c.recovering(),0);
  prepareSleep(c);commit(c);sleep(c);const wake=c.now()+2n;wakeAt(c,wake);
  assert.equal(c.recovering(),1);c.reset();assert.equal(c.recovering(),0);assert.equal(c.phase(),0);
});
