import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compileAnalog} from './analog-test-build.mjs';
import {instrumentClockRatio,ratioSource,ratioHeader,ratioSupport,ratioGroupFields,
  readClockRatioCounters,validateClockRatioCounters} from '../scripts/lib/clock-ratio-counters.mjs';

const source=readFileSync(new URL('../../'+ratioSource,import.meta.url),'utf8').replaceAll('\r\n','\n'),names=[];
const instrumented=instrumentClockRatio(source,name=>{names.push(name);return names.length-1;});
const create=compileAnalog('clock-ratio-counters',[],`
#include <stdint.h>
static uint64_t counters[${names.length}],quotient=17,remainder=19;
#define MM_TRACE_HIT(id) (++counters[id])
${ratioHeader}
${instrumented}
${ratioSupport}
int ratio(uint64_t a,uint64_t b,uint64_t c,uint64_t d) { return device_clock_ratio(a,b,c,d,&quotient,&remainder); }
int delay(uint64_t a,uint64_t b,uint64_t c,uint64_t d) { return device_clock_delay(a,b,c,d,&quotient); }
uint64_t q(void) { return quotient; }
uint64_t r(void) { return remainder; }
uint64_t count(uint32_t id) { return id<${names.length}?counters[id]:0; }
void clear(void) { for(unsigned i=0;i<${names.length};i++)counters[i]=0;mm_ratio_reset(); }
`,{fixedMemoryPages:2});
const U64=0xffffffffffffffffn,u=n=>BigInt.asUintN(64,n);
const report=c=>readClockRatioCounters(c,names.map((name,i)=>({name,count:u(c.count(i)).toString()})));
function check(c,a,b,carry,divisor){
  const before=[u(c.q()),u(c.r())],n=a*b+carry,q=divisor?n/divisor:U64+1n,accepted=divisor!==0n&&q<=U64;
  assert.equal(c.ratio(a,b,carry,divisor),Number(accepted));
  assert.deepEqual([u(c.q()),u(c.r())],accepted?[q,n%divisor]:before,'Exact result or unchanged failed outputs');
}

test('instrumented ratio preserves uint64 results and failure writes against a BigInt oracle',()=>{
  const c=create(),edges=[0n,1n,2n,0xffffffffn,0x100000000n,U64-1n,U64];let checks=0,seed=0x131320261101n;
  for(const a of edges)for(const b of edges)for(const carry of [0n,1n,U64])for(const d of edges){check(c,a,b,carry,d);checks++;}
  const random=()=>seed=(seed*6364136223846793005n+1442695040888963407n)&U64;
  for(let i=0;i<5000;i++){check(c,random(),random(),random(),random());checks++;}
  assert.equal(checks,6029);assert.equal(report(c).paths.entry,String(checks));
});

test('actual branches form disjoint nested partitions including every wide failure',()=>{
  const c=create();
  for(const args of [[1n,2n,0n,0n],[3n,7n,1n,11n],
    [U64,2n,0n,1n],[U64,2n,1n,2n],[U64,2n,U64,2n],[U64,U64,U64,U64],
    [U64,U64,0n,U64],[U64,U64,0n,U64-1n],
    [U64-1n,U64,0n,U64],[U64-1n,U64,1n,U64-2n]])check(c,...args);
  const r=report(c);
  for(const name of ['entry','zero-divisor','short','wide','decomposed','whole-overflow','sum-overflow',
    'decomposed-ok','long-division','quotient-overflow','long-ok'])assert.ok(BigInt(r.paths[name])>0n,'Path '+name+' must execute');
});

test('delay callers retain phase subtraction and upward rounding',()=>{
  const c=create();
  for(const units of [0n,1n,47n,1n<<53n])for(const denominator of [1n,1000000000000n,256000000000000n])
    for(const rate of [1n,19200000n,1000000000000n])for(const phase of [0n,denominator-1n]){
      const before=u(c.q()),expected=units?(units*denominator-phase+rate-1n)/rate:0n,
        accepted=units===0n||(units*denominator/rate<=U64&&expected<=U64);
      assert.equal(c.delay(units,denominator,rate,phase),Number(accepted));assert.equal(u(c.q()),accepted?expected:before);
    }
  validateClockRatioCounters(report(c));
});

test('operand groups retain original values, extrema and overlapping classes',()=>{
  const c=create();for(const [a,carry]of [[0n,0n],[3n,4n],[0x100000000n,9n],[U64,U64]])check(c,a,7n,carry,9n);
  const r=report(c);assert.equal(r.untracked,'0');assert.deepEqual(r.groups,[{
    b:'7',divisor:'9',calls:'4',minA:'0',maxA:U64.toString(),minCarry:'0',maxCarry:U64.toString(),
    zeroA:'1',zeroCarry:'1',a32:'2',properCarry:'2'}]);
  assert.deepEqual(Object.keys(r.groups[0]),ratioGroupFields);
});

test('table overflow is counted without evicting groups or affecting arithmetic',()=>{
  const c=create();for(let i=0n;i<40n;i++)check(c,i,i+1n,0n,97n);
  const r=report(c);assert.equal(r.groups.length,32);assert.equal(r.untracked,'8');
  check(c,123n,1n,4n,97n);const s=report(c);assert.equal(s.groups[0].calls,'2');assert.equal(s.untracked,'8');
  assert.equal(c.mm_ratio_value(32,0),0n);assert.equal(c.mm_ratio_value(0,11),0n);
});

test('reset clears counts, operands and overflow between diagnostic workloads',()=>{
  const c=create();for(let i=0n;i<40n;i++)check(c,10n,i,3n,11n);
  c.clear();const r=report(c);assert.equal(r.paths.entry,'0');assert.deepEqual(r.groups,[]);assert.equal(r.untracked,'0');
  check(c,9n,5n,2n,7n);assert.equal(report(c).groups[0].calls,'1');
});

test('source instrumentation rejects missing or duplicate anchors',()=>{
  for(const bad of [source.replace('if (!divisor) return 0;','if (divisor==0) return 0;'),source+source])
    assert.throws(()=>instrumentClockRatio(bad,()=>0),/anchor differs/);
});

test('retained-data validation rejects broken partitions, duplicates, bounds and classes',()=>{
  const c=create();check(c,1n,2n,0n,3n);const r=report(c);
  for(const mutate of [x=>x.paths.entry='2',x=>delete x.paths.short,x=>x.groups.push(x.groups[0]),
    x=>x.groups[0].minA='2',x=>x.groups[0].zeroA='2',x=>x.groups[0].calls='0',x=>x.untracked='1',
    x=>x.groups[0].calls='01',x=>x.groups[0].maxCarry=(U64+1n).toString(),x=>x.groups[0].extra='private-field']){
    const changed=structuredClone(r);mutate(changed);assert.throws(()=>validateClockRatioCounters(changed));
  }
});
