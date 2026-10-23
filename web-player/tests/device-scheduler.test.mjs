import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const make=compileAnalog('device-scheduler',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','device-test',
].map(name=>`web-player/native/peripherals/${name}.c`),'');
const cases=['masked bus','physical PWM pins','external T0','IRQ routing',
  'ADC result locks','ADC auto triggers','Idle sleep','Power-down watchdog',
  'CLKPR phase and window','EEPROM wall time','Flash generation and stalls',
  'asynchronous reset','bounded buffer diagnostics','external RESET hold/release',
  'NVM during RESET hold','RSTDISBL GPIO and ADC0'];
for(const [index,name] of cases.entries())test('connected C scheduler: '+name,()=>{
  assert.equal(make().device_test_case(index),0,'C fixture failure line');
});
