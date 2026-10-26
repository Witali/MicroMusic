import test from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create=compileAnalog('shared-bandgap',['web-player/native/devices/attiny13a/bandgap.c'],`
#include "../devices/attiny13a/bandgap.h"
static attiny13a_bandgap_t s;
int reset(uint32_t ns,uint64_t now) { return attiny13a_bandgap_init(&s,ns,now); }
int set(uint32_t owners,int powered,uint64_t now) { return attiny13a_bandgap_set(&s,owners,powered,now); }
int advance(uint64_t now) { return attiny13a_bandgap_advance(&s,now); }
uint64_t next_event(void) { return attiny13a_bandgap_next_event(&s); }
int value(int field) { switch(field) {
case 0:return s.owner_mask;case 1:return s.powered;case 2:return s.enabled;
case 3:return s.ready;case 4:return s.fault;default:return -1; } }
uint64_t detail(int field) { switch(field) {
case 0:return s.now_ps;case 1:return s.ready_at_ps;case 2:return s.startup_ps;default:return 0; } }
`);
const MAX=0xffffffffffffffffn,u64=x=>BigInt.asUintN(64,x);
const next=c=>u64(c.next_event()),state=c=>Array.from({length:5},(_,n)=>c.value(n));
function make(ns=10,now=0n) { const c=create();assert.equal(c.reset(ns,now),1);return c; }

test('shared reference initializes ownerless and waits only while powered demand exists',()=>{
  const c=make();assert.deepEqual(state(c),[0,0,0,0,0]);assert.equal(next(c),MAX);
  assert.equal(c.set(1,0,100n),1);assert.deepEqual(state(c),[1,0,0,0,0]);assert.equal(next(c),MAX);
  assert.equal(c.set(1,1,200n),1);assert.equal(next(c),10200n);
  assert.equal(c.advance(10199n),1);assert.equal(c.value(3),0);
  assert.equal(c.advance(10200n),1);assert.equal(c.value(3),1);assert.equal(next(c),MAX);
});
test('continuous ADC/comparator/BOD handoffs preserve startup progress and stable readiness',()=>{
  const c=make();assert.equal(c.set(1,1,0n),1);
  for(const [owners,at]of [[3,2000n],[2,4000n],[6,6000n],[4,8000n]]) {
    assert.equal(c.set(owners,1,at),1);assert.equal(next(c),10000n);
  }
  assert.equal(c.set(7,1,10000n),1);assert.equal(c.value(3),1);
  for(const owners of [1,2,4,5,6,7]) {
    assert.equal(c.set(owners,1,20000n),1);assert.equal(c.value(3),1);assert.equal(next(c),MAX);
  }
});
test('loss of all owners explicitly invalidates readiness and the next owner starts cold',()=>{
  const c=make();c.set(1,1,0n);c.advance(10000n);assert.equal(c.value(3),1);
  assert.equal(c.set(0,1,20000n),1);assert.deepEqual(state(c),[0,1,0,0,0]);
  assert.equal(c.set(2,1,20000n),1);assert.equal(c.value(3),0);assert.equal(next(c),30000n);
  assert.equal(c.set(0,1,25000n),1);assert.equal(next(c),MAX);
  assert.equal(c.set(4,1,26000n),1);assert.equal(next(c),36000n);
});
test('qualified power loss cancels startup while retaining the owner request for later restoration',()=>{
  const c=make();c.set(4,1,0n);
  assert.equal(c.set(4,0,5000n),1);assert.deepEqual(state(c),[4,0,0,0,0]);assert.equal(next(c),MAX);
  assert.equal(c.advance(10000000n),1);assert.equal(c.value(3),0);
  assert.equal(c.set(4,1,10000000n),1);assert.equal(next(c),10010000n);
  c.advance(10010000n);assert.equal(c.value(3),1);
  c.set(4,0,20000000n);assert.equal(c.value(3),0);assert.equal(next(c),MAX);
});
test('zero startup resolves in the enabling transaction without clock phases',()=>{
  const c=make(0);assert.equal(c.set(1,1,123n),1);assert.equal(c.value(3),1);assert.equal(next(c),MAX);
  c.set(0,1,123n);assert.equal(c.value(3),0);
  c.set(4,1,123n);assert.equal(c.value(3),1);assert.equal(u64(c.detail(0)),123n);
});
test('a due completion is serviced before an equal-time ownership update',()=>{
  const c=make();c.set(1,1,0n);
  assert.equal(c.set(2,1,10000n),1);assert.equal(c.value(3),1);assert.equal(next(c),MAX);
  assert.equal(c.set(0,1,10000n),1);assert.equal(c.value(3),0);
  assert.equal(c.set(4,1,10000n),1);assert.equal(next(c),20000n);
});
test('BOD demand preserves readiness through arbitrary elapsed intervals without any CPU/reset input',()=>{
  const c=make();c.set(4,1,0n);c.advance(10000n);
  for(const at of [20000n,1000000000000n,1n<<60n]) {
    assert.equal(c.set(4,1,at),1);assert.equal(c.value(3),1);assert.equal(next(c),MAX);
  }
});
test('large timestamps and uint32 ns retain exact deadlines without narrowing',()=>{
  const now=(1n<<60n)+17n,c=make(0xffffffff,now);
  c.set(7,1,now);assert.equal(u64(c.detail(2)),4294967295000n);
  assert.equal(next(c),now+4294967295000n);
  c.advance(now+4294967295000n);assert.equal(c.value(3),1);
});
test('faults reject reversed and sentinel times until reinitialized',()=>{
  const c=make(10,100n);assert.equal(c.advance(99n),0);assert.equal(c.value(4),1);
  assert.equal(c.set(1,1,200n),0);assert.equal(c.advance(200n),0);assert.equal(next(c),MAX);
  assert.equal(c.reset(0,1000n),1);assert.equal(c.set(1,1,1000n),1);assert.equal(c.value(3),1);
  assert.equal(c.advance(MAX),0);assert.equal(c.value(4),1);
  const invalid=create();assert.equal(invalid.reset(0,MAX),0);assert.equal(invalid.value(4),1);
});
for(const [owners,powered]of [[8,1],[256,1],[1,-1],[1,2]])test(`invalid owners/power ${owners}/${powered} is rejected before state mutation`,()=>{
  const c=make();c.set(1,1,0n);const before=state(c).slice(0,4);
  assert.equal(c.set(owners,powered,5000n),0);assert.deepEqual(state(c).slice(0,4),before);
  assert.equal(u64(c.detail(0)),0n);assert.equal(c.value(4),2);assert.equal(next(c),MAX);
});
test('overflow and no-event sentinel collisions never fabricate a ready reference',()=>{
  for(const now of [MAX-1000n,MAX-999n]) {
    const c=make(1,now);assert.equal(c.set(1,1,now),0);assert.equal(c.value(4),3);
    assert.equal(c.value(3),0);assert.equal(next(c),MAX);
  }
  const c=make(1,MAX-1001n);assert.equal(c.set(1,1,MAX-1001n),1);assert.equal(next(c),MAX-1n);
  assert.equal(c.advance(MAX-1n),1);assert.equal(c.value(3),1);
});
