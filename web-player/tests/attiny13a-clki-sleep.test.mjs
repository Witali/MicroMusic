import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create = compileAnalog('attiny13a-clki-sleep', [
  'web-player/native/peripherals/system_sleep.c'
], `#include "system_sleep.h"
static system_sleep_t s;
void reset(uint64_t now) { system_sleep_reset(&s,now); }
int enter(int mode,uint64_t now) { return system_sleep_enter(&s,0x20|(mode<<3),now); }
int wake(int asserted,int enabled,int level,uint64_t ck,uint32_t cycles,uint64_t recovery,uint64_t now) {
 return system_sleep_wake_clocked(&s,asserted,enabled,level,ck,cycles,recovery,now);
}
int legacy(uint64_t startup,uint64_t extra,uint64_t now) {
 return system_sleep_wake_exact(&s,SYSTEM_WAKE_PCINT,SYSTEM_WAKE_PCINT,1,startup,extra,now);
}
int edge(int source,int system,uint64_t now) { return system_sleep_clock_edge(&s,source,system,now); }
int advance(uint64_t now) { return system_sleep_advance(&s,now); }
uint64_t next(void) { return system_sleep_next_event(&s); }
uint64_t source_left(void) { return s.source_ck_left; }
uint32_t cycles_left(void) { return s.wake_cycles_left; }
uint64_t ready_at(void) { return s.ready_at; }
uint64_t startup_until(void) { return s.startup_until; }
uint64_t wake_delay_at(void) { return s.wake_delay_at; }
uint64_t recovery_until(void) { return s.recovery_until; }
int phase(void) { return s.phase; }
int clocked(void) { return s.clocked; }
int sources(void) { return s.wake_sources; }
int domains(void) { return system_sleep_domains(&s,0,1); }
int clamp(void) { return system_sleep_input_clamp(&s); }
uintptr_t state_ptr(void) { return (uintptr_t)&s; }
unsigned state_size(void) { return sizeof(s); }
`);
const MAX = (1n << 64n) - 1n;
const P = {RUNNING:0,ASLEEP:1,STARTING:2,WAKE_DELAY:3};
const F = {NONE:0,ENTER:1,RESET:4,START:8,READY:16,INVALID:32};
const W = {RESET:1,INT0:2,PCINT:4,TIMER:8,WDT:256,ADC:512};
const snapshot = s => new Uint8Array(s.memory.buffer,s.state_ptr(),s.state_size()).slice();
function asleep(mode=2,at=0n) {
  const s=create(); s.reset(at); assert.equal(s.enter(mode,at),F.ENTER); return s;
}
const wake = (s,{source=W.PCINT,enabled=source,level=1,ck=6n,cycles=4,recovery=0n,at=0n}={}) =>
  s.wake(source,enabled,level,ck,cycles,recovery,at);

test('power-down startup waits for six source edges despite arbitrary wall time',()=>{
  const s=asleep(); assert.equal(wake(s,{at:100n}),F.START);
  assert.equal(s.source_left(),6n); assert.equal(s.cycles_left(),4);
  assert.equal(s.next(),-1n); assert.equal(s.clamp(),1); assert.equal(s.domains(),48);
  assert.equal(s.edge(1,1,100n),F.NONE); assert.equal(s.source_left(),6n);
  assert.equal(s.advance(1000000000000n),F.NONE); assert.equal(s.phase(),P.STARTING);
  for(let i=1n;i<=6n;i++) {
    assert.equal(s.edge(1,1,1000000000000n+i*100n),F.NONE);
    assert.equal(s.source_left(),6n-i); assert.equal(s.cycles_left(),4);
  }
  assert.equal(s.phase(),P.WAKE_DELAY); assert.equal(s.domains(),255); assert.equal(s.clamp(),0);
  assert.equal(s.next(),-1n);
  for(const [i,t] of [2000n,9000n,9001n,80000n].entries()) {
    assert.equal(s.edge(0,1,1000000000000n+t),i===3?F.READY:F.NONE);
  }
  assert.equal(s.phase(),P.RUNNING); assert.equal(s.cycles_left(),0);
  assert.equal(s.ready_at(),1000000080000n);
});

test('BOD wall recovery and source startup overlap when source finishes first',()=>{
  const s=asleep(); wake(s,{at:100n,ck:2n,recovery:100n});
  assert.equal(s.next(),200n);
  s.edge(1,0,110n); s.edge(1,1,120n);
  assert.equal(s.source_left(),0n); assert.equal(s.phase(),P.STARTING);
  assert.equal(s.startup_until(),200n); assert.equal(s.next(),200n);
  s.edge(0,1,199n); assert.equal(s.cycles_left(),4);
  s.edge(0,1,200n); assert.equal(s.phase(),P.WAKE_DELAY); assert.equal(s.cycles_left(),4);
  assert.equal(s.wake_delay_at(),200n); assert.equal(s.next(),-1n);
  s.edge(0,1,201n); assert.equal(s.cycles_left(),3);
});

test('expired recovery cannot substitute for stopped source CK',()=>{
  const s=asleep(); wake(s,{at:10n,ck:2n,recovery:20n});
  s.advance(900n); assert.equal(s.phase(),P.STARTING); assert.equal(s.next(),-1n);
  assert.equal(s.domains(),48);
  s.edge(1,1,1000n); assert.equal(s.phase(),P.STARTING);
  s.edge(1,1,2000n); assert.equal(s.phase(),P.WAKE_DELAY);
  assert.equal(s.wake_delay_at(),2000n); assert.equal(s.cycles_left(),4);
});

test('late advance records actual wall recovery boundary and counts a later edge',()=>{
  const s=asleep(); wake(s,{at:10n,ck:0n,recovery:50n});
  s.edge(0,1,100n); assert.equal(s.wake_delay_at(),60n); assert.equal(s.cycles_left(),3);
  assert.equal(s.startup_until(),60n);
});

test('separate source/system deliveries at startup completion cannot double count',()=>{
  const s=asleep(); wake(s,{ck:2n});
  s.edge(0,1,10n); assert.equal(s.source_left(),2n);
  s.edge(1,0,20n); s.edge(1,0,20n); assert.equal(s.source_left(),1n);
  s.edge(1,0,30n); s.edge(0,1,30n); assert.equal(s.cycles_left(),4);
  s.edge(0,1,31n); s.edge(0,1,31n); assert.equal(s.cycles_left(),3);
  s.edge(1,0,32n); s.edge(0,0,33n); assert.equal(s.cycles_left(),3);
  s.edge(0,1,34n); s.edge(0,1,37n); assert.equal(s.edge(0,1,90n),F.READY);
  assert.equal(s.edge(1,1,100n),F.NONE); assert.equal(s.cycles_left(),0);
});

test('Idle and ADC Noise Reduction use four actual system edges with no source startup',()=>{
  for(const mode of [0,1]) {
    const s=asleep(mode); wake(s,{source:W.WDT,ck:0n,at:5n});
    assert.equal(s.phase(),P.WAKE_DELAY); assert.equal(s.domains(),255);
    s.edge(1,1,5n); s.advance(999999999n); assert.equal(s.cycles_left(),4);
    for(let i=1n;i<=4n;i++) {
      assert.equal(s.edge(0,1,999999999n+i*13n),i===4n?F.READY:F.NONE);
    }
  }
});

test('clocked wake timestamps retain integer precision above 2^53',()=>{
  const at=(1n<<53n)+123n, s=asleep(2,at);
  wake(s,{at,ck:1n,recovery:1n});
  assert.equal(s.next(),at+1n);
  s.edge(1,1,at+1n); assert.equal(s.wake_delay_at(),at+1n);
  for(let i=2n;i<=5n;i++) s.edge(0,1,at+i);
  assert.equal(s.ready_at(),at+5n); assert.equal(s.phase(),P.RUNNING);
});

test('invalid cycle counts, non-powerdown startup, and overflow do not mutate state',()=>{
  const cases=[
    [2,{cycles:0}], [2,{cycles:3}], [2,{cycles:5}],
    [0,{ck:1n}], [1,{ck:1n}],
    [2,{recovery:MAX-5n,at:5n}], [2,{at:MAX,recovery:0n}]
  ];
  for(const [mode,options] of cases) {
    const s=asleep(mode,5n), before=snapshot(s);
    assert.equal(wake(s,{at:5n,...options}),F.INVALID);
    assert.deepEqual(snapshot(s),before);
  }
});

test('backward edges and advances cannot consume counters or change timestamps',()=>{
  const s=asleep(2,100n); wake(s,{at:100n,ck:2n}); s.edge(1,0,200n);
  const before=snapshot(s);
  assert.equal(s.edge(1,1,199n),F.INVALID); assert.deepEqual(snapshot(s),before);
  assert.equal(s.advance(0n),F.INVALID); assert.deepEqual(snapshot(s),before);
  assert.equal(wake(s,{at:199n}),F.INVALID); assert.deepEqual(snapshot(s),before);
});

test('wake masks and level sensing are unchanged for the edge-driven API',()=>{
  const s=asleep();
  assert.equal(wake(s,{source:W.INT0,enabled:0}),F.NONE);
  assert.equal(wake(s,{source:W.INT0,level:0}),F.NONE);
  assert.equal(wake(s,{source:W.TIMER|W.ADC}),F.NONE);
  assert.equal(s.phase(),P.ASLEEP); assert.equal(s.clocked(),0);
  assert.equal(wake(s,{source:W.INT0}),F.START); assert.equal(s.sources(),W.INT0);
});

test('reset cancels clocked counters even when wake timing arguments are invalid',()=>{
  const s=asleep(); wake(s,{ck:2n,recovery:100n}); s.edge(1,0,1n);
  assert.equal(wake(s,{source:W.RESET,enabled:0,cycles:0,recovery:MAX,at:2n}),F.RESET);
  assert.equal(s.phase(),P.RUNNING); assert.equal(s.clocked(),0);
  assert.equal(s.source_left(),0n); assert.equal(s.cycles_left(),0);
  assert.equal(s.next(),-1n); assert.equal(s.recovery_until(),-1n);
  assert.equal(s.sources(),W.RESET);
});

test('legacy deadline wake remains unchanged and later sleep clears clocked state',()=>{
  const s=asleep(); assert.equal(s.legacy(10n,8n,2n),F.START);
  assert.equal(s.clocked(),0); assert.equal(s.next(),12n);
  assert.equal(s.edge(1,1,12n),F.NONE); assert.equal(s.next(),20n);
  assert.equal(s.advance(20n),F.READY);
  s.enter(2,20n); wake(s,{ck:0n,at:20n});
  for(let i=1n;i<=4n;i++) s.edge(0,1,20n+i);
  assert.equal(s.enter(0,25n),F.ENTER); assert.equal(s.clocked(),0);
  assert.equal(s.source_left(),0n); assert.equal(s.cycles_left(),0);
  assert.equal(s.legacy(0n,8n,25n),F.START); assert.equal(s.advance(33n),F.READY);
});
