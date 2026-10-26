import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_IO as IO,AT13_MASK as M} from '../lib/attiny13a-registers.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A7.5.3: clear ADEN before setting PRADC. The outcome of
// violating that sequencing requirement is not specified as a paused ADC.
const create=compileAnalog('device-adc-power-sequence',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog',
].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.h"
static uint8_t data[160],flash[1024],eeprom[64];
int init(void) {return device_init(data,flash,eeprom);}
void write(int io,int value,int mask) {device_write(io,value,mask);}
void cycles(int count) {device_advance(count);}
int read(int io) {return device_read(io);}
int raw(int io) {return data[32+io];}
int fault(void) {return device_fault();}
int detail(void) {return device_fault_detail();}
`);
function board(){const c=create();assert.equal(c.init(),1);return c;}
const write=(c,io,value,mask=255)=>c.write(io,value,mask);

for(const phase of ['idle','waiting','converting','completed'])
test(`PRADC rejects ADEN=1 in ${phase} state before changing either PRR bit`,()=>{
  for(const value of [M.PRADC,M.PRADC|M.PRTIM0])for(const masked of [false,true]){
    const c=board();write(c,IO.TCCR0B,1);
    write(c,IO.ADCSRA,M.ADEN|(phase==='idle'?0:M.ADSC));
    c.cycles(phase==='converting'?3:phase==='completed'?60:0);
    const before=Array.from({length:64},(_,i)=>c.raw(i));
    write(c,IO.PRR,value,masked?value:255);
    assert.equal(c.fault(),4);assert.equal(c.detail(),16);
    assert.deepEqual(Array.from({length:64},(_,i)=>c.raw(i)),before,'Reject before timer/ADC/control publication changes');
  }
});

test('legal ADC disable, power gate, ungate and restart retains the first-conversion timing',()=>{
  const c=board();write(c,IO.ADCSRA,M.ADEN|M.ADSC);c.cycles(3);
  write(c,IO.ADCSRA,0);assert.equal(c.raw(IO.ADCSRA)&(M.ADEN|M.ADSC),0);
  write(c,IO.PRR,M.PRADC);c.cycles(200);assert.equal(c.raw(IO.PRR),M.PRADC);
  assert.equal(c.fault(),0);assert.equal(c.raw(IO.ADCSRA)&M.ADIF,0);
  write(c,IO.PRR,0);write(c,IO.ADCSRA,M.ADEN|M.ADSC);
  c.cycles(51);assert.equal(c.raw(IO.ADCSRA)&M.ADIF,0);
  c.cycles(1);assert.equal(c.raw(IO.ADCSRA)&M.ADIF,M.ADIF);assert.equal(c.fault(),0);
});

test('PRTIM0 alone can gate Timer0 during an active ADC conversion',()=>{
  const c=board();write(c,IO.TCCR0B,1);write(c,IO.ADCSRA,M.ADEN|M.ADSC);
  c.cycles(3);const timer=c.raw(IO.TCNT0);write(c,IO.PRR,M.PRTIM0);c.cycles(60);
  assert.equal(c.raw(IO.TCNT0),timer);assert.equal(c.raw(IO.ADCSRA)&M.ADIF,M.ADIF);
  assert.equal(c.fault(),0);
});

test('already disabled ADC can be power gated despite ADATE, ADIE, ADIF and prescaler state',()=>{
  for(const pending of [false,true])for(const value of [0,M.ADIE|M.ADATE|7]){
    const c=board();
    if(pending){write(c,IO.ADCSRA,M.ADEN|M.ADSC);c.cycles(52);}
    write(c,IO.ADCSRA,value);assert.equal(c.raw(IO.ADCSRA)&M.ADIF,pending?M.ADIF:0);
    const control=c.raw(IO.ADCSRA);write(c,IO.PRR,M.PRADC|M.PRTIM0);
    assert.equal(c.raw(IO.PRR),M.PRADC|M.PRTIM0);assert.equal(c.fault(),0);
    assert.equal(c.raw(IO.ADCSRA),control,'Gating does not acknowledge ADIF or change stored controls');
  }
});

const code=sequential([avr.ldi(16,M.ADEN),avr.out(IO.ADCSRA,16),
  avr.ldi(16,M.PRADC),avr.out(IO.PRR,16),avr.ldi(20,0xa5)]);
const table=Array(128).fill(0);table[0]=1000000;
for(const [name,options] of [
  ['compatible',{}],
  ['physical',{oscillatorHz:1000000,osccalHz:table,resumable:true,fuseLow:0x72}],
  ['CLKI',{resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}],
])test(`generated ${name} CPU stops at the invalid PRADC bus write`,()=>{
  const c=new ATtiny13A(code,null,options);
  if(name==='CLKI'){
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,
      highPs:500000n,lowPs:500000n,transitionCount:100n,knownUntilPs:50000000n}),true);
    assert.throws(()=>c.runUntilPs(10000000n),/peripheral fault 4, detail 16/);
  }else{
    for(let n=0;n<3;n++)c.step();
    assert.throws(()=>c.step(),/peripheral fault 4, detail 16/);
  }
  assert.equal(c.data[32+IO.PRR],0);assert.equal(c.data[32+IO.ADCSRA]&M.ADEN,M.ADEN);
  assert.equal(c.r[20],0);assert.equal(c.state().deviceFault,4);
});
