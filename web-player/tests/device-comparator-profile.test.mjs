import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('device-comparator-profile',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
int timing(int field,uint32_t value) {return device_configure_comparator(field,value);}
int legacy(int key,uint32_t value) {return device_configure(key,value);}
int source(int clki) {
 if(!device_configure(DEVICE_CFG_OSCILLATOR_HZ,1000000))return 0;
 if(clki)return device_configure(DEVICE_CFG_FUSE_LOW,0x70)&&device_configure_clki(1,0)&&device_configure_clki(0,1);
 return device_configure_osccal_hz(0,1000000);
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
int fault(void) {return device_fault();}
int detail(void) {return device_fault_detail();}
`);
function configure(c){assert.equal(c.timing(1,200),1);assert.equal(c.timing(2,1000),1);assert.equal(c.timing(0,1),1);}
for(const missing of [1,2])test(`native comparator profile rejects missing field${missing} before touching caller memory`,()=>{
  const c=create();assert.equal(c.source(0),1);assert.equal(c.timing(3-missing,0),1);assert.equal(c.timing(0,1),1);
  assert.equal(c.init(),0);assert.equal(c.fault(),1);assert.equal(c.detail(),16);assert.equal(c.untouched(),1);
  assert.equal(c.timing(missing,0),1);assert.equal(c.init(),1);assert.equal(c.fault(),0);
});
test('native comparator profile requires a physical source before touching caller memory',()=>{
  const c=create();configure(c);assert.equal(c.init(),0);assert.equal(c.fault(),1);assert.equal(c.detail(),16);assert.equal(c.untouched(),1);
});
for(const key of [9,10])test(`native comparator profile rejects mixed half-clock field${key}`,()=>{
  const c=create();assert.equal(c.source(0),1);configure(c);assert.equal(c.legacy(key,1),1);
  assert.equal(c.init(),0);assert.equal(c.fault(),1);assert.equal(c.detail(),16);assert.equal(c.untouched(),1);
});
for(const clki of [0,1])test(`native comparator profile accepts an explicit ${clki?'CLKI':'OSCCAL'} source and rejects later configuration`,()=>{
  const c=create();assert.equal(c.source(clki),1);configure(c);assert.equal(c.init(),1);assert.equal(c.fault(),0);
  assert.equal(c.timing(1,300),0);assert.equal(c.timing(0,0),0);assert.equal(c.fault(),0);
});
test('native disable clears both presence bits; unknown fields and non-boolean enable are rejected',()=>{
  const c=create();assert.equal(c.source(0),1);configure(c);assert.equal(c.timing(0,0),1);
  assert.equal(c.timing(3,0),0);assert.equal(c.timing(0,2),0);assert.equal(c.timing(0,1),1);
  assert.equal(c.init(),0);assert.equal(c.detail(),16);assert.equal(c.untouched(),1);
});
