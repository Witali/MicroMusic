import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('all-peripherals',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "timer0.h"
#include "system_gpio.h"
#include "system_watchdog.h"
#include "system_sleep.h"
#include "nvm.h"
#include "analog.h"

static timer0_t timer;
static system_gpio_t gpio;
static system_watchdog_t watchdog;
static system_sleep_t sleep;
static attiny13a_nvm_t nvm;
static analog_t analog;
static timer0_event_t events[16];
static uint8_t flash[1024], eeprom[64];

int linked_reset(void) {
  flash[0]=0xab; eeprom[0]=0xcd;
  timer0_init(&timer,events,16,0);
  system_gpio_reset(&gpio,1);
  system_watchdog_init(&watchdog,0);
  system_sleep_reset(&sleep,0);
  analog_comparator_config_t config={2,20,0,0};
  analog_reset(&analog,5000000,1100000,27,&config,0);
  nvm_timing_t timing=nvm_datasheet_timing(1);
  return nvm_init(&nvm,flash,eeprom,&timing,0x6a,0xff,0xff);
}
int linked_initial_state(void) {
  return flash[0]==0xab && eeprom[0]==0xcd && timer.count==0 &&
    system_gpio_pending(&gpio)==0 && system_watchdog_pending(&watchdog)==0 &&
    sleep.phase==SYSTEM_SLEEP_RUNNING && analog_pending(&analog)==0 &&
    nvm_cpu_halted(&nvm)==0;
}
`);

test('all peripheral modules link into one import-free WASM with independent state',()=>{
  const wasm=make();assert.equal(wasm.linked_reset(),1);assert.equal(wasm.linked_initial_state(),1);
  for(const name of ['timer0_advance','system_gpio_advance','system_watchdog_advance',
    'system_sleep_advance','nvm_advance','analog_advance'])assert.equal(typeof wasm[name],'function',name);
});
