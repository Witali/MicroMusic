import test from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO,AT13_MASK as M} from '../lib/attiny13a-registers.js';

const create=compileAnalog('analog-bandgap-readiness',[
  'web-player/native/peripherals/analog_adc.c','web-player/native/peripherals/analog_comparator.c',
  'web-player/native/peripherals/analog.c'],`
#include "analog.h"
static analog_t a;
void reset(int physical,int propagation) {
  analog_comparator_config_t config={0};analog_reset(&a,5000000,1100000,27,&config,0);
  if(physical)analog_comparator_configure_physical(&a.comparator,propagation,0,0);
}
int adc_ready(int ready) { return analog_adc_bandgap_ready(&a.adc,ready); }
int comparator_ready(int ready,uint64_t half) { return analog_comparator_bandgap_ready(&a.comparator,ready,half); }
int wall(uint64_t ps) { return analog_comparator_advance_ps(&a.comparator,ps); }
int advance(uint64_t half) { return analog_advance(&a,half); }
int write_io(int io,int value,uint64_t half) { return analog_write(&a,io,value,half); }
int read_io(int io,uint64_t half) { uint8_t value=0;return analog_read(&a,io,&value,half)?value:-1; }
int input(int pin,int uv,uint64_t half) { return analog_input(&a,pin,uv,half); }
int reference(int vcc,int bg,uint64_t half) { return analog_reference(&a,vcc,bg,half); }
int sources(int flags,uint64_t half) { return analog_sources(&a,flags,half); }
int ack(int vector,uint64_t half) { return analog_ack(&a,vector,half); }
int adc_clock(int enabled,uint64_t half) { return analog_adc_clock_running(&a.adc,enabled,half); }
uint64_t next_half(void) { return analog_next_event(&a); }
uint64_t next_ps(void) { return analog_comparator_next_event_ps(&a.comparator); }
int value(int field) { switch(field) {
case 0:return a.adc.bandgap_ready;case 1:return a.adc.reference_unsettled;
case 2:return a.adc.result;case 3:return a.adc.sampled_result;case 4:return a.adc.sampled;
case 5:return a.adc.adcsra;case 6:return a.comparator.bandgap_ready;
case 7:return a.comparator.raw;case 8:return a.comparator.sync1;case 9:return a.comparator.acsr;
case 10:return analog_pending(&a);default:return -1; } }
uint64_t detail(int field) { switch(field) {
case 0:return a.adc.conversions;case 1:return a.adc.sampled_at;case 2:return a.adc.completed_at;
case 3:return a.adc.half_cycle;case 4:return a.comparator.half_cycle;
case 5:return a.comparator.transitions;default:return 0; } }
`);
const MAX=0xffffffffffffffffn,u64=x=>BigInt.asUintN(64,x);
const make=(physical=0,propagation=0)=>{const c=create();c.reset(physical,propagation);return c;};
const write=(c,io,v,half=0n)=>assert.equal(c.write_io(io,v,half),1);
const input=(c,pin,uv,half=0n)=>assert.equal(c.input(pin,uv,half),1);
const advance=(c,half)=>assert.equal(c.advance(half),1);
const wall=(c,ps)=>assert.equal(c.wall(ps),1);
const output=c=>!!(c.value(9)&M.ACO);
function start(c,internal=false,half=0n) {
  input(c,5,550000,half);write(c,IO.ADMUX,internal?M.REFS0:0,half);
  write(c,IO.ADCSRA,M.ADEN|M.ADSC,half);
}

test('consumer reset defaults preserve independent legacy reference assumptions',()=>{
  const c=make();assert.equal(c.value(0),1);assert.equal(c.value(1),0);assert.equal(c.value(6),1);
  start(c,true);advance(c,104n);assert.equal(c.value(2),512);assert.equal(c.detail(0),1n);
});
for(const internal of [false,true])test(`${internal?'internal':'VCC'} ADC sampling faults before a fabricated first result when the shared reference is unavailable`,()=>{
  const c=make();assert.equal(c.adc_ready(0),1);start(c,internal);advance(c,57n);
  assert.equal(c.advance(58n),0);assert.equal(c.value(1),1);assert.equal(c.detail(3),58n);
  assert.equal(c.value(4),0);assert.equal(c.detail(0),0n);assert.equal(c.value(2),0);
  assert.equal(c.value(5)&M.ADIF,0);assert.equal(u64(c.next_half()),MAX);
  assert.equal(c.advance(1000000n),0);assert.equal(c.detail(0),0n);
});
for(const internal of [false,true])test(`readiness published before the tied ${internal?'internal':'VCC'} sample allows the original conversion timing`,()=>{
  const c=make();c.adc_ready(0);start(c,internal);advance(c,57n);
  assert.equal(c.adc_ready(1),1);advance(c,58n);assert.equal(c.value(4),1);
  assert.equal(c.detail(1),58n);advance(c,104n);assert.equal(c.detail(2),104n);
  assert.equal(c.detail(0),1n);assert.equal(c.value(2),internal?512:112);assert.equal(c.value(1),0);
});
test('readiness returned after a failed sample cannot resume an invented result; reset clears the diagnostic',()=>{
  const c=make();c.adc_ready(0);start(c,true);assert.equal(c.advance(58n),0);
  assert.equal(c.adc_ready(1),0);assert.equal(c.value(0),1);assert.equal(c.value(1),1);
  assert.equal(c.advance(104n),0);assert.equal(c.detail(0),0n);
  c.reset(0,0);assert.equal(c.value(1),0);start(c,true);advance(c,104n);assert.equal(c.value(2),512);
});
test('a failed later sample retains the prior result and cannot set completion flags or conversions',()=>{
  const c=make();start(c,true);advance(c,104n);assert.equal(c.value(2),512);
  c.adc_ready(0);write(c,IO.ADCSRA,M.ADEN|M.ADSC|M.ADIF,104n);advance(c,113n);
  assert.equal(c.advance(114n),0);assert.equal(c.value(2),512);assert.equal(c.value(3),512);
  assert.equal(c.value(4),0);assert.equal(c.detail(0),1n);assert.equal(c.detail(2),104n);
  assert.equal(c.value(5)&M.ADIF,0);
  for(const call of [()=>c.read_io(IO.ADCL,114n),()=>c.write_io(IO.ADCSRA,0,114n),
    ()=>c.input(5,100000,114n),()=>c.reference(5000000,1100000,114n),
    ()=>c.sources(4,114n),()=>c.ack(9,114n)])assert.ok(call()<=0);
});
test('gated ADC clock does not invent samples while readiness changes independently',()=>{
  const c=make();c.adc_ready(0);assert.equal(c.adc_clock(0,0n),1);start(c,true);
  advance(c,1000n);assert.equal(c.value(1),0);assert.equal(c.detail(0),0n);
  assert.equal(c.adc_ready(1),1);assert.equal(c.adc_clock(1,1000n),1);
  advance(c,1104n);assert.equal(c.value(2),512);assert.equal(c.detail(0),1n);
});
test('an ADC advanced by its clock control is not backdated while the comparator catches up',()=>{
  const c=make();input(c,0,2000000);assert.equal(c.adc_clock(0,10n),1);
  assert.equal(c.detail(3),10n);assert.equal(c.detail(4),0n);
  advance(c,10n);assert.equal(c.detail(3),10n);assert.equal(c.detail(4),10n);
  assert.equal(output(c),true);assert.equal(c.value(1),0);
});
test('an already-advanced comparator does not hide valid ADC events while the ADC catches up',()=>{
  const c=make();start(c,true);assert.equal(c.comparator_ready(1,20n),1);
  assert.equal(c.detail(3),0n);assert.equal(c.detail(4),20n);
  advance(c,104n);assert.equal(c.detail(0),1n);assert.equal(c.value(2),512);
  assert.equal(c.detail(1),58n);assert.equal(c.detail(3),104n);assert.equal(c.detail(4),104n);
});
test('AIN0 comparison stays available while the shared reference is unavailable',()=>{
  const c=make();c.adc_ready(0);assert.equal(c.comparator_ready(0,0n),1);
  input(c,0,2000000);advance(c,4n);assert.equal(output(c),true);assert.equal(c.value(1),0);
});
test('ACBG waits through held wall time, then ordinary propagation and digital synchronization resume',()=>{
  const c=make(1);assert.equal(c.comparator_ready(0,0n),1);
  write(c,IO.ACSR,M.ACBG|M.ACIE);wall(c,10000000n);advance(c,20n);
  assert.equal(c.value(7),0);assert.equal(output(c),false);assert.equal(c.value(10),0);
  assert.equal(c.comparator_ready(1,20n),1);assert.equal(u64(c.next_ps()),10000000n);
  wall(c,10000000n);assert.equal(c.value(7),1);assert.equal(output(c),false);
  advance(c,22n);assert.equal(output(c),false);advance(c,24n);assert.equal(output(c),true);
  assert.equal(c.value(10),1<<5);
});
test('loss of shared readiness retains already captured stages and the last known comparator raw value',()=>{
  const c=make(1);write(c,IO.ACSR,M.ACBG|M.ACIE);wall(c,0n);advance(c,2n);
  assert.equal(c.value(7),1);assert.equal(c.value(8),1);assert.equal(output(c),false);
  assert.equal(c.comparator_ready(0,2n),1);advance(c,4n);assert.equal(output(c),true);
  assert.equal(c.value(10),1<<5);assert.equal(c.ack(5,4n),1);
  input(c,1,2000000,4n);wall(c,1000000n);advance(c,8n);
  assert.equal(c.value(7),1);assert.equal(output(c),true);assert.equal(c.value(10),0);
  assert.equal(c.comparator_ready(1,8n),1);wall(c,1000000n);assert.equal(c.value(7),0);
  advance(c,12n);assert.equal(output(c),false);assert.equal(c.value(10),1<<5);
});
test('a shared-reference loss cancels pending unsampled raw propagation and readiness restarts that propagation',()=>{
  const c=make(1,100);write(c,IO.ACSR,M.ACBG);assert.equal(u64(c.next_ps()),100000n);
  wall(c,50000n);assert.equal(c.comparator_ready(0,0n),1);assert.equal(u64(c.next_ps()),MAX);
  wall(c,1000000n);assert.equal(c.value(7),0);assert.equal(c.comparator_ready(1,0n),1);
  assert.equal(u64(c.next_ps()),1100000n);wall(c,1100000n);assert.equal(c.value(7),1);
});
test('readiness cannot retroactively change an already acquired ADC sample',()=>{
  const c=make();start(c,true);advance(c,58n);assert.equal(c.value(3),512);
  assert.equal(c.adc_ready(0),1);advance(c,104n);
  assert.equal(c.detail(0),1n);assert.equal(c.value(2),512);assert.equal(c.value(1),0);
});
test('invalid readiness values are rejected without clock delivery or new diagnostics',()=>{
  const c=make(1);
  for(const ready of [-1,2]) {
    assert.equal(c.adc_ready(ready),0);assert.equal(c.comparator_ready(ready,100n),0);
    assert.equal(c.value(0),1);assert.equal(c.value(6),1);assert.equal(c.detail(3),0n);
    assert.equal(c.detail(4),0n);assert.equal(c.value(1),0);
  }
});
