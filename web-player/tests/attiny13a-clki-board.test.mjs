import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync} from 'node:fs';
import {join, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {compileAnalog} from './analog-test-build.mjs';

// Select another checkout only while its board integration is under review.
// The committed test normally compiles its own real C board, without a CPU,
// opcode fixture or host imports. No production sources are copied or edited.
const testRoot=fileURLToPath(new URL('../../',import.meta.url));
const nativeRoot=process.env.MICROMUSIC_CLKI_NATIVE_ROOT||testRoot;
const native=join(nativeRoot,'web-player/native');
const sourcePath=p=>relative(testRoot,join(native,p));
const sources=readdirSync(join(native,'peripherals')).sort()
  .filter(name=>name.endsWith('.c')&&!/(?:^|[.\-_])tests?(?:[.\-_]|$)/i.test(name))
  .map(name=>sourcePath('peripherals/'+name));
for(const name of ['reset_input.c','clki_input.c','clki_clock.c'])
  sources.push(sourcePath('devices/attiny13a/'+name));
const header=join(native,'peripherals/device.h').replaceAll('\\','/');
const create=compileAnalog('attiny13a-clki-board',sources,`
#include "${header}"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
static attiny13a_clki_edge_t edges[513];
static uint64_t consumed;
int configure(int key,int value) { return device_configure(key,value); }
int configure_clki(int field,int value) { return device_configure_clki(field,value); }
int setup(int initial,int low,int profile,int wake_halves) {
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 if(!device_configure(DEVICE_CFG_FUSE_LOW,low)||
    !device_configure(DEVICE_CFG_FUSE_STARTUP_PROFILE,profile)||
    !device_configure(DEVICE_CFG_WAKE_STARTUP_BASE_HALF,wake_halves)||
    !device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS)||
    !device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,9600000)||
    !device_configure_clki(1,initial)||!device_configure_clki(0,1))return 0;
 return device_init(data,flash,eeprom);
}
void set_edge(unsigned i,uint64_t at,int level) {
 if(i<513)edges[i]=(attiny13a_clki_edge_t){at,(uint8_t)level};
}
int enqueue(unsigned n,uint64_t horizon) { return device_clki_enqueue(edges,n,horizon); }
int hold(uint64_t horizon) { return device_clki_enqueue(0,0,horizon); }
int span(uint64_t halves,uint64_t wall) {
 consumed=UINT64_MAX;return device_advance_half_until_ps(halves,wall,&consumed);
}
uint64_t used(void) { return consumed; }
uint64_t now(void) { return device_time_ps(); }
uint64_t half(void) { return device_virtual_half(); }
uint64_t horizon(void) { return device_clki_horizon_ps(); }
int queued(void) { return device_clki_count(); }
int free_edges(void) { return device_clki_free(); }
int level(void) { return device_clki_level(); }
int status(void) { return device_clki_status(); }
int aligned(void) { return device_clki_aligned(); }
uint64_t startup_ck(void) { return device_clki_startup_ck(); }
int physical(void) { return device_physical_mode(); }
int oscillator(void) { return device_oscillator_hz(); }
int divisor(void) { return device_clkpr_divisor(); }
int halted(void) { return device_halted(); }
int starting(void) { return device_starting(); }
int held(void) { return device_reset_held(); }
int requested(void) { return device_reset_requested(); }
void reset(int flags) { device_reset(flags); }
int phase(void) { return device_sleep_phase(); }
int irq(void) { return device_pending_irqs(); }
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
int read_io(int address) { return device_read(address); }
unsigned write_io(int address,int value) { return device_write(address,value,255); }
void control(int command) { device_control(command,0,0); }
void unbounded(unsigned cycles) { device_advance(cycles); }
uint64_t wait_until(uint64_t at) { return device_wait_until_ps(at); }
int pins(uint64_t at,int mask,int levels) { return device_inject_digital_ps(at,mask,levels); }
int analog(uint64_t at,int pin,int uv) { return device_inject_analog_ps(at,pin,uv); }
int eeprom_byte(int address) { return eeprom[address]; }
void clear_events(void) { device_clear_pin_events(); }
unsigned event_count(void) { unsigned n;device_pin_events_ps(&n);return n; }
uint64_t event_at(unsigned i) { unsigned n;const device_pin_event_ps_t *p=device_pin_events_ps(&n);return i<n?p[i].time_ps:UINT64_MAX; }
int event_levels(unsigned i) { unsigned n;const device_pin_event_ps_t *p=device_pin_events_ps(&n);return i<n?p[i].levels:0; }
`);
const IO={PINB:0x16,DDRB:0x17,PORTB:0x18,EECR:0x1c,EEDR:0x1d,EEAR:0x1e,
  WDTCR:0x21,ADCL:0x04,ADCH:0x05,ADCSRA:0x06,ADMUX:0x07,
  CLKPR:0x26,PCMSK:0x15,TCCR0B:0x33,TCNT0:0x32,MCUSR:0x34,MCUCR:0x35,GIMSK:0x3b};
function board({initial=1,low=0x70,profile=0,wakeHalves=0}={}) {
  const c=create();assert.equal(c.setup(initial,low,profile,wakeHalves),1);
  assert.equal(c.fault(),0);return c;
}
function enqueue(c,events,horizon=events.at(-1)?.[0]??c.horizon()) {
  events.forEach(([at,level],i)=>c.set_edge(i,at,level));
  assert.equal(c.enqueue(events.length,horizon),1);return horizon;
}
function waveform(start,count,{step=100000n,initial=1}={}) {
  return Array.from({length:count},(_,i)=>[start+BigInt(i+1)*step,(initial+i+1)&1]);
}
function span(c,halves,wall,{result=1,used=halves}={}) {
  assert.equal(c.span(BigInt(halves),wall),result,`fault=${c.fault()}/${c.detail()}`);
  assert.equal(c.used(),BigInt(used));assert.equal(c.fault(),0);
}

// Official basis: DS40002307A sections6.1..6.3, Table6-3, sections7/8,
// Figure10-3 and section18.4.2/Table18-3. CKSEL00 selects PB3/CLKI;
// synchronous clock domains stop with the source, independent watchdog/NVM
// elapsed-time profiles do not. Initial alignment, exact tie ordering and
// stopped/irregular waveform delivery below are explicit digital policies,
// not a claim of characterized silicon behavior outside electrical limits.
// https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf

test('CLKI held high/low advances physical time without inventing CPU halves',()=>{
  for(const initial of [0,1]) {
    const c=board({initial});assert.equal(c.physical(),1);assert.equal(c.oscillator(),0);
    assert.equal(c.aligned(),initial);assert.equal(c.halted(),1-initial);
    assert.equal(c.hold(1000000000000n),1);
    span(c,2,900000000000n,{result:0,used:0});
    assert.equal(c.now(),900000000000n);assert.equal(c.half(),0n);
    assert.equal(c.level(),initial);assert.equal(c.status(),1);assert.equal(c.halted(),1);
    assert.equal(c.wait_until(1000000000000n),1000000000000n);
    assert.equal(c.half(),0n);assert.equal(c.status(),1);
  }
});

test('first D1 rising edge aligns an initially-low source without charging a half',()=>{
  const c=board({initial:0});enqueue(c,[[100000n,1],[180000n,0],[400000n,1]]);
  assert.equal(c.wait_until(100000n),100000n);
  assert.equal(c.aligned(),1);assert.equal(c.half(),0n);assert.equal(c.halted(),0);
  span(c,2,400000n);assert.equal(c.now(),400000n);assert.equal(c.half(),2n);
});

test('CKDIV8 first system rising edge aligns at half zero without inferred midpoints',()=>{
  const c=board({initial:0,low:0x60});
  const events=waveform(0n,15,{initial:0});enqueue(c,events);
  assert.equal(c.wait_until(events[6][0]),events[6][0]);
  assert.equal(c.aligned(),1);assert.equal(c.half(),0n);assert.equal(c.halted(),0);
  span(c,1,events[14][0]);assert.equal(c.half(),1n);assert.equal(c.level(),1);
  assert.equal(c.halted(),1,'source high does not imply divided system high');
});

test('unknown horizon returns partial work and enqueue backpressure is nonsticky',()=>{
  const c=board();enqueue(c,[[100000n,0]],200000n);
  span(c,2,300000n,{result:0,used:1});assert.equal(c.now(),200000n);
  assert.equal(c.status(),2);assert.equal(c.horizon(),200000n);
  enqueue(c,[[300000n,1]],400000n);assert.equal(c.status(),0);
  span(c,1,300000n);assert.equal(c.now(),300000n);
  const before=c.half(),oldHorizon=c.horizon();
  waveform(oldHorizon,513).forEach(([at,level],i)=>c.set_edge(i,at,level));
  assert.equal(c.enqueue(513,oldHorizon+60000000n),-1);
  assert.equal(c.queued(),0);assert.equal(c.free_edges(),512);
  assert.equal(c.horizon(),oldHorizon);assert.equal(c.half(),before);assert.equal(c.fault(),0);
  enqueue(c,[[oldHorizon+100000n,0],[oldHorizon+200000n,1]]);
  span(c,2,oldHorizon+200000n);assert.equal(c.status(),0);
});

test('full queue backpressure preserves every accepted edge and refill resumes normally',()=>{
  const c=board(),events=waveform(0n,512);enqueue(c,events);
  assert.equal(c.queued(),512);assert.equal(c.free_edges(),0);
  c.set_edge(0,events.at(-1)[0]+100000n,0);
  assert.equal(c.enqueue(1,events.at(-1)[0]+100000n),-1);
  assert.equal(c.queued(),512);assert.equal(c.horizon(),events.at(-1)[0]);assert.equal(c.fault(),0);
  span(c,16,events[15][0]);assert.equal(c.queued(),496);assert.equal(c.free_edges(),16);
  const tail=waveform(events.at(-1)[0],16);enqueue(c,tail);
  span(c,512,tail.at(-1)[0]);assert.equal(c.queued(),0);assert.equal(c.free_edges(),512);
  assert.equal(c.now(),tail.at(-1)[0]);assert.equal(c.half(),528n);
});

test('CLKI preserves exact edge timestamps above 2^53 without a nominal source frequency',()=>{
  const c=board({initial:0}),at=(1n<<53n)+37n;
  enqueue(c,[[at,1],[at+100001n,0],[at+900003n,1]]);
  assert.equal(c.wait_until(at),at);assert.equal(c.half(),0n);
  span(c,1,at+100001n);assert.equal(c.now(),at+100001n);
  span(c,1,at+900003n);assert.equal(c.now(),at+900003n);assert.equal(c.half(),2n);
});

test('CLKPR waits for the real old rising edge and divides subsequent source rises',()=>{
  const c=board();c.write_io(IO.CLKPR,128);c.write_io(IO.CLKPR,3);
  assert.equal(c.divisor(),1);assert.equal(c.hold(1000000000n),1);
  span(c,1,1000000000n,{result:0,used:0});assert.equal(c.divisor(),1);
  const events=waveform(1000000000n,18);enqueue(c,events);
  span(c,2,events[1][0]);assert.equal(c.divisor(),8);
  span(c,1,events[9][0]);assert.equal(c.now(),events[9][0]);assert.equal(c.halted(),1);
  span(c,1,events[17][0]);assert.equal(c.now(),events[17][0]);assert.equal(c.halted(),0);
});

test('unequal CLKI edges appear on physical PB3 at their actual timestamps',()=>{
  const c=board();c.clear_events();
  const events=[[100000n,0],[180000n,1],[300000n,0],[900000n,1],[999999n,0]];
  enqueue(c,events);span(c,5,999999n);
  assert.equal(c.event_count(),events.length);
  for(const [i,[at,level]] of events.entries()) {
    assert.equal(c.event_at(i),at);assert.equal((c.event_levels(i)>>3)&1,level);
  }
});

test('GPIO sampling follows actual falling/rising edges and current-time injections follow sampling',()=>{
  const c=board();assert.equal(c.pins(0n,1,1),1);
  enqueue(c,[[100000n,0],[160000n,1],[500000n,0],[900000n,1]]);
  span(c,1,100000n);assert.equal(c.read_io(IO.PINB)&1,0);
  assert.equal(c.pins(100000n,1,0),1); // After the falling-edge latch closed.
  span(c,1,160000n);assert.equal(c.read_io(IO.PINB)&1,1);
  span(c,2,900000n);assert.equal(c.read_io(IO.PINB)&1,0);
});

test('Timer0 and ADC freeze throughout a hold then resume on delivered system edges',()=>{
  const c=board();assert.equal(c.analog(0n,2,5000000),1);
  c.write_io(IO.TCCR0B,1);c.write_io(IO.ADMUX,1);c.write_io(IO.ADCSRA,0xc0);
  assert.equal(c.hold(1000000000n),1);
  span(c,2,1000000000n,{result:0,used:0});
  assert.equal(c.read_io(IO.TCNT0),0);assert.equal(c.read_io(IO.ADCSRA)&0x50,0x40);
  const events=waveform(1000000000n,240);enqueue(c,events);
  span(c,240,events.at(-1)[0]);assert.equal(c.read_io(IO.TCNT0),120);
  assert.equal(c.read_io(IO.ADCSRA)&0x50,0x10);
  assert.equal(c.read_io(IO.ADCL)|(c.read_io(IO.ADCH)<<8),1023);
});

test('watchdog interrupt and EEPROM programming use wall time while CLKI stays high',()=>{
  const c=board();c.write_io(IO.WDTCR,0x40);
  c.write_io(IO.EEAR,7);c.write_io(IO.EEDR,0x5a);c.write_io(IO.EECR,4);
  assert.equal(c.write_io(IO.EECR,2),2);
  assert.equal(c.hold(16000000000n),1);
  span(c,2,3399999999n,{result:0,used:0});assert.equal(c.eeprom_byte(7),255);
  span(c,2,3400000000n,{result:0,used:0});assert.equal(c.eeprom_byte(7),0x5a);
  span(c,2,15999999999n,{result:0,used:0});assert.equal(c.irq()&256,0);
  span(c,2,16000000000n,{result:0,used:0});assert.equal(c.irq()&256,256);
  assert.equal(c.half(),0n);assert.equal(c.level(),1);
});

test('RESET wins a system-edge tie and preserves the queued source after CPU acknowledgment',()=>{
  const c=board();c.write_io(IO.TCCR0B,1);
  enqueue(c,[[100000n,0],[200000n,1],[300000n,0],[400000n,1]]);
  assert.equal(c.pins(200000n,32,0),1);
  assert.equal(c.span(4n,400000n),-1);assert.equal(c.now(),200000n);
  assert.equal(c.requested(),2);assert.equal(c.held(),1);assert.equal(c.read_io(IO.TCNT0),0);
  assert.equal(c.queued(),2);const half=c.half();
  c.reset(2);assert.equal(c.requested(),0);assert.equal(c.held(),1);assert.equal(c.queued(),2);
  assert.equal(c.pins(300000n,32,32),1);
  assert.equal(c.wait_until(400000n),400000n);assert.equal(c.held(),0);
  assert.ok(c.half()>=half);assert.equal(c.queued(),0);assert.equal(c.fault(),0);
});

test('fuse reset startup counts twenty subsequent source CK and stops with the source',()=>{
  const c=board({initial:0,profile:1});assert.equal(c.starting(),1);assert.equal(c.startup_ck(),20n);
  assert.equal(c.hold(9000000000n),1);assert.equal(c.wait_until(9000000000n),9000000000n);
  assert.equal(c.startup_ck(),20n);assert.equal(c.starting(),1);
  const events=waveform(9000000000n,39,{initial:0});enqueue(c,events);
  assert.equal(c.wait_until(events[36][0]),events[36][0]);assert.equal(c.startup_ck(),1n);
  assert.equal(c.starting(),1);assert.equal(c.wait_until(events[38][0]),events[38][0]);
  assert.equal(c.startup_ck(),0n);assert.equal(c.starting(),0);assert.equal(c.halted(),0);
});

test('SUT watchdog timeout precedes source-CK startup and elapsed CK are not backfilled',()=>{
  const c=board({initial:0,low:0x74,profile:1}); // SUT01:512 WDT ticks at128kHz.
  enqueue(c,[[100000n,1],[200000n,0]],4000000000n);
  assert.equal(c.wait_until(4000000000n),4000000000n);assert.equal(c.startup_ck(),20n);
  const events=waveform(4000000000n,39,{initial:0});enqueue(c,events);
  assert.equal(c.wait_until(events.at(-1)[0]),events.at(-1)[0]);
  assert.equal(c.startup_ck(),0n);assert.equal(c.starting(),0);assert.equal(c.fault(),0);
});

test('RESET release-edge tie arms twenty later startup CK without counting the release edge',()=>{
  const c=board({profile:1}),first=waveform(0n,40);enqueue(c,first);
  const at=first.at(-1)[0];assert.equal(c.wait_until(at),at);assert.equal(c.starting(),0);
  assert.equal(c.pins(at,32,0),1);assert.equal(c.requested(),2);c.reset(2);
  const events=waveform(at,42);enqueue(c,events);assert.equal(c.pins(events[1][0],32,32),1);
  assert.equal(c.wait_until(events[1][0]),events[1][0]);
  assert.equal(c.held(),0);assert.equal(c.startup_ck(),20n);assert.equal(c.starting(),1);
  assert.equal(c.wait_until(events[39][0]),events[39][0]);assert.equal(c.startup_ck(),1n);
  assert.equal(c.wait_until(events[41][0]),events[41][0]);
  assert.equal(c.startup_ck(),0n);assert.equal(c.starting(),0);assert.equal(c.halted(),0);
});

test('WDT reset pulse waits one raw source CK and survives a stopped-high interval',()=>{
  const c=board();c.write_io(IO.WDTCR,8);
  enqueue(c,[[17000000000n,0],[18000000000n,1],[19000000000n,0]],20000000000n);
  assert.equal(c.span(2n,16500000000n),-1);assert.equal(c.now(),16000000000n);
  assert.equal(c.requested(),8);assert.equal(c.held(),1);assert.equal(c.startup_ck(),1n);
  assert.equal(c.queued(),3);c.reset(8);assert.equal(c.held(),1);
  assert.equal(c.wait_until(17500000000n),17500000000n);assert.equal(c.held(),1);
  assert.equal(c.startup_ck(),1n);assert.equal(c.queued(),2);
  assert.equal(c.wait_until(18000000000n),18000000000n);assert.equal(c.held(),0);
  assert.equal(c.startup_ck(),0n);assert.equal(c.queued(),1);assert.equal(c.fault(),0);
});

test('a source rise coincident with WDT assertion cannot discharge its reset pulse',()=>{
  const c=board({initial:0});c.write_io(IO.WDTCR,8);
  enqueue(c,[[16000000000n,1],[17000000000n,0],[18000000000n,1]]);
  assert.equal(c.span(2n,16000000000n),-1);assert.equal(c.requested(),8);
  assert.equal(c.held(),1);assert.equal(c.startup_ck(),1n);assert.equal(c.queued(),2);
  c.reset(8);assert.equal(c.wait_until(17500000000n),17500000000n);
  assert.equal(c.held(),1);assert.equal(c.startup_ck(),1n);
  assert.equal(c.wait_until(18000000000n),18000000000n);
  assert.equal(c.held(),0);assert.equal(c.startup_ck(),0n);assert.equal(c.fault(),0);
});

test('Power-down wake requires six real source CK then four system rising edges',()=>{
  const c=board({wakeHalves:12});
  assert.equal(c.pins(0n,2,2),1);c.write_io(IO.GIMSK,64);c.write_io(IO.MCUCR,0x30);
  c.control(1);assert.equal(c.phase(),1);
  assert.equal(c.pins(100000n,2,0),1);assert.equal(c.hold(100000n),1);
  assert.equal(c.wait_until(100000n),100000n);assert.equal(c.phase(),2);
  const events=waveform(100000n,20);enqueue(c,events);
  assert.equal(c.wait_until(events[10][0]),events[10][0]);assert.equal(c.phase(),2);
  assert.equal(c.wait_until(events[11][0]),events[11][0]);assert.equal(c.phase(),3);
  assert.equal(c.wait_until(events[18][0]),events[18][0]);assert.equal(c.phase(),3);
  assert.equal(c.wait_until(events[19][0]),events[19][0]);assert.equal(c.phase(),0);
  assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});

test('CLKI config and unbounded CPU-clock misuse fail explicitly',()=>{
  for(const low of [0x71,0x72,0x73]) {
    const c=create();assert.equal(c.setup(1,low,0,0),0);assert.equal(c.fault(),1);
  }
  const odd=create();assert.equal(odd.setup(1,0x70,0,1),0);assert.equal(odd.fault(),1);
  const c=board();assert.equal(c.configure_clki(1,0),0);
  c.unbounded(1);assert.equal(c.fault(),13);assert.equal(c.half(),0n);
  assert.equal(c.now(),0n);assert.equal(c.horizon(),0n);
});
