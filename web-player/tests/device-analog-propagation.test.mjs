import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

// Compare private analog state against the former six-input board operation,
// including pending zero-delay events that public register reads would settle.
const create=compileAnalog('analog-propagation',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','power_reset',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.c"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
int initialize(int delay,int initial) {
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 device_configure(DEVICE_CFG_FUSE_LOW,0x72);
 device_configure(DEVICE_CFG_COMPARATOR_PROPAGATION,delay);
 device_configure(DEVICE_CFG_COMPARATOR_INITIAL,initial);
 device_configure_osccal_hz(0,9600000);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS);
 device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,9600000);
 const uint32_t power[]={1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000};
 for(unsigned i=0;i<10;i++)if(!device_configure_power(i,power[i]))return 0;
 return device_init(data,flash,eeprom);
}
int check_pins(int levels,int mask,int vcc,int uv0,int uv1,int uv2,int uv3,int uv4,int uv5) {
 const int32_t uv[]={uv0,uv1,uv2,uv3,uv4,uv5};
 board.gpio.pins.levels=levels;board.analog_mask=mask;board.vcc_uv=vcc;
 memcpy(board.analog_uv,uv,sizeof uv);
 analog_t reference;memcpy(&reference,&board.analog,sizeof reference);
 for(unsigned pin=0;pin<6;pin++) {
  int32_t voltage=(mask&(1u<<pin))?uv[pin]:((levels&(1u<<pin))?vcc:0);
  if(!analog_input(&reference,pin,voltage,board.half))return -1;
 }
 pin_voltages();
 return memcmp(&reference,&board.analog,sizeof reference)==0;
}
void cycles(unsigned n) { device_advance(n);device_clear_pin_events(); }
void reset_cpu(void) { device_reset(8);device_clear_pin_events(); }
void write(int io,int value) { device_write(io,value,255); }
int input(int pin,int uv) { return device_inject_analog_ps(board.base,pin,uv); }
int supply(int uv) { return device_inject_vcc_ps(board.base,uv); }
int pin_uv(int pin) { return pin<6?board.analog.comparator.pin_uv[pin]:-1; }
int channel_uv(int channel) { return channel<4?board.analog.adc.channel_uv[channel]:-1; }
int fault(void) { return device_fault(); }
`);
function make(delay=0,initial=0){const c=create();assert.equal(c.initialize(delay,initial),1);return c;}

for(const delay of [0,1,5])for(const initial of [0,1])
test(`changed-only pin propagation matches all six input updates: delay=${delay}, initial=${initial}`,()=>{
  const c=make(delay,initial);let seed=0x138a;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
  // ADC active, comparator ACME enabled, multiple simultaneous voltage changes,
  // zero-time repetitions, gated domains and reset all share this oracle.
  for(let n=0;n<800;n++){
    if(n%71===0)c.reset_cpu();
    if(n%37===0){c.write(IO.PRR,0);c.write(IO.ADMUX,random()&3);c.write(IO.ADCSRB,(random()%7)|(random()&0x40));
      c.write(IO.ADCSRA,[0,0x80,0xc0,0xe0][random()&3]);}
    if(n%29===0)c.write(IO.PRR,random()&3);
    const levels=random()&63,mask=random()&63,vcc=[1800000,3300000,5000000][random()%3];
    const uv=Array.from({length:6},()=>[0,-100,1100000,2500000,5000000][random()%5]);
    assert.equal(c.check_pins(levels,mask,vcc,...uv),1,`new voltages at operation ${n}`);
    assert.equal(c.check_pins(levels,mask,vcc,...uv),1,`unchanged voltages at operation ${n}`);
    c.cycles(random()%4);assert.equal(c.fault(),0);
  }
});

test('GPIO, VCC and explicit analog overrides feed all ADC channels across reset',()=>{
  const c=make();c.write(IO.DDRB,0x1f);c.write(IO.PORTB,0x1f);
  for(let pin=0;pin<5;pin++)assert.equal(c.pin_uv(pin),5000000);
  c.input(2,1234567);c.supply(3300000);
  assert.equal(c.pin_uv(0),3300000);assert.equal(c.pin_uv(2),1234567);
  assert.equal(c.channel_uv(1),1234567);assert.equal(c.channel_uv(3),3300000,'PB3 feeds ADC3');
  c.reset_cpu();
  assert.equal(c.pin_uv(0),0);assert.equal(c.pin_uv(2),1234567);assert.equal(c.channel_uv(1),1234567);
  c.write(IO.DDRB,0x1f);c.write(IO.PORTB,0x1f);
  assert.equal(c.pin_uv(0),3300000);assert.equal(c.pin_uv(2),1234567);
  assert.equal(c.fault(),0);
});
