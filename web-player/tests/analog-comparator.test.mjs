import test from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';

const create = compileAnalog('comparator', ['web-player/native/peripherals/analog_comparator.c'], `
#include "analog_comparator.h"
static analog_comparator_t c;
void reset(int propagation,int startup,int initial,int origin) {
  analog_comparator_config_t config={propagation,startup,origin,initial};
  analog_comparator_reset(&c,&config,1100000,0);
}
int advance(uint64_t t) { return analog_comparator_advance(&c,t); }
int read_io(int io,uint64_t t) { uint8_t v=0; return analog_comparator_read(&c,io,&v,t)?v:-1; }
int write_io(int io,int v,uint64_t t) { return analog_comparator_write(&c,io,v,t); }
int input(int pin,int uv,uint64_t t) { return analog_comparator_input(&c,pin,uv,t); }
int reference(int uv,uint64_t t) { return analog_comparator_reference(&c,uv,t); }
int adc_regs(int a,int b,int m,uint64_t t) { return analog_comparator_adc(&c,a,b,m,t); }
int pending(void) { return analog_comparator_pending(&c); }
int ack(uint64_t t) { return analog_comparator_ack(&c,t); }
int clock_run(int run,uint64_t origin,uint64_t t) { return analog_comparator_clock_running(&c,run,origin,t); }
int sleep_disable(int disabled,uint64_t t) { return analog_comparator_sleep(&c,disabled,t); }
uint64_t next_event(void) { return analog_comparator_next_event(&c); }
uint64_t transitions(void) { return c.transitions; }
uint64_t unsafe_changes(void) { return c.unsafe_control_changes; }
`);
function comparator(p=0,bg=0,initial=0,origin=0) { const c=create();c.reset(p,bg,initial,origin);return c; }
const read=(c,t)=>c.read_io(8,t);
const output=(c,t)=>(read(c,t)>>5)&1;

test('comparator ACSR reset and masks; ACO is read-only and ACI is W1C',()=>{
  const c=comparator();assert.equal(read(c,0n),0);assert.equal(c.next_event(),-1n);
  c.write_io(8,0xff,0n);assert.equal(read(c,0n),0xcb);
  assert.equal(c.read_io(7,0n),-1);assert.equal(c.write_io(7,0,0n),0);
  assert.equal(c.input(6,0,0n),0);c.advance(1n);assert.equal(c.advance(0n),0);
});
test('two clock stages introduce 1..2 CPU cycles after supplied propagation delay',()=>{
  const c=comparator(3);c.input(0,2000000,0n);
  assert.equal(c.next_event(),3n);assert.equal(output(c,5n),0);
  assert.equal(output(c,6n),1);assert.equal(read(c,6n)&0x10,0x10);
  const d=comparator(0,0,0,1);d.input(0,2000000,0n);
  assert.equal(output(d,2n),0);assert.equal(output(d,3n),1);
});
test('ideal voltage comparison includes negative values and an explicit low tie convention',()=>{
  const c=comparator();c.input(0,-100,0n);c.input(1,-200,0n);
  assert.equal(output(c,4n),1);c.input(1,-100,4n);assert.equal(output(c,8n),0);
});
test('toggle/falling/rising senses set ACI independently of ACIE; reserved mode is inactive',()=>{
  for(const sense of [0,1,2,3]) {
    const c=comparator();c.write_io(8,sense,0n);c.input(0,2000000,0n);c.advance(4n);
    assert.equal(read(c,4n)&0x10,[0,3].includes(sense)?0x10:0);
    assert.equal(c.pending(),0);c.ack(4n);c.input(0,0,4n);c.advance(8n);
    assert.equal(read(c,8n)&0x10,[0,2].includes(sense)?0x10:0);
  }
});
test('ACIE gates pending; ACI survives writes of zero, clears with one and vector ack',()=>{
  const c=comparator();c.input(0,2000000,0n);c.advance(4n);assert.equal(c.pending(),0);
  c.write_io(8,8,4n);assert.equal(c.pending(),1);c.write_io(8,0x18,4n);assert.equal(c.pending(),0);
  c.input(0,0,4n);c.advance(8n);assert.equal(c.pending(),1);c.ack(8n);assert.equal(c.pending(),0);
});
test('ADC-disabled ACME routes every channel; ADEN or cleared ACME selects AIN1',()=>{
  const channelPin=[5,2,4,3];
  for(let mux=0;mux<4;mux++) {
    const c=comparator();c.input(0,2000000,0n);c.input(1,3000000,0n);
    c.input(channelPin[mux],1000000,0n);c.adc_regs(0,0x40,mux,0n);
    assert.equal(output(c,4n),1);c.adc_regs(0x80,0x40,mux,4n);assert.equal(output(c,8n),0);
    c.adc_regs(0,0x40,mux,8n);assert.equal(output(c,12n),1);
    c.adc_regs(0,0,mux,12n);assert.equal(output(c,16n),0);
  }
});
test('ACBG replaces AIN0 with supplied bandgap and models explicit startup delay',()=>{
  const c=comparator(2,10);c.input(1,1000000,0n);c.write_io(8,0x40,0n);
  assert.equal(c.next_event(),10n);assert.equal(output(c,15n),0);
  assert.equal(output(c,16n),1);c.reference(900000,16n);assert.equal(output(c,22n),0);
  c.input(0,2000000,22n);c.write_io(8,0,22n);assert.equal(output(c,28n),1);
});
test('short inertial pulses disappear before propagation, while sampled pulses traverse both stages',()=>{
  const c=comparator(5);c.input(0,2000000,0n);c.input(0,0,4n);c.advance(20n);
  assert.equal(c.transitions(),0n);
  const d=comparator();d.input(0,2000000,0n);d.advance(2n);d.input(0,0,3n);
  assert.equal(output(d,4n),1);assert.equal(output(d,6n),0);assert.equal(d.transitions(),2n);
});
test('input changes on an existing event timestamp are applied after that event',()=>{
  const c=comparator();c.input(0,2000000,0n);c.input(0,0,2n);
  assert.equal(output(c,4n),1);assert.equal(output(c,6n),0);
});
test('ACD and power-down disable halt comparisons without rewriting readable controls',()=>{
  const c=comparator();c.write_io(8,0x80,0n);c.input(0,2000000,0n);c.advance(20n);
  assert.equal(output(c,20n),0);c.write_io(8,0,20n);assert.equal(output(c,24n),1);
  c.sleep_disable(1,24n);c.input(0,0,24n);assert.equal(output(c,100n),1);
  assert.equal(read(c,100n)&0x80,0);c.sleep_disable(0,100n);assert.equal(output(c,104n),0);
});
test('clock gating freezes synchronizers while analog propagation continues',()=>{
  const c=comparator(3);c.clock_run(0,0n,0n);c.input(0,2000000,0n);c.advance(20n);
  assert.equal(output(c,20n),0);assert.equal(c.next_event(),-1n);
  c.clock_run(1,0n,20n);assert.equal(output(c,23n),0);assert.equal(output(c,24n),1);
});
test('unsafe ACD/ACIS writes with ACIE enabled are diagnosed without inventing spurious IRQs',()=>{
  const c=comparator();c.write_io(8,8,0n);c.write_io(8,0x0b,0n);
  assert.equal(c.unsafe_changes(),1n);assert.equal(c.pending(),0);
  c.write_io(8,0x8b,0n);assert.equal(c.unsafe_changes(),2n);
});
test('reset ACO is explicit because the hardware reset value is unspecified',()=>{
  const c=comparator(0,0,1);assert.equal(output(c,0n),1);
  assert.equal(output(c,4n),0);assert.equal(c.transitions(),1n);
});

const createSystem=compileAnalog('combined', ['web-player/native/peripherals/analog_adc.c',
  'web-player/native/peripherals/analog_comparator.c','web-player/native/peripherals/analog.c'], `
#include "analog.h"
static analog_t a;
void reset(void) { analog_comparator_config_t c={0}; analog_reset(&a,5000000,1100000,27,&c,0); }
int advance(uint64_t t) { return analog_advance(&a,t); }
int read_io(int io,uint64_t t) { uint8_t v=0;return analog_read(&a,io,&v,t)?v:-1; }
int write_io(int io,int v,uint64_t t) { return analog_write(&a,io,v,t); }
int input(int pin,int uv,uint64_t t) { return analog_input(&a,pin,uv,t); }
int flags(int v,uint64_t t) { return analog_sources(&a,v,t); }
int pending(void) { return analog_pending(&a); }
int ack(int vector,uint64_t t) { return analog_ack(&a,vector,t); }
uint64_t count(void) { return a.adc.conversions; }
uint64_t next_event(void) { return analog_next_event(&a); }
`);
test('comparator ACI routes to ADC auto trigger in C without enabling comparator IRQ',()=>{
  const a=createSystem();a.reset();a.input(5,2500000,0n);a.input(0,2000000,0n);
  a.write_io(3,1,0n);a.write_io(6,0xa8,0n);a.advance(109n);assert.equal(a.count(),0n);
  a.advance(110n);assert.equal(a.count(),1n);assert.equal(a.pending(),1<<9);
  assert.equal(a.read_io(4,110n)|(a.read_io(5,110n)<<8),512);
  a.advance(200n);assert.equal(a.count(),1n);a.ack(9,200n);a.ack(5,200n);
  a.input(0,0,200n);a.advance(264n);assert.equal(a.count(),2n);
  assert.equal(a.ack(7,264n),0);
});
test('combined register writes share ADC multiplexer; external flags do not overwrite comparator flag',()=>{
  const a=createSystem();a.reset();a.input(0,2000000,0n);a.input(1,3000000,0n);
  a.input(2,1000000,0n);a.write_io(7,1,0n);a.write_io(3,0x40,0n);
  assert.equal(a.read_io(8,4n)&0x20,0x20);
  a.write_io(6,0x80,4n);assert.equal(a.read_io(8,8n)&0x20,0);
  assert.equal(a.read_io(0x14,8n),-1,'DIDR0 belongs to GPIO');
  a.flags(0x7e,8n);assert.equal(a.read_io(8,8n)&0x10,0x10);
});
test('combined event schedule is invariant to batch size for deterministic external inputs',()=>{
  const a=createSystem(),b=createSystem();
  for(const s of [a,b]) {s.reset();s.input(0,2000000,0n);s.input(5,1234567,0n);s.write_io(3,1,0n);s.write_io(6,0xa8,0n);}
  a.advance(1000n);for(let t=1n;t<=1000n;t++) b.advance(t);
  for(const io of [3,4,5,6,7,8]) assert.equal(a.read_io(io,1000n),b.read_io(io,1000n));
  assert.equal(a.count(),b.count());assert.equal(a.pending(),b.pending());
});
