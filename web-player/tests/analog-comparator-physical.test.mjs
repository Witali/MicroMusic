import test from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_MASK as M} from '../lib/attiny13a-registers.js';

const create=compileAnalog('comparator-physical',['web-player/native/peripherals/analog_comparator.c'],`
#include "analog_comparator.h"
static analog_comparator_t c;
void reset(int propagation,int startup,int initial,uint64_t origin,uint64_t half) {
  analog_comparator_config_t config={propagation,startup,origin,initial};
  analog_comparator_reset(&c,&config,1100000,half);
}
int configure(uint32_t propagation,uint32_t startup,uint64_t now) { return analog_comparator_configure_physical(&c,propagation,startup,now); }
int wall(uint64_t now) { return analog_comparator_advance_ps(&c,now); }
int arm_first_rise(void) { return analog_comparator_arm_first_rise(&c); }
int advance(uint64_t half) { return analog_comparator_advance(&c,half); }
int input(int pin,int uv,uint64_t half) { return analog_comparator_input(&c,pin,uv,half); }
int reference(int uv,uint64_t half) { return analog_comparator_reference(&c,uv,half); }
int adc_regs(int a,int b,int m,uint64_t half) { return analog_comparator_adc(&c,a,b,m,half); }
int write_io(int value,uint64_t half) { return analog_comparator_write(&c,ANALOG_ACSR,value,half); }
int read_io(uint64_t half) { uint8_t value=0;return analog_comparator_read(&c,ANALOG_ACSR,&value,half)?value:-1; }
int clock_run(int run,uint64_t origin,uint64_t half) { return analog_comparator_clock_running(&c,run,origin,half); }
int sleep_disable(int off,uint64_t half) { return analog_comparator_sleep(&c,off,half); }
int ack(uint64_t half) { return analog_comparator_ack(&c,half); }
uint64_t next_half(void) { return analog_comparator_next_event(&c); }
uint64_t next_ps(void) { return analog_comparator_next_event_ps(&c); }
int value(int field) { switch(field) {
case 0:return c.raw;case 1:return c.sync1;case 2:return c.acsr;
case 3:return c.physical_enabled;case 4:return c.physical_fault;
case 5:return analog_comparator_pending(&c);default:return -1; } }
uint64_t detail(int field) { switch(field) {
case 0:return c.half_cycle;case 1:return c.physical_time_ps;
case 2:return c.propagation_at;case 3:return c.bandgap_ready_at;
case 4:return c.propagation_at_ps;case 5:return c.bandgap_ready_at_ps;
case 6:return c.synchronize_at;case 7:return c.propagation_delay_ps;
case 8:return c.bandgap_startup_delay_ps;case 9:return c.transitions;
case 10:return c.unsafe_control_changes;default:return 0; } }
`);
const MAX=0xffffffffffffffffn,u64=value=>BigInt.asUintN(64,value);
const half=c=>u64(c.detail(0)),wall=c=>u64(c.detail(1)),aco=c=>!!(c.value(2)&M.ACO);
const nextPs=c=>u64(c.next_ps()),nextHalf=c=>u64(c.next_half());
function make({propagation=0,startup=0,initial=0,legacyPropagation=7,legacyStartup=9,origin=0n,half:epoch=0n,now=0n}={}) {
  const c=create();c.reset(legacyPropagation,legacyStartup,initial,origin,epoch);
  assert.equal(c.configure(propagation,startup,now),1);return c;
}
const input=(c,pin,uv)=>assert.equal(c.input(pin,uv,half(c)),1);
const write=(c,value)=>assert.equal(c.write_io(value,half(c)),1);
const settle=(c,at)=>assert.equal(c.wall(at),1);
function edge(c,at,deliveredHalf) {
  assert.equal(c.advance(deliveredHalf-1n),1);
  settle(c,at);assert.equal(c.advance(deliveredHalf),1);
}
function snapshot(c) {
  return {values:Array.from({length:6},(_,n)=>c.value(n)),details:Array.from({length:11},(_,n)=>u64(c.detail(n)))};
}

test('reset-time selection replaces legacy raw timing and retains explicit output at arbitrary epochs',()=>{
  const epoch=1n<<60n,now=(1n<<60n)+123n;
  const c=make({initial:1,legacyPropagation:3,propagation:7,half:epoch,now});
  assert.equal(half(c),epoch);assert.equal(wall(c),now);assert.equal(aco(c),true);
  assert.equal(c.value(0),1);assert.equal(c.value(1),1);assert.equal(nextPs(c),now+7000n);
  assert.equal(u64(c.detail(2)),MAX);assert.equal(u64(c.detail(3)),MAX);assert.equal(nextHalf(c),MAX);
  settle(c,now+6999n);assert.equal(c.value(0),1);settle(c,now+7000n);
  assert.equal(c.value(0),0);assert.equal(aco(c),true);assert.equal(nextHalf(c),epoch+2n);
  assert.equal(c.advance(epoch+4n),1);assert.equal(aco(c),false);
});
test('analog settling completes through a held source without delivering digital phases or IRQs',()=>{
  const c=make({propagation:100});write(c,M.ACIE);input(c,0,2000000);
  assert.equal(nextPs(c),100000n);settle(c,99999n);assert.equal(c.value(0),0);
  settle(c,10000000n);assert.equal(c.value(0),1);assert.equal(half(c),0n);
  assert.equal(aco(c),false);assert.equal(c.value(5),0);assert.equal(nextHalf(c),2n);
  edge(c,11000000n,1n);edge(c,11001000n,2n);assert.equal(aco(c),false);
  edge(c,15000000n,3n);edge(c,17000000n,4n);assert.equal(aco(c),true);assert.equal(c.value(5),1);
});
test('initial-low CLKI first rise samples at half zero after an arbitrarily long analog hold',()=>{
  const c=make({propagation:5});write(c,M.ACIE);input(c,0,2000000);settle(c,10000000n);
  assert.equal(half(c),0n);assert.equal(nextHalf(c),2n);assert.equal(c.value(0),1);
  assert.equal(c.arm_first_rise(),1);assert.equal(nextHalf(c),0n);
  assert.equal(c.value(1),0);assert.equal(aco(c),false);assert.equal(c.value(5),0);
  assert.equal(c.advance(0n),1);assert.equal(c.value(1),1);
  assert.equal(aco(c),false);assert.equal(c.value(5),0);assert.equal(nextHalf(c),2n);
  assert.equal(c.advance(2n),1);assert.equal(aco(c),true);assert.equal(c.value(5),1);
});
test('repeated first-rise arms and zero-time advances cannot sample a second digital stage twice',()=>{
  const c=make();write(c,M.ACIE);input(c,0,2000000);settle(c,1000n);
  assert.equal(c.arm_first_rise(),1);assert.equal(c.arm_first_rise(),1);
  assert.equal(c.advance(0n),1);assert.equal(c.value(1),1);assert.equal(aco(c),false);
  assert.equal(c.arm_first_rise(),1);assert.equal(nextHalf(c),2n);
  assert.equal(c.advance(0n),1);assert.equal(aco(c),false);assert.equal(c.value(5),0);
  assert.equal(c.advance(2n),1);assert.equal(aco(c),true);assert.equal(u64(c.detail(9)),1n);
});
test('a first rise with no raw work is consumed before later input changes',()=>{
  const c=make();assert.equal(c.arm_first_rise(),1);assert.equal(nextHalf(c),MAX);
  assert.equal(c.advance(0n),1);assert.equal(aco(c),false);
  input(c,0,2000000);settle(c,0n);assert.equal(nextHalf(c),2n);
  assert.equal(c.arm_first_rise(),1);assert.equal(nextHalf(c),2n);
  assert.equal(c.advance(0n),1);assert.equal(c.value(1),0);
  assert.equal(c.advance(2n),1);assert.equal(aco(c),false);
  assert.equal(c.advance(4n),1);assert.equal(aco(c),true);
});
test('a gated first-rise clock is rejected, while disabled comparators consume the edge without work',()=>{
  const gated=make();assert.equal(gated.clock_run(0,0n,0n),1);
  assert.equal(gated.arm_first_rise(),0);assert.equal(gated.value(4),3);
  for(const gate of ['ACD','sleep']) {
    const c=make();if(gate==='ACD')write(c,M.ACD);else assert.equal(c.sleep_disable(1,0n),1);
    input(c,0,2000000);assert.equal(c.arm_first_rise(),1);assert.equal(nextHalf(c),MAX);
    assert.equal(c.advance(0n),1);assert.equal(c.value(5),0);
    if(gate==='ACD')write(c,0);else assert.equal(c.sleep_disable(0,0n),1);
    settle(c,0n);assert.equal(nextHalf(c),2n);assert.equal(c.arm_first_rise(),1);
    assert.equal(nextHalf(c),2n);assert.equal(c.advance(0n),1);assert.equal(c.value(1),0);
  }
});
test('first-rise admission requires physical mode and the unprogressed reset half-zero epoch',()=>{
  const legacy=create();legacy.reset(0,0,0,0n,0n);
  assert.equal(legacy.arm_first_rise(),0);assert.equal(legacy.value(4),3);
  const later=make({half:100n});assert.equal(later.arm_first_rise(),0);assert.equal(later.value(4),3);
  const progressed=make();assert.equal(progressed.advance(1n),1);
  assert.equal(progressed.arm_first_rise(),0);assert.equal(progressed.value(4),3);
});
test('delivered half counts and physical ns remain separate when clock cadence changes',()=>{
  const c=make({propagation:200});input(c,0,2000000);
  assert.equal(c.advance(1000n),1);assert.equal(wall(c),0n);assert.equal(c.value(0),0);
  assert.equal(nextPs(c),200000n);settle(c,200000n);
  assert.equal(c.value(0),1);assert.equal(nextHalf(c),1002n);
  edge(c,5000000n,1001n);edge(c,10000000n,1002n);
  edge(c,50000000n,1003n);edge(c,100000000n,1004n);
  assert.equal(aco(c),true);assert.equal(wall(c),100000000n);
});
test('clock gating stops only digital synchronization while physical propagation continues',()=>{
  const c=make({propagation:50});assert.equal(c.clock_run(0,0n,0n),1);input(c,0,2000000);
  settle(c,1000000n);assert.equal(c.value(0),1);assert.equal(nextHalf(c),MAX);assert.equal(aco(c),false);
  assert.equal(c.clock_run(1,0n,0n),1);assert.equal(nextHalf(c),2n);
  edge(c,2000000n,1n);edge(c,4000000n,2n);edge(c,5000000n,3n);edge(c,6000000n,4n);
  assert.equal(aco(c),true);
});
test('short inertial pulses during a clock hold disappear before any raw or synchronized transition',()=>{
  const c=make({propagation:100});input(c,0,2000000);settle(c,99999n);input(c,0,0);
  assert.equal(nextPs(c),MAX);settle(c,10000000n);
  assert.equal(c.value(0),0);assert.equal(nextHalf(c),MAX);assert.equal(c.advance(10n),1);
  assert.equal(aco(c),false);assert.equal(u64(c.detail(9)),0n);
});
test('a sampled pulse survives a later analog change while digital clocks are held',()=>{
  const c=make();input(c,0,2000000);settle(c,0n);
  edge(c,10n,1n);edge(c,20n,2n);assert.equal(c.value(1),1);assert.equal(aco(c),false);
  settle(c,30n);input(c,0,0);settle(c,30n);settle(c,10000000n);
  assert.equal(c.value(0),0);assert.equal(c.value(1),1);assert.equal(aco(c),false);
  edge(c,10000010n,3n);edge(c,10000020n,4n);assert.equal(aco(c),true);
  edge(c,10000030n,5n);edge(c,10000040n,6n);assert.equal(aco(c),false);assert.equal(u64(c.detail(9)),2n);
});
test('an existing physical deadline precedes a tied rising edge',()=>{
  const c=make({propagation:10});input(c,0,2000000);
  edge(c,5000n,1n);edge(c,10000n,2n);
  assert.equal(c.value(1),1);assert.equal(aco(c),false);
  edge(c,15000n,3n);edge(c,20000n,4n);assert.equal(aco(c),true);
});
test('a zero-delay input injected after a tied edge waits for the next eligible rise',()=>{
  const c=make();edge(c,5000n,1n);edge(c,10000n,2n);
  input(c,0,2000000);settle(c,10000n);assert.equal(c.value(1),0);assert.equal(nextHalf(c),4n);
  edge(c,15000n,3n);edge(c,20000n,4n);assert.equal(aco(c),false);
  edge(c,25000n,5n);edge(c,30000n,6n);assert.equal(aco(c),true);
});
test('physical startup and propagation execute chronologically in ns while clocks are absent',()=>{
  const c=make({propagation:10,startup:20});settle(c,5000n);write(c,M.ACBG);
  assert.equal(nextPs(c),25000n);settle(c,24999n);assert.equal(c.value(0),0);
  settle(c,25000n);assert.equal(nextPs(c),35000n);settle(c,34999n);assert.equal(c.value(0),0);
  settle(c,35000n);assert.equal(c.value(0),1);assert.equal(aco(c),false);
  assert.equal(u64(c.detail(8)),20000n);assert.equal(u64(c.detail(7)),10000n);
  edge(c,40000n,1n);edge(c,50000n,2n);edge(c,60000n,3n);edge(c,70000n,4n);
  assert.equal(aco(c),true);
});
test('reference and mux changes use physical inertial delays without restarting completed startup',()=>{
  const c=make({propagation:10,startup:20});input(c,1,1000000);write(c,M.ACBG);settle(c,30000n);
  assert.equal(c.value(0),1);assert.equal(c.reference(900000,half(c)),1);
  assert.equal(nextPs(c),40000n);settle(c,40000n);assert.equal(c.value(0),0);
  assert.equal(c.reference(1200000,half(c)),1);assert.equal(nextPs(c),50000n);
  settle(c,50000n);assert.equal(c.value(0),1);
  for(const [mux,pin]of [5,2,4,3].entries()) {
    const a=make({propagation:10});input(a,0,2000000);input(a,1,3000000);input(a,pin,1000000);
    assert.equal(a.adc_regs(0,M.ACME,mux,half(a)),1);settle(a,10000n);assert.equal(a.value(0),1);
    assert.equal(a.adc_regs(M.ADEN,M.ACME,mux,half(a)),1);settle(a,20000n);assert.equal(a.value(0),0);
  }
});
for(const gate of ['ACD','sleep'])test(`${gate} cancels wall deadlines and restart uses the new wall epoch`,()=>{
  const c=make({propagation:10,startup:20});write(c,M.ACBG);settle(c,5000n);
  if(gate==='ACD')write(c,M.ACBG|M.ACD);else assert.equal(c.sleep_disable(1,half(c)),1);
  assert.equal(nextPs(c),MAX);assert.equal(nextHalf(c),MAX);settle(c,1000000n);
  assert.equal(c.value(0),0);assert.equal(aco(c),false);
  if(gate==='ACD')write(c,M.ACBG);else assert.equal(c.sleep_disable(0,half(c)),1);
  assert.equal(nextPs(c),1020000n);settle(c,1030000n);assert.equal(c.value(0),1);
});
test('physical IRQ senses, W1C and acknowledgment retain the existing synchronized semantics',()=>{
  for(const sense of [0,1,2,3]) {
    const c=make({propagation:1});write(c,sense|M.ACIE);input(c,0,2000000);settle(c,1000n);
    for(let n=1n;n<=4n;n++)edge(c,1000n+n,n);
    assert.equal(c.value(5),[0,3].includes(sense)?1:0);
    write(c,sense|M.ACIE|M.ACI);assert.equal(c.value(5),0);
    input(c,0,0);settle(c,2004n);
    for(let n=5n;n<=8n;n++)edge(c,2000n+n,n);
    assert.equal(c.value(5),[0,2].includes(sense)?1:0);
    assert.equal(c.ack(half(c)),1);assert.equal(c.value(5),0);
  }
});
test('one large wall advance equals subdivided advancement through startup and raw completion',()=>{
  const a=make({propagation:3,startup:7}),b=make({propagation:3,startup:7});
  for(const c of [a,b])write(c,M.ACBG);
  settle(a,20000n);for(let t=1n;t<=20000n;t+=7n)settle(b,t);settle(b,20000n);
  assert.deepEqual(snapshot(a),snapshot(b));
});
test('uint32 ns and timestamps beyond 2^53 retain exact independent deadlines',()=>{
  const now=(1n<<60n)+11n,c=make({propagation:0xffffffff,startup:0xffffffff,now});
  write(c,M.ACBG);const startup=now+4294967295000n;
  assert.equal(nextPs(c),startup);settle(c,startup);
  assert.equal(nextPs(c),startup+4294967295000n);settle(c,startup+4294967295000n);
  assert.equal(c.value(0),1);assert.equal(half(c),0n);
});
test('reversed physical time faults immediately and reset restores fresh configuration at global epochs',()=>{
  const c=make({propagation:1,now:100n});assert.equal(c.wall(99n),0);
  assert.equal(c.value(4),1);assert.equal(wall(c),100n);assert.equal(nextPs(c),MAX);
  for(const call of [()=>c.advance(1n),()=>c.input(0,2000000,0n),()=>c.reference(1,0n),
    ()=>c.adc_regs(0,0,0,0n),()=>c.write_io(0,0n),()=>c.read_io(0n),
    ()=>c.clock_run(0,0n,0n),()=>c.sleep_disable(1,0n),()=>c.ack(0n)])
    assert.ok(call()<=0);
  c.reset(3,5,1,0n,1n<<50n);assert.equal(c.configure(1,2,1n<<60n),1);
  assert.equal(c.value(4),0);assert.equal(aco(c),true);assert.equal(nextPs(c),(1n<<60n)+1000n);
});
for(const late of ['advance','read','input','repeat'])test(`reject ${late} before physical reconfiguration instead of restarting work`,()=>{
  const c=create();c.reset(3,5,0,0n,100n);
  if(late==='advance')assert.equal(c.advance(100n),1);
  if(late==='read')assert.equal(c.read_io(100n),0);
  if(late==='input')assert.equal(c.input(0,2000000,100n),1);
  if(late==='repeat')assert.equal(c.configure(1,2,500n),1);
  assert.equal(c.configure(1,2,1000n),0);assert.equal(c.value(4),3);
});
test('wall advancement cannot silently enable a physical profile',()=>{
  const c=create();c.reset(0,0,0,0n,0n);assert.equal(c.wall(1n),0);assert.equal(c.value(4),3);
});
test('sentinel and overflowing physical deadlines fail without wrapped events',()=>{
  for(const now of [MAX-1000n,MAX-999n]) {
    const c=make({propagation:1,now});assert.equal(c.input(0,2000000,0n),0);
    assert.equal(c.value(4),2);assert.equal(nextPs(c),MAX);assert.equal(c.value(0),0);
  }
  const c=make({propagation:1,now:MAX-1001n});input(c,0,2000000);
  assert.equal(nextPs(c),MAX-1n);settle(c,MAX-1n);assert.equal(c.value(0),1);
  const zero=make({now:MAX});assert.equal(zero.input(0,2000000,0n),0);assert.equal(zero.value(4),2);
});
for(const mutation of ['reference','mux','control','reenable','sleep'])test(`${mutation} returns a physical overflow at its own mutation boundary`,()=>{
  const c=make({propagation:1});
  if(mutation==='reference'){input(c,1,2000000);write(c,M.ACBG);}
  if(mutation==='mux'){input(c,1,2000000);input(c,0,1000000);}
  if(mutation==='reenable'){write(c,M.ACD);input(c,0,2000000);}
  if(mutation==='sleep'){assert.equal(c.sleep_disable(1,0n),1);input(c,0,2000000);}
  settle(c,MAX-1000n);
  const result=mutation==='reference'?c.reference(3000000,0n):mutation==='mux'?c.adc_regs(0,M.ACME,1,0n):
    mutation==='control'?c.write_io(M.ACBG,0n):mutation==='reenable'?c.write_io(0,0n):c.sleep_disable(0,0n);
  assert.equal(result,0);assert.equal(c.value(4),2);assert.equal(nextPs(c),MAX);
});
test('startup overflow is returned by the ACBG write and completion overflow by wall advance',()=>{
  const startup=make({startup:1,now:MAX-1000n});assert.equal(startup.write_io(M.ACBG,0n),0);assert.equal(startup.value(4),2);
  const chained=make({startup:1,propagation:1,now:MAX-1500n});write(chained,M.ACBG);
  assert.equal(chained.wall(MAX-500n),0);assert.equal(chained.value(4),2);assert.equal(chained.value(0),0);
});
test('digital sentinel overflow in physical mode is returned by settling, clock controls and phase advancement',()=>{
  const settleOverflow=make({half:MAX-1n});input(settleOverflow,0,2000000);
  assert.equal(settleOverflow.wall(0n),0);assert.equal(settleOverflow.value(4),2);
  const control=make();assert.equal(control.clock_run(0,0n,0n),1);input(control,0,2000000);settle(control,0n);
  assert.equal(control.advance(MAX-1n),1);assert.equal(control.clock_run(1,0n,MAX-1n),0);assert.equal(control.value(4),2);
  const phase=make({half:MAX-3n});input(phase,0,2000000);settle(phase,0n);
  assert.equal(nextHalf(phase),MAX-1n);assert.equal(phase.advance(MAX-1n),0);assert.equal(phase.value(4),2);
});
