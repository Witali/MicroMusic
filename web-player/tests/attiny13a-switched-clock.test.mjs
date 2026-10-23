import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const make=compileAnalog('attiny13a-switched-clock',[
  'web-player/native/devices/attiny13a/switched_clock.c',
],String.raw`
#include "../devices/attiny13a/switched_clock.h"
#include <stddef.h>
#include <string.h>
static attiny13a_switched_clock_t s,before;
int init(uint64_t at,uint32_t hz,int enabled){return attiny13a_switched_clock_init(&s,at,hz,enabled);}
int advance(uint64_t to){return attiny13a_switched_clock_advance(&s,to);}
int enabled(int value){return attiny13a_switched_clock_set_enabled(&s,value);}
uint64_t deadline(uint64_t n){return attiny13a_switched_clock_deadline_halves(&s,n);}
uint64_t now(void){return s.time_ps;}
uint64_t halves(void){return s.source_half;}
uint64_t phase(void){return s.phase;}
uint32_t frequency(void){return s.frequency_hz;}
int on(void){return s.enabled;}
void snapshot(void){memcpy(&before,&s,sizeof s);}
int unchanged(void){return !memcmp(&before,&s,sizeof s);}
/* Test-only defensive count-bound probe; production callers never edit state. */
void force_count(uint64_t n){s.source_half=n;}
int null_arguments(void){
 return attiny13a_switched_clock_init(NULL,0,1,0)==AT13_SWITCHED_CLOCK_BAD_ARGUMENT &&
  attiny13a_switched_clock_advance(NULL,1)==AT13_SWITCHED_CLOCK_BAD_ARGUMENT &&
  attiny13a_switched_clock_set_enabled(NULL,1)==AT13_SWITCHED_CLOCK_BAD_ARGUMENT &&
  attiny13a_switched_clock_deadline_halves(NULL,1)==AT13_SWITCHED_CLOCK_NEVER;
}
int zero_state_arguments(void){
 attiny13a_switched_clock_t zero={0};
 return attiny13a_switched_clock_advance(&zero,1)==AT13_SWITCHED_CLOCK_BAD_ARGUMENT &&
  attiny13a_switched_clock_set_enabled(&zero,1)==AT13_SWITCHED_CLOCK_BAD_ARGUMENT &&
  attiny13a_switched_clock_deadline_halves(&zero,0)==AT13_SWITCHED_CLOCK_NEVER;
}
`);
const MAX=(1n<<64n)-1n,PS=1000000000000n,u64=value=>BigInt.asUintN(64,value);
const state=c=>({time:u64(c.now()),halves:u64(c.halves()),phase:u64(c.phase()),hz:c.frequency(),on:c.on()});
function expectedDeadline(s,count){
  if(!count)return s.time;
  if(!s.on||count>MAX-s.halves)return MAX;
  const rate=2n*BigInt(s.hz),at=s.time+(count*PS-s.phase+rate-1n)/rate;
  return at>=MAX?MAX:at;
}

test('switched clock initializes explicit fixed frequency/on state with abstract output high',()=>{
  for(const hz of [1,3,9600000,20000000])for(const on of [0,1]){
    const c=make();assert.equal(c.init(37n,hz,on),1);
    assert.deepEqual(state(c),{time:37n,halves:0n,phase:0n,hz,on});
    assert.equal(c.advance(37n),1);assert.equal(c.enabled(on),1);
    assert.equal(u64(c.deadline(0n)),37n);assert.equal(u64(c.halves())&1n,0n);
  }
});

test('enabled mapping matches exact BigInt arithmetic through the uint64 wall timeline',()=>{
  for(const hz of [1,3,128000,9600000,12345679,20000000]){
    const c=make();assert.equal(c.init(0n,hz,1),1);
    for(const at of [0n,1n,17n,PS,(1n<<53n)+37n,MAX-1n]){
      assert.equal(c.advance(at),1);
      const numerator=at*BigInt(hz)*2n;
      assert.equal(u64(c.halves()),numerator/PS);assert.equal(u64(c.phase()),numerator%PS);
      assert.equal(u64(c.now()),at);
      for(const n of [0n,1n,2n,7n,10000n,MAX])assert.equal(u64(c.deadline(n)),expectedDeadline(state(c),n));
    }
  }
});

test('arbitrary batching preserves exact count and remainder at nonintegral half periods',()=>{
  const a=make(),b=make(),start=(1n<<53n)+37n,hz=12345679;
  assert.equal(a.init(start,hz,1),1);assert.equal(b.init(start,hz,1),1);
  let seed=0x12345678n,at=start;
  for(let i=0;i<1200;i++){
    seed=(seed*1664525n+1013904223n)&0xffffffffn;at+=seed%1000000001n;
    assert.equal(a.advance(at),1);
  }
  assert.equal(b.advance(at),1);assert.deepEqual(state(a),state(b));
  const total=(at-start)*2n*BigInt(hz);
  assert.equal(u64(a.halves()),total/PS);assert.equal(u64(a.phase()),total%PS);
});

test('mid-phase off/on freezes phase and emits no phantom half-period',()=>{
  const c=make();assert.equal(c.init(0n,20000000,1),1);assert.equal(c.advance(10000n),1);
  assert.equal(u64(c.phase()),400000000000n);assert.equal(u64(c.halves()),0n);
  assert.equal(c.enabled(0),1);assert.equal(c.advance(1000000000000000n),1);
  assert.equal(u64(c.phase()),400000000000n);assert.equal(u64(c.halves()),0n);
  assert.equal(u64(c.deadline(1n)),MAX);assert.equal(u64(c.deadline(0n)),u64(c.now()));
  const stopped=state(c);assert.equal(c.enabled(1),1);
  assert.deepEqual(state(c),{...stopped,on:1});
  const edge=stopped.time+15000n;assert.equal(u64(c.deadline(1n)),edge);
  assert.equal(c.advance(edge-1n),1);assert.equal(u64(c.halves()),0n);
  assert.equal(c.advance(edge),1);assert.equal(u64(c.halves()),1n);assert.equal(u64(c.phase()),0n);
});

test('random switched spans match an enabled-time oracle without changing frequency',()=>{
  const c=make(),hz=9600000;assert.equal(c.init(0n,hz,1),1);
  let at=0n,phase=0n,halves=0n,on=1,seed=0xcafebaben;
  for(let i=0;i<1000;i++){
    seed=(seed*1103515245n+12345n)&0xffffffffn;const delta=seed%1000000001n;at+=delta;
    if(on){const total=delta*2n*BigInt(hz)+phase;halves+=total/PS;phase=total%PS;}
    assert.equal(c.advance(at),1);
    assert.deepEqual(state(c),{time:at,halves,phase,hz,on});
    if(seed&4n){on^=1;assert.equal(c.enabled(on),1);}
    for(const n of [0n,1n,77n])assert.equal(u64(c.deadline(n)),expectedDeadline({time:at,halves,phase,hz,on},n));
  }
});

test('one advance can cover a near-uint64 stopped span without source progress',()=>{
  const c=make();assert.equal(c.init(37n,20000000,0),1);
  assert.equal(c.advance(MAX-1n),1);
  assert.deepEqual(state(c),{time:MAX-1n,halves:0n,phase:0n,hz:20000000,on:0});
  assert.equal(c.enabled(1),1);assert.equal(u64(c.deadline(1n)),MAX);
  assert.equal(u64(c.deadline(0n)),MAX-1n);
});

test('small explicit-front oracle agrees at each pre-edge/exact-edge boundary',()=>{
  for(const hz of [3,9600000,12345679,20000000]){
    const c=make(),rate=2n*BigInt(hz);assert.equal(c.init(0n,hz,1),1);
    for(let half=1n;half<=160n;half++){
      // Explicit source-front iteration is confined to this independent oracle.
      const at=(half*PS+rate-1n)/rate;
      assert.equal(c.advance(at-1n),1);assert.equal(u64(c.halves()),half-1n);
      assert.equal(c.advance(at),1);assert.equal(u64(c.halves()),half);
    }
  }
});

test('deadline inverse rounds retained phase before time and is earliest representable ps',()=>{
  for(const hz of [1,3,9600000,12345679,20000000])for(const phaseAt of [1n,123n,24999n,500001n])for(const n of [1n,2n,31n]){
    const c=make();assert.equal(c.init(0n,hz,1),1);assert.equal(c.advance(phaseAt),1);
    const before=state(c),at=expectedDeadline(before,n);
    c.snapshot();assert.equal(u64(c.deadline(n)),at);assert.equal(c.unchanged(),1);
    assert.equal(c.advance(at-1n),1);assert.ok(u64(c.halves())<before.halves+n);
    assert.equal(c.advance(at),1);assert.equal(u64(c.halves()),before.halves+n);
  }
});

test('bad arguments/backward/MAX time reject atomically and remain recoverable',()=>{
  const c=make();assert.equal(c.init(100n,10000000,1),1);c.snapshot();
  for(const [at,hz,on,error] of [[0n,0,1,-1],[0n,20000001,1,-1],[0n,0xffffffff,1,-1],
    [0n,1,2,-1],[0n,1,-1,-1],[MAX,1,1,-2]]){
    assert.equal(c.init(at,hz,on),error);assert.equal(c.unchanged(),1);
  }
  for(const at of [99n,MAX]){assert.equal(c.advance(at),-2);assert.equal(c.unchanged(),1);}
  for(const on of [-1,2]){assert.equal(c.enabled(on),-1);assert.equal(c.unchanged(),1);}
  assert.equal(c.null_arguments(),1);assert.equal(c.zero_state_arguments(),1);
  assert.equal(c.advance(100100n),1);assert.equal(u64(c.halves()),2n);
});

test('defensive counter overflow is atomic and deadline count bounds stay explicit',()=>{
  const c=make();assert.equal(c.init(0n,20000000,1),1);
  c.force_count(MAX-1n);c.snapshot();
  assert.equal(c.advance(50000n),-3);assert.equal(c.unchanged(),1);
  assert.equal(u64(c.deadline(2n)),MAX);assert.equal(u64(c.deadline(1n)),25000n);
  assert.equal(c.advance(25000n),1);assert.equal(u64(c.halves()),MAX);
  assert.equal(u64(c.deadline(1n)),MAX);assert.equal(c.enabled(0),1);
  assert.equal(c.advance(MAX-1n),1);assert.equal(u64(c.halves()),MAX);
});
