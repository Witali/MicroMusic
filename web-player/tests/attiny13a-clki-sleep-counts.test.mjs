import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('attiny13a-clki-sleep-counts',[
  'web-player/native/peripherals/system_sleep.c'
],`#include "system_sleep.h"
#include <string.h>
static system_sleep_t s,reference;
int init(int mode,uint64_t at,uint64_t ck,uint64_t recovery) {
 system_sleep_reset(&s,at);
 if(system_sleep_enter(&s,0x20|(mode<<3),at)!=SYSTEM_SLEEP_ENTERED)return -1;
 int result=system_sleep_wake_clocked(&s,SYSTEM_WAKE_WDT,SYSTEM_WAKE_WDT,1,ck,4,recovery,at);
 reference=s;return result;
}
int counts(uint64_t source,uint64_t system,uint64_t at) {
 return system_sleep_clock_counts(&s,source,system,at);
}
int edge(int source,int system,uint64_t at) {
 return system_sleep_clock_edge(&reference,source,system,at);
}
int equal(void) { return memcmp(&s,&reference,sizeof s)==0; }
int advance(uint64_t at) { return system_sleep_advance(&s,at); }
int null_counts(void) { return system_sleep_clock_counts(0,1,1,0); }
int reset_wake(uint64_t at) {
 return system_sleep_wake_clocked(&s,SYSTEM_WAKE_RESET,0,0,0,0,UINT64_MAX,at);
}
int legacy(uint64_t at) {
 system_sleep_reset(&s,at);system_sleep_enter(&s,0x20,at);
 return system_sleep_wake_exact(&s,SYSTEM_WAKE_WDT,SYSTEM_WAKE_WDT,1,10,8,at);
}
int phase(void) { return s.phase; }
int clocked(void) { return s.clocked; }
uint64_t source_left(void) { return s.source_ck_left; }
unsigned cycles_left(void) { return s.wake_cycles_left; }
uint64_t ready(void) { return s.ready_at; }
uint64_t wake_delay_at(void) { return s.wake_delay_at; }
uint64_t next(void) { return system_sleep_next_event(&s); }
uintptr_t state_ptr(void) { return (uintptr_t)&s; }
unsigned state_size(void) { return sizeof s; }
`);
const MAX=(1n<<64n)-1n;
const snapshot=c=>new Uint8Array(c.memory.buffer,c.state_ptr(),c.state_size()).slice();

test('analytic batches match individual source and system edges at stage endpoints',()=>{
  const c=create();assert.equal(c.init(2,0n,6n,0n),8);
  for(let i=1n;i<=6n;i++)assert.equal(c.edge(1,1,i*100n),0);
  assert.equal(c.counts(6n,6n,600n),0);assert.equal(c.equal(),1);
  for(let i=7n;i<=10n;i++)assert.equal(c.edge(1,1,i*100n),i===10n?16:0);
  assert.equal(c.counts(4n,4n,1000n),16);assert.equal(c.equal(),1);
  assert.equal(c.ready(),1000n);assert.equal(c.phase(),0);
});

test('partial source batches clamp to startup count without reusing wake rises',()=>{
  const c=create();c.init(2,0n,6n,0n);
  assert.equal(c.counts(4n,4n,400n),0);assert.equal(c.source_left(),2n);
  assert.equal(c.counts(2n,2n,400n),0);assert.equal(c.source_left(),2n);
  assert.equal(c.counts(MAX,MAX,500n),0);assert.equal(c.source_left(),0n);
  assert.equal(c.phase(),3);assert.equal(c.cycles_left(),4);assert.equal(c.wake_delay_at(),500n);
  assert.equal(c.counts(0n,MAX,500n),0);assert.equal(c.cycles_left(),4);
  assert.equal(c.counts(0n,MAX,600n),16);assert.equal(c.cycles_left(),0);
  assert.equal(c.counts(MAX,MAX,700n),0);assert.equal(c.cycles_left(),0);
});

test('source startup and independent recovery overlap with an exact wall boundary',()=>{
  const c=create();c.init(2,0n,2n,100n);
  assert.equal(c.counts(2n,2n,20n),0);assert.equal(c.source_left(),0n);
  assert.equal(c.phase(),2);assert.equal(c.next(),100n);
  assert.equal(c.counts(0n,0n,100n),0);assert.equal(c.phase(),3);
  assert.equal(c.wake_delay_at(),100n);assert.equal(c.next(),-1n);
  assert.equal(c.counts(0n,4n,100n),0);assert.equal(c.cycles_left(),4);
  assert.equal(c.counts(0n,3n,103n),0);assert.equal(c.cycles_left(),1);
  assert.equal(c.counts(0n,3n,103n),0);assert.equal(c.cycles_left(),1);
  assert.equal(c.counts(0n,1n,104n),16);assert.equal(c.ready(),104n);
});

test('wall recovery never substitutes for stopped source CK',()=>{
  const c=create();c.init(2,0n,2n,100n);
  assert.equal(c.counts(0n,0n,10000n),0);assert.equal(c.phase(),2);
  assert.equal(c.source_left(),2n);assert.equal(c.next(),-1n);
  assert.equal(c.counts(2n,4n,20000n),0);assert.equal(c.phase(),3);
  assert.equal(c.cycles_left(),4);assert.equal(c.counts(0n,4n,20010n),16);
});

test('Idle and ADC noise wake batches require four actual rises after the wake cause',()=>{
  for(const mode of [0,1]) {
    const c=create();assert.equal(c.init(mode,100n,0n,0n),8);
    assert.equal(c.counts(20n,20n,100n),0);assert.equal(c.cycles_left(),4);
    assert.equal(c.counts(0n,0n,1000000000n),0);assert.equal(c.cycles_left(),4);
    assert.equal(c.counts(0n,4n,1000000100n),16);assert.equal(c.ready(),1000000100n);
  }
});

test('uint64 source counters and timestamps remain exact without addition overflow',()=>{
  const c=create(),at=(1n<<53n)+17n;c.init(2,at,MAX,0n);
  assert.equal(c.counts(MAX-1n,0n,at+100n),0);assert.equal(c.source_left(),1n);
  assert.equal(c.counts(1n,4n,at+101n),0);assert.equal(c.cycles_left(),4);
  assert.equal(c.counts(0n,4n,at+102n),16);assert.equal(c.ready(),at+102n);
});

test('invalid state and backward time reject before mutating counters or timestamps',()=>{
  const c=create();c.init(2,100n,6n,20n);c.counts(3n,0n,200n);
  const before=snapshot(c);
  assert.equal(c.counts(MAX,MAX,199n),32);assert.deepEqual(snapshot(c),before);
  assert.equal(c.null_counts(),32);assert.deepEqual(snapshot(c),before);
  assert.equal(c.advance(199n),32);assert.deepEqual(snapshot(c),before);
});

test('reset cancels batched counts and legacy deadlines do not become edge counters',()=>{
  const c=create();c.init(2,0n,6n,100n);c.counts(2n,0n,20n);
  assert.equal(c.reset_wake(21n),4);assert.equal(c.clocked(),0);
  assert.equal(c.source_left(),0n);assert.equal(c.cycles_left(),0);
  assert.equal(c.legacy(100n),8);assert.equal(c.counts(MAX,MAX,110n),0);
  assert.equal(c.clocked(),0);assert.equal(c.phase(),3);assert.equal(c.next(),118n);
  assert.equal(c.counts(0n,0n,118n),16);assert.equal(c.phase(),0);
});
