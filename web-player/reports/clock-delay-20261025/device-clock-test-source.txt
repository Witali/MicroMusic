import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('device-clock',[],`
#include "device_clock.h"
static uint64_t quotient,remainder;
int ratio(uint64_t a,uint64_t b,uint64_t c,uint64_t d) {
 return device_clock_ratio(a,b,c,d,&quotient,&remainder);
}
int delay(uint64_t units,uint64_t denominator,uint64_t rate,uint64_t phase) {
 return device_clock_delay(units,denominator,rate,phase,&quotient);
}
uint64_t q(void) { return quotient; }
uint64_t r(void) { return remainder; }
`);
const U64=(1n<<64n)-1n,unsigned=n=>BigInt.asUintN(64,n);

test('clock products around32-bit bounds and64-bit addition wrap match a BigInt oracle',()=>{
  const c=create(),U32=(1n<<32n)-1n;
  const values=[0n,1n,U32-1n,U32,U32+1n,U64];
  for(const a of values)for(const b of values){
    const product=a*b,room=U64-(product&U64);
    for(const carry of [0n,room,room<U64?room+1n:U64,U64])
      for(const divisor of [0n,1n,2n,U32,1000000000000n,U64]){
        const n=product+carry,q=divisor?n/divisor:U64+1n;
        assert.equal(c.ratio(a,b,carry,divisor),Number(divisor>0n&&q<=U64));
        if(divisor&&q<=U64){assert.equal(unsigned(c.q()),q);assert.equal(unsigned(c.r()),n%divisor);}
      }
  }
});

test('equal clock rates retain full-width counters, proper and improper carries, and input validation',()=>{
  const c=create();
  for(const rate of [1n,2n,19200000n,1000000000000n,U64-1n,U64])
    for(const value of [0n,1n,999n,U64/2n,U64-1n,U64])
      for(const carry of [0n,rate-1n,rate,U64]){
        const numerator=value*rate+carry,q=numerator/rate;
        assert.equal(c.ratio(value,rate,carry,rate),Number(q<=U64));
        if(q<=U64){assert.equal(unsigned(c.q()),q);assert.equal(unsigned(c.r()),numerator%rate);}
        const phase=carry%rate,expected=value?(value*rate-phase+rate-1n)/rate:0n;
        assert.equal(c.delay(value,rate,rate,phase),1);assert.equal(unsigned(c.q()),expected);
      }
  assert.equal(c.ratio(U64,0n,0n,0n),0);
  for(const value of [0n,U64]){
    assert.equal(c.delay(value,0n,0n,0n),0);
    assert.equal(c.delay(value,9n,9n,9n),0);
  }
});
test('clock multiply-add/divide matches128-bit oracle across overflow boundaries',()=>{
  const c=create();let seed=0xfade12abn;
  const random=()=>seed=(seed*6364136223846793005n+1442695040888963407n)&U64;
  const cases=[[0n,U64,U64,1n],[U64,U64,U64,U64],[U64,U64,0n,U64],
    [1000000000000n,2000000000n,255999999999999n,256000000000000n]];
  for(let i=0;i<1200;i++)cases.push([random(),random(),random(),random()||1n]);
  for(const [a,b,carry,divisor] of cases){
    const n=a*b+carry,q=n/divisor;
    assert.equal(c.ratio(a,b,carry,divisor),Number(q<=U64));
    if(q<=U64){assert.equal(unsigned(c.q()),q);assert.equal(unsigned(c.r()),n%divisor);}
  }
  assert.equal(c.ratio(1n,1n,0n,0n),0);
});
test('clock deadline calculation preserves phase before rounding and detects overflow',()=>{
  const c=create();
  for(const denominator of [2n,19200000n,1000000000000n,256000000000000n])
    for(const rate of [1n,128000n,19600000n,2000000000n])
      for(const units of [0n,1n,2n,999n,65537000000000n])
        for(const phase of [0n,denominator/2n,denominator-1n]){
          const expected=units?(units*denominator-phase+rate-1n)/rate:0n;
          assert.equal(c.delay(units,denominator,rate,phase),Number(expected<=U64));
          if(expected<=U64)assert.equal(unsigned(c.q()),expected);
        }
  assert.equal(c.delay(1n,0n,1n,0n),0);assert.equal(c.delay(1n,10n,1n,10n),0);
});

test('deadline rounding retains every small fraction and native-product boundary',()=>{
  const c=create();
  const check=(units,denominator,rate,phase)=>{
    const product=units*denominator,expected=units?(product-phase+rate-1n)/rate:0n;
    // Preserve the original wide-path admission: its intermediate quotient
    // must fit too, even if later phase subtraction could reduce the result.
    const accepted=product/rate<=U64&&expected<=U64;
    const before=unsigned(c.q());assert.equal(c.delay(units,denominator,rate,phase),Number(accepted));
    if(accepted)assert.equal(unsigned(c.q()),expected);else assert.equal(unsigned(c.q()),before);
  };
  for(let d=1n;d<=24n;d++)for(let rate=1n;rate<=32n;rate++)
    for(let units=0n;units<=6n;units++)for(let phase=0n;phase<d;phase++)check(units,d,rate,phase);
  for(const d of [1n,2n,19200000n,1000000000000n,256000000000000n,U64]){
    const edge=U64/d;
    for(const units of new Set([0n,1n,edge,edge?edge-1n:0n,edge<U64?edge+1n:U64,U64]))
      for(const rate of [1n,2n,128000n,19200000n,2000000000n,U64])
        for(const phase of new Set([0n,d/2n,d-1n]))check(units,d,rate,phase);
  }
});
