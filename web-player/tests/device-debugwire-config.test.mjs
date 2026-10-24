import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {CLKI_PHASE_POLICY} from '../lib/devices/attiny13a-clki-profile.js';
import {compileAnalog} from './analog-test-build.mjs';

// DS40002307A15.3/15.5: DWEN changes PB5 to the debugWIRE gateway,
// and external RESET is unavailable. Until its startup/clock/debug contract
// is implemented, admitting DWEN must not silently execute the RESET model.
const create=compileAnalog('device-debugwire-config',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),String.raw`
#include "device.h"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
int configure(int key,int value) { return device_configure(key,value); }
int select_mode(int mode) {
 if(!device_configure(DEVICE_CFG_OSCILLATOR_HZ,1000000))return 0;
 if(mode==1||mode==3) {
  if(!device_configure_osccal_hz(0,1000000))return 0;
 }
 if(mode==2) {
  if(!device_configure(DEVICE_CFG_FUSE_LOW,0x70)||
     !device_configure_clki(1,1)||!device_configure_clki(0,1))return 0;
 }
 if(mode==3) {
  static const uint32_t fields[]={0,400000,600000,50,30,20,10};
  for(unsigned i=1;i<7;i++)if(!device_configure_reset_input(i,fields[i]))return 0;
  if(!device_configure_reset_input(0,1))return 0;
 }
 return 1;
}
int init(void) {
 memset(data,0xa6,sizeof data);memset(flash,0x5b,sizeof flash);memset(eeprom,0xc3,sizeof eeprom);
 return device_init(data,flash,eeprom);
}
int untouched(void) {
 for(unsigned i=0;i<sizeof data;i++)if(data[i]!=0xa6)return 0;
 for(unsigned i=0;i<sizeof flash;i++)if(flash[i]!=0x5b)return 0;
 for(unsigned i=0;i<sizeof eeprom;i++)if(eeprom[i]!=0xc3)return 0;
 return 1;
}
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
`);

const fuses=[0xf7,0xf6,0xe7,0xe6],locks=[0xff,0xfe,0xfd,0xfc];
for(const [mode,name] of ['compatible clock','physical OSCCAL','external CLKI','analog RESET'].entries()){
  test('native admission rejects unsupported DWEN with '+name,()=>{
    for(const fuseHigh of fuses)for(const lock of locks){
      const c=create(),label=`${name}, high=${fuseHigh.toString(16)}, lock=${lock.toString(16)}`;
      assert.equal(c.select_mode(mode),1,label);
      assert.equal(c.configure(6,fuseHigh),1,label);assert.equal(c.configure(7,lock),1,label);
      assert.equal(c.init(),0,label);assert.equal(c.fault(),1,label);assert.equal(c.detail(),14,label);
      assert.equal(c.untouched(),1,'rejected init must not touch caller memories: '+label);
      assert.equal(c.configure(6,fuseHigh|8),1,label);assert.equal(c.init(),1,label);
      assert.equal(c.fault(),0,'a supported reinitialization clears the fault: '+label);
    }
  });
}

const loop=Uint8Array.of(0xff,0xcf),table=Array(128).fill(1000000);
const receiver={assertThresholdPpm:400000,releaseThresholdPpm:600000,
  assertQualificationNs:50,releaseQualificationNs:30,assertPropagationNs:20,releasePropagationNs:10};
for(const [name,options] of [
  ['compatible clock',{}],
  ['physical OSCCAL',{oscillatorHz:1000000,osccalHz:table}],
  ['external CLKI',{oscillatorHz:1000000,fuseLow:0x70,resumable:true,
    clkiProfile:{phasePolicy:CLKI_PHASE_POLICY,initialLevel:1}}],
  ['analog RESET',{oscillatorHz:1000000,osccalHz:table,resetInputProfile:receiver}],
])test('public runtime rejects DWEN independently of '+name,()=>{
  for(const fuseHigh of fuses)for(const lock of locks)
    assert.throws(()=>new ATtiny13A(loop,null,{...options,fuseHigh,lock}),/DWEN unprogrammed/);
});

test('unprogrammed DWEN retains RESET and RSTDISBL GPIO behavior',()=>{
  const reset=new ATtiny13A(loop,null,{fuseHigh:0xff});
  reset.injectPins({at:0n,mask:32,levels:0});assert.equal(reset.state().resetHeld,true);
  const gpio=new ATtiny13A(loop,null,{fuseHigh:0xfe});
  gpio.injectPins({at:0n,mask:32,levels:0});assert.equal(gpio.state().resetHeld,false);
  gpio.writeIO(0x17,32);gpio.writeIO(0x18,32);
  assert.equal(gpio.state().resetCount,0);
});

test('distributed native runtime enforces DWEN without the JavaScript wrapper',()=>{
  const e=new WebAssembly.Instance(runtimeModule).exports;
  assert.equal(e.avr_device_configure(6,0xf7),1);e.avr_reset(0,0);
  assert.equal(e.avr_device_fault(),1);assert.equal(e.avr_device_fault_detail(),14);
});
