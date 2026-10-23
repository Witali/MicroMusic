import test from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create = compileAnalog('adc', ['web-player/native/peripherals/analog_adc.c'], `
#include "analog_adc.h"
static analog_adc_t a;
void reset(int sample) { analog_adc_reset(&a, 5000000, 1100000, sample, 0); }
int advance(uint64_t t) { return analog_adc_advance(&a,t); }
int read_io(int io,uint64_t t) { uint8_t v=0; return analog_adc_read(&a,io,&v,t)?v:-1; }
int write_io(int io,int v,uint64_t t) { return analog_adc_write(&a,io,v,t); }
int input(int c,int uv,uint64_t t) { return analog_adc_input(&a,c,uv,t); }
int reference(int v,int bg,uint64_t t) { return analog_adc_reference(&a,v,bg,t); }
int flags(int v,uint64_t t) { return analog_adc_sources(&a,v,t); }
int pending(void) { return analog_adc_pending(&a); }
int ack(uint64_t t) { return analog_adc_ack(&a,t); }
int clock_run(int v,uint64_t t) { return analog_adc_clock_running(&a,v,t); }
int sleep_start(uint64_t t) { return analog_adc_noise_cancel_start(&a,t); }
uint64_t next_event(void) { return analog_adc_next_event(&a); }
uint64_t count(void) { return a.conversions; }
uint64_t lost(void) { return a.discarded_results; }
uint64_t sampled_at(void) { return a.sampled_at; }
uint64_t completed_at(void) { return a.completed_at; }
int invalid_reference(void) { return a.invalid_reference; }
`);
const B=3,L=4,H=5,A=6,M=7;
function adc(phase=27) { const a=create(); a.reset(phase); return a; }
function value(a,t) { return a.read_io(L,t) | (a.read_io(H,t)<<8); }

test('ADC register reset, masks, read-only data and monotonic timestamps',()=>{
  const a=adc();
  for(const io of [B,L,H,A,M]) assert.equal(a.read_io(io,0n),0);
  a.write_io(B,255,0n);a.write_io(M,255,0n);
  assert.equal(a.read_io(B,0n),0x47);assert.equal(a.read_io(M,0n),0x63);
  a.write_io(L,255,0n);a.write_io(H,255,0n);assert.equal(value(a,0n),0);
  assert.equal(a.read_io(8,0n),-1);assert.equal(a.input(4,123,0n),0);
  a.advance(10n);assert.equal(a.advance(9n),0);assert.equal(a.read_io(A,9n),-1);
});
test('first conversion start edge, S/H and completion include exact half-cycle phase',()=>{
  const a=adc();a.input(0,2500000,0n);a.write_io(A,0xc0,0n);
  assert.equal(a.next_event(),4n);a.advance(3n);assert.equal(a.count(),0n);
  a.advance(57n);assert.equal(a.sampled_at(),0n);a.advance(58n);
  assert.equal(a.sampled_at(),58n);a.input(0,0,59n);
  a.advance(103n);assert.equal(a.count(),0n);assert.equal(a.read_io(A,103n)&0x40,0x40);
  assert.equal(value(a,104n),512);assert.equal(a.completed_at(),104n);
  assert.equal(a.read_io(A,104n),0x90);assert.equal(a.next_event(),-1n);
});
test('first S/H datasheet discrepancy is an explicit configurable phase',()=>{
  const a=adc(29);a.input(0,2500000,0n);a.write_io(A,0xc0,0n);
  a.advance(58n);assert.equal(a.sampled_at(),0n);a.input(0,1250000,59n);
  assert.equal(value(a,104n),256);assert.equal(a.sampled_at(),62n);
});
test('normal conversion uses continuously running prescaler and 13 ADC clocks',()=>{
  const a=adc();a.input(0,1000000,0n);a.write_io(A,0xc0,0n);a.advance(104n);
  a.write_io(A,0xc0,105n);assert.equal(a.next_event(),108n);
  a.advance(159n);assert.equal(a.count(),1n);
  assert.equal(value(a,160n),204);assert.equal(a.count(),2n);assert.equal(a.sampled_at(),114n);
});
test('all /2 through /128 prescalers preserve source-clock timing',()=>{
  for(let code=0;code<8;code++) {
    const a=adc();const d=code<2?2:1<<code;a.write_io(A,0xc0|code,0n);
    const end=BigInt(52*d);a.advance(end-1n);assert.equal(a.count(),0n);
    a.advance(end);assert.equal(a.count(),1n);
  }
});
test('channel/reference latch at conversion start; ADLAR reformats immediately',()=>{
  const a=adc();a.input(0,1250000,0n);a.input(1,550000,0n);
  a.write_io(A,0xc0,0n);a.write_io(M,0x41,5n);
  assert.equal(value(a,104n),256);
  a.write_io(A,0xc0,104n);assert.equal(value(a,160n),512);
  a.write_io(M,0x61,160n);assert.equal(value(a,160n),512<<6);
  a.write_io(M,0x41,160n);assert.equal(value(a,160n),512);
});
test('channel changed while start is pending selects the new channel',()=>{
  const a=adc();a.input(2,3750000,0n);a.write_io(A,0xc0,0n);a.write_io(M,2,3n);
  assert.equal(value(a,104n),768);
});
test('ADCL locks result updates; completion IRQ still fires and lost result is discarded',()=>{
  const a=adc();a.input(0,2500000,0n);a.write_io(A,0xc8,0n);assert.equal(value(a,104n),512);
  assert.equal(a.read_io(L,104n),0);a.ack(104n);a.input(0,1250000,104n);
  a.write_io(A,0xc8,104n);a.advance(160n);
  assert.equal(a.pending(),1);assert.equal(a.lost(),1n);assert.equal(a.read_io(H,160n),2);
  assert.equal(value(a,160n),512);
  a.write_io(A,0xc8,160n);assert.equal(value(a,216n),256);
});
test('ADIF W1C, interrupt enable and vector acknowledgement',()=>{
  const a=adc();a.write_io(A,0xc0,0n);a.advance(104n);assert.equal(a.pending(),0);
  a.write_io(A,0x88,104n);assert.equal(a.pending(),1);
  a.write_io(A,0x98,104n);assert.equal(a.pending(),0);
  a.write_io(A,0xc8,104n);a.advance(160n);assert.equal(a.pending(),1);
  a.ack(160n);assert.equal(a.pending(),0);
});
test('ADSC zero does not cancel; ADEN zero aborts and next enable has first timing',()=>{
  const a=adc();a.write_io(A,0xc0,0n);a.write_io(A,0x80,10n);
  assert.equal(a.read_io(A,10n)&0x40,0x40);a.write_io(A,0,20n);a.advance(104n);
  assert.equal(a.count(),0n);a.write_io(A,0xc0,104n);a.advance(207n);assert.equal(a.count(),0n);
  a.advance(208n);assert.equal(a.count(),1n);
});
test('free running restarts without host calls or clearing ADIF; next channel starts before read',()=>{
  const a=adc();a.input(0,2500000,0n);a.input(1,1250000,0n);a.write_io(A,0xe0,0n);
  assert.equal(value(a,104n),512);a.write_io(M,1,104n);
  assert.equal(value(a,156n),512);assert.equal(value(a,208n),256);
  assert.equal(a.count(),3n);assert.equal(a.read_io(A,208n)&0x50,0x50);
  a.write_io(A,0x80,208n);a.advance(260n);assert.equal(a.count(),4n);
  assert.equal(a.read_io(A,260n)&0x40,0);
});
test('all six auto trigger sources use flag edges, ignore busy edges and held flags',()=>{
  for(let source=1;source<=6;source++) {
    const a=adc();a.write_io(B,source,0n);a.write_io(A,0xa0,0n);
    a.flags(1<<source,10n);assert.equal(a.next_event(),16n);
    a.flags(0,20n);a.flags(1<<source,21n);a.advance(116n);assert.equal(a.count(),1n);
    a.advance(200n);assert.equal(a.count(),1n);a.flags(0,200n);a.flags(1<<source,201n);
    a.advance(260n);assert.equal(a.count(),1n);a.advance(261n);assert.equal(a.count(),2n);
    assert.equal(a.sampled_at(),215n);assert.equal(a.completed_at(),261n);
  }
});
test('switching to an asserted auto source triggers; free running selection does not',()=>{
  const a=adc();a.flags(1<<3,0n);a.write_io(B,2,0n);a.write_io(A,0xa0,0n);
  a.write_io(B,3,10n);assert.equal(a.next_event(),16n);a.advance(116n);
  a.write_io(B,0,116n);a.advance(500n);assert.equal(a.count(),1n);
  a.write_io(B,7,500n);a.flags(0xff,500n);a.advance(1000n);assert.equal(a.count(),1n);
});
test('manual ADSC conversion remains available with auto triggering enabled',()=>{
  const a=adc();a.write_io(B,3,0n);a.write_io(A,0xe0,0n);a.advance(104n);
  assert.equal(a.count(),1n);a.advance(200n);assert.equal(a.count(),1n);
});
test('ideal fixed-point conversion clamps and uses injected references',()=>{
  for(const [uv,expected] of [[-1,0],[0,0],[1,0],[4995118,1023],[5000000,1023],[2000000000,1023]]) {
    const a=adc();a.input(0,uv,0n);a.write_io(A,0xc0,0n);assert.equal(value(a,104n),expected);
  }
  const a=adc();a.reference(3300000,1000000,0n);a.input(3,500000,0n);
  a.write_io(M,0x43,0n);a.write_io(A,0xc0,0n);assert.equal(value(a,104n),512);
  a.reference(0,0,104n);a.write_io(A,0xc0,104n);assert.equal(value(a,160n),0);
  assert.equal(a.invalid_reference(),1);
});
test('clock gating freezes prescaler and conversion deadlines including writes while stopped',()=>{
  const a=adc();a.write_io(A,0xc0,0n);a.clock_run(0,10n);a.advance(1000n);
  assert.equal(a.next_event(),-1n);assert.equal(a.count(),0n);
  a.clock_run(1,1010n);a.advance(1103n);assert.equal(a.count(),0n);a.advance(1104n);
  assert.equal(a.count(),1n);
  const b=adc();b.clock_run(0,0n);b.write_io(A,0xc0,100n);b.clock_run(1,1000n);
  b.advance(1103n);assert.equal(b.count(),0n);b.advance(1104n);assert.equal(b.count(),1n);
});
test('sleep noise-canceller starts only enabled single conversions with ADIE',()=>{
  const a=adc();a.write_io(A,0x88,0n);a.sleep_start(0n);a.advance(104n);assert.equal(a.count(),1n);
  for(const control of [0x80,0xa8,0x08]) {
    const b=adc();b.write_io(A,control,0n);b.sleep_start(0n);b.advance(1000n);assert.equal(b.count(),0n);
  }
});
