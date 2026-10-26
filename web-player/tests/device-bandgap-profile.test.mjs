import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

// Exercise the real native admission API with caller-owned sentinel memories.
// This is the selected shared-reference fixture, not a silicon startup curve.
const create=compileAnalog('device-bandgap-profile',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.h"
#include "analog_comparator.h"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
int timing(int field,uint32_t value) {return device_configure_bandgap(field,value);}
int comparator(int field,uint32_t value) {return device_configure_comparator(field,value);}
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
int enabled(void) {return device_bandgap_enabled();}
int ready(void) {return device_bandgap_ready();}
uint64_t deadline(void) {return device_bandgap_deadline_ps();}
int acquire(void) {device_write(ANALOG_ACSR,ANALOG_ACBG,255);return !device_fault();}
int fault(void) {return device_fault();}
int detail(void) {return device_fault_detail();}
`);
const max=0xffffffffffffffffn;
const deadline=c=>BigInt.asUintN(64,c.deadline());
function configureComparator(c,startupNs=0){
  assert.equal(c.comparator(1,37),1);assert.equal(c.comparator(2,startupNs),1);assert.equal(c.comparator(0,1),1);
}
function configureBandgap(c,startupNs=37){assert.equal(c.timing(1,startupNs),1);assert.equal(c.timing(0,1),1);}
function rejected(c,detail=17){
  assert.equal(c.init(),0);assert.equal(c.fault(),1);assert.equal(c.detail(),detail);
  assert.equal(c.untouched(),1,'Rejected profile must not modify caller data, Flash or EEPROM');
}

test('native shared profile rejects missing explicit startup before touching caller memory',()=>{
  const c=create();assert.equal(c.source(0),1);configureComparator(c);assert.equal(c.timing(0,1),1);
  rejected(c);
  assert.equal(c.timing(1,0),1);assert.equal(c.init(),1);assert.equal(c.fault(),0);
});

test('nonphysical comparator/shared profile retains the earlier comparator detail16 precedence',()=>{
  const c=create();configureComparator(c);configureBandgap(c);
  rejected(c,16);
});

test('native shared profile requires an explicit physical comparator profile',()=>{
  const c=create();assert.equal(c.source(0),1);configureBandgap(c);rejected(c);
});

test('native shared profile rejects a second comparator-local reference startup',()=>{
  const c=create();assert.equal(c.source(0),1);configureComparator(c,83);configureBandgap(c);rejected(c);
});

for(const key of [9,10])test(`mixed legacy half-clock field${key} retains comparator admission precedence`,()=>{
  const c=create();assert.equal(c.source(0),1);configureComparator(c);configureBandgap(c);
  assert.equal(c.legacy(key,1),1);rejected(c,16);
});

for(const clki of [0,1])for(const startupNs of [0,0xffffffff])
test(`native ${clki?'CLKI':'OSCCAL'} shared profile accepts explicit startup${startupNs} and rejects reconfiguration`,()=>{
  const c=create();assert.equal(c.source(clki),1);configureComparator(c);configureBandgap(c,startupNs);
  assert.equal(c.init(),1);assert.equal(c.fault(),0);assert.equal(c.enabled(),1);
  assert.equal(deadline(c),max);assert.equal(c.ready(),0,'Ownerless profile is not ready');
  assert.equal(c.acquire(),1);assert.equal(c.ready(),startupNs===0?1:0);
  const expectedDeadline=startupNs?BigInt(startupNs)*1000n:max;
  assert.equal(deadline(c),expectedDeadline,'uint32 nanoseconds must retain their exact physical deadline');
  assert.equal(c.timing(1,100),0);assert.equal(c.timing(0,0),0);
  assert.equal(c.enabled(),1);assert.equal(deadline(c),expectedDeadline);assert.equal(c.fault(),0);
});

test('native shared disable clears startup presence, including a previous explicit zero',()=>{
  const c=create();assert.equal(c.source(0),1);configureComparator(c);configureBandgap(c,0);
  assert.equal(c.timing(0,0),1);assert.equal(c.timing(0,1),1);rejected(c);
  assert.equal(c.timing(1,0),1);assert.equal(c.init(),1);assert.equal(c.enabled(),1);
});

test('disabled shared profile permits the original nonphysical device configuration',()=>{
  const c=create();configureBandgap(c);assert.equal(c.timing(0,0),1);
  assert.equal(c.init(),1);assert.equal(c.enabled(),0);assert.equal(c.ready(),0);assert.equal(deadline(c),max);
});

test('unknown native fields and nonboolean enable reject without clearing valid startup presence',()=>{
  const c=create();assert.equal(c.source(0),1);configureComparator(c);assert.equal(c.timing(1,0),1);
  assert.equal(c.timing(2,0),0);assert.equal(c.timing(-1,0),0);assert.equal(c.timing(0,2),0);
  assert.equal(c.timing(0,1),1);assert.equal(c.init(),1);assert.equal(c.fault(),0);
});
