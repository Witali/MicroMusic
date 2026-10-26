import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO,AT13_MASK as M} from '../lib/attiny13a-registers.js';
const methods=['reset','next_event','advance','read','write','input','reference','sources','pending','ack'];
const reference=readFileSync(new URL('fixtures/analog-unconditional-reference.c',import.meta.url),'utf8');
const create=compileAnalog('analog-idle-dispatch',[
  'web-player/native/peripherals/analog_adc.c','web-player/native/peripherals/analog_comparator.c',
],`
#include "analog.h"
#include <string.h>
static analog_t a,b;
static uint64_t actual_calls,reference_calls;
static int counted_adc(analog_adc_t *adc,uint64_t time) {
 if(adc==&a.adc)actual_calls++;else if(adc==&b.adc)reference_calls++;
 return analog_adc_advance(adc,time);
}
#define analog_adc_advance counted_adc
#include "analog.c"
${methods.map(n=>`#define analog_${n} reference_analog_${n}`).join('\n')}
#define connect_sources reference_connect_sources
${reference}
${methods.map(n=>`#undef analog_${n}`).join('\n')}
#undef connect_sources
#undef analog_adc_advance
static int ra,rb;
static uint8_t va,vb;
void initialize(int sample,int delay,int startup,int initial) {
 memset(&a,0,sizeof a);memset(&b,0,sizeof b);
 analog_comparator_config_t c={delay,startup,0,initial};
 analog_reset(&a,5000000,1100000,sample,&c,0);
 reference_analog_reset(&b,5000000,1100000,sample,&c,0);
 actual_calls=reference_calls=0;ra=rb=va=vb=0;
}
int operation(int op,int arg,int value,uint64_t time) {
 va=vb=0xa5;
 switch(op) {
 case 0:ra=analog_advance(&a,time);rb=reference_analog_advance(&b,time);break;
 case 1:ra=analog_read(&a,arg,&va,time);rb=reference_analog_read(&b,arg,&vb,time);break;
 case 2:ra=analog_write(&a,arg,value,time);rb=reference_analog_write(&b,arg,value,time);break;
 case 3:ra=analog_input(&a,arg,value,time);rb=reference_analog_input(&b,arg,value,time);break;
 case 4:ra=analog_reference(&a,arg,value,time);rb=reference_analog_reference(&b,arg,value,time);break;
 case 5:ra=analog_sources(&a,arg,time);rb=reference_analog_sources(&b,arg,time);break;
 case 6:ra=analog_ack(&a,arg,time);rb=reference_analog_ack(&b,arg,time);break;
 case 7:ra=analog_adc_clock_running(&a.adc,arg,time);rb=analog_adc_clock_running(&b.adc,arg,time);break;
 case 8:ra=analog_comparator_clock_running(&a.comparator,arg,value,time);rb=analog_comparator_clock_running(&b.comparator,arg,value,time);break;
 case 9:ra=analog_adc_noise_cancel_start(&a.adc,time);rb=analog_adc_noise_cancel_start(&b.adc,time);break;
 case 10:ra=analog_comparator_sleep(&a.comparator,arg,time);rb=analog_comparator_sleep(&b.comparator,arg,time);break;
 default:return 0;
 }
 return ra==rb&&va==vb&&!memcmp(&a,&b,sizeof a)&&
  analog_next_event(&a)==reference_analog_next_event(&b)&&analog_pending(&a)==reference_analog_pending(&b);
}
int mismatch(void) { const uint8_t *x=(void*)&a,*y=(void*)&b;for(unsigned i=0;i<sizeof a;i++)if(x[i]!=y[i])return i+1;return 0; }
int result(void) { return ra; }
uint64_t optimized_calls(void) { return actual_calls; }
uint64_t original_calls(void) { return reference_calls; }
void clear_counts(void) { actual_calls=reference_calls=0; }
uint64_t conversions(void) { return a.adc.conversions; }
uint64_t lost(void) { return a.adc.discarded_results; }
uint64_t sampled_at(void) { return a.adc.sampled_at; }
int sampled_result(void) { return a.adc.sampled_result; }
int control(void) { return a.comparator.acsr; }
`);
function make(sample=27,delay=0,startup=0,initial=0){
  const c={...create()};c.initialize(sample,delay,startup,initial);
  c.call=(op,arg=0,value=0,time=0n)=>assert.equal(c.operation(op,arg,value,time),1,`op=${op},arg=${arg},value=${value},time=${time},byte=${c.mismatch()}`);
  return c;
}
test('running idle ADC keeps canonical full state without recurring module dispatch',()=>{
  for(const enabled of [false,true]){
    const c=make();if(enabled)c.call(2,IO.ADCSRA,M.ADEN|7);c.clear_counts();
    for(let n=0;n<5000;n++)c.call(0,0,0,BigInt(n*17));
    assert.equal(c.optimized_calls(),0n);assert.equal(c.original_calls(),5000n);
    assert.equal(c.conversions(),0n);
  }
});
test('all ADC divisors, first-sample choices and trigger sources match the unconditional aggregator',()=>{
  for(const sample of [27,29])for(let code=0;code<8;code++)for(let trigger=0;trigger<7;trigger++){
    const c=make(sample);c.call(3,5,2500000);c.call(2,IO.ADCSRB,trigger);
    c.call(2,IO.ADCSRA,M.ADEN|M.ADATE|code|(trigger?0:M.ADSC));
    for(let n=0;n<1024;n++){
      const time=BigInt(n*17);
      if(n%64===0){
        c.call(5,n%128===0?0x7c:0,0,time);
        if(trigger===1){c.call(6,5,0,time);c.call(3,0,n%128===0?2000000:0,time);}
      }
      c.call(0,0,0,time);
    }
    assert.ok(c.conversions()>0n,`sample=${sample},code=${code},trigger=${trigger}`);
  }
});
test('random bus, input, flags and domain changes preserve every analog state byte',()=>{
  let seed=0x13adc;const random=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
  const registers=[IO.ADCSRB,IO.ADCL,IO.ADCH,IO.ADCSRA,IO.ADMUX,IO.ACSR];
  for(const sample of [27,29])for(const delay of [0,1,5])for(const initial of [0,1]){
    const c=make(sample,delay,9,initial);let time=0n;
    for(let n=0;n<3000;n++){
      time+=BigInt(random()%32);const op=random()%11;
      if(op===1)c.call(op,registers[random()%registers.length],0,time);
      else if(op===2)c.call(op,registers[random()%registers.length],random()&255,time);
      else if(op===3)c.call(op,random()%6,[-100,0,1100000,2500000,5000000][random()%5],time);
      else if(op===4)c.call(op,[0,1800000,5000000][random()%3],[0,1100000][random()%2],time);
      else if(op===5)c.call(op,random()&0x7c,0,time);
      else if(op===6)c.call(op,[5,9][random()&1],0,time);
      else if([7,8,10].includes(op))c.call(op,random()&1,op===8?random()&1:0,time);
      else c.call(op,0,0,time);
      if(time>0n&&n%43===0)c.call(0,0,0,time-1n);
    }
  }
});
test('sample/input ties, result locking and stopped active clocks keep their exact endpoints',()=>{
  for(const sample of [27,29]){
    const c=make(sample),at=BigInt(4+2*sample);
    c.call(3,5,2500000);c.call(2,IO.ADCSRA,M.ADEN|M.ADSC|M.ADIE);
    c.call(3,5,1250000,at-1n);c.call(3,5,0,at);
    assert.equal(c.sampled_at(),at);assert.equal(c.sampled_result(),256);
    c.call(1,IO.ADCL,0,103n);c.call(0,0,0,104n);assert.equal(c.conversions(),1n);assert.equal(c.lost(),1n);
    c.call(1,IO.ADCH,0,104n);c.call(6,9,0,104n);
    const d=make(sample);d.call(3,5,2500000);d.call(2,IO.ADCSRA,M.ADEN|M.ADSC);
    d.call(7,0,0,20n);d.call(0,0,0,200n);d.call(7,1,0,200n);
    d.call(0,0,0,at+179n);assert.equal(d.sampled_at(),0n);
    d.call(0,0,0,at+180n);assert.equal(d.sampled_at(),at+180n);assert.equal(d.sampled_result(),512);
  }
});
test('disabled ADC fast path preserves comparator ACME routing across enable changes',()=>{
  const c=make();c.call(3,0,2000000);c.call(3,1,3000000);c.call(3,5,1000000);
  c.call(2,IO.ADCSRB,M.ACME);c.call(2,IO.ADMUX,0);c.call(0,0,0,4n);assert.ok(c.control()&M.ACO);
  c.call(2,IO.ADCSRA,M.ADEN,4n);c.call(0,0,0,8n);assert.equal(c.control()&M.ACO,0);
  c.call(2,IO.ADCSRA,0,8n);c.call(0,0,0,12n);assert.ok(c.control()&M.ACO);
});
test('idle uint64 endpoints and reversed-time rejection match in running and stopped domains',()=>{
  const end=(1n<<64n)-1n;
  for(const running of [0,1]){
    const c=make();c.call(7,running);c.call(0,0,0,end);c.call(0,0,0,end);
    c.call(0,0,0,end-1n);assert.equal(c.result(),0);
  }
});
