import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

const create=compileAnalog('pin-observation',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','power_reset',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.c"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
static device_t image;
static uint64_t consumed;
/* The preceding single-consumer capture algorithm, isolated from the new
 * subscription logic, checks default ring bytes, wrapping and fault prefixes. */
static device_pin_event_t old_pins,old_events[PIN_CAPACITY];
static uint16_t old_head,old_count;
static uint64_t old_dropped;
static int old_fault;
static void old_capture(void){
 device_pin_event_t pins={{board.base},board.gpio.pins.levels,board.gpio.pins.driven,
  board.gpio.pins.pullups,board.gpio.pins.floating,board.gpio.pins.contention,{0}};
 if(same_pins(&pins,&old_pins))return;
 old_pins=pins;
 if(old_count){unsigned last=(old_head+old_count-1)%PIN_CAPACITY;
  if(old_events[last].base_half==board.base){old_events[last]=pins;return;}}
 if(old_count==PIN_CAPACITY){if(old_dropped!=UINT64_MAX)old_dropped++;old_fault=1;return;}
 old_events[(old_head+old_count++)%PIN_CAPACITY]=pins;
}
int initialize(int mode){
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 device_configure(DEVICE_CFG_OSCILLATOR_HZ,1000000);
 device_configure(DEVICE_CFG_FUSE_LOW,mode==2?0xf0:0xf2);
 device_configure(DEVICE_CFG_FUSE_HIGH,0xef);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS);
 device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,1000000);
 if(mode==1)device_configure_osccal_hz(0,1000000);
 if(mode==2){device_configure_clki(1,1);device_configure_clki(0,1);}
 int ok=device_init(data,flash,eeprom);
 old_pins=(device_pin_event_t){0};memset(old_events,0,sizeof old_events);
 old_head=old_count=0;old_dropped=0;old_fault=0;old_capture();return ok;
}
int observe(uint32_t mask,uint32_t retain){return device_configure_pin_trace(mask,retain);}
unsigned trace_configuration(void){return device_pin_trace_configuration();}
int audio(int mask){return device_configure_audio_pins((uint8_t)mask);}
void force(uint64_t at,int levels,int driven,int pullups,int floating,int contention){
 board.base=at;board.gpio.pins.levels=levels;board.gpio.pins.driven=driven;
 board.gpio.pins.pullups=pullups;board.gpio.pins.floating=floating;board.gpio.pins.contention=contention;
 capture_pins();old_capture();
}
int prefix_equal(void){
 return board.pin_head==old_head&&board.pin_count==old_count&&board.dropped==old_dropped&&
  !!board.fault==!!old_fault&&!memcmp(&board.pins,&old_pins,sizeof old_pins)&&
  !memcmp(board.pin_events,old_events,sizeof old_events);
}
int host_count(void){return board.pin_count;}
int audio_count(void){return board.audio_pin_count;}
unsigned host_ptr(void){uint32_t count;return (unsigned)(uintptr_t)pin_events(&count);}
unsigned host_contiguous(void){uint32_t count;pin_events(&count);return count;}
unsigned audio_ptr(void){uint32_t count;return (unsigned)(uintptr_t)device_audio_pin_events(&count);}
unsigned audio_contiguous(void){uint32_t count;device_audio_pin_events(&count);return count;}
void consume_host(unsigned count){
 device_consume_pin_events(count);if(count>old_count)count=old_count;
 old_head=(old_head+count)%PIN_CAPACITY;old_count-=count;
}
void consume_audio(unsigned count){device_consume_audio_pin_events(count);}
void clear_host(void){device_clear_pin_events();old_head=old_count=0;old_dropped=0;}
void discard(uint64_t at){device_discard_audio_trace(at);}
unsigned live_ptr(void){return (unsigned)(uintptr_t)&board.pins;}
unsigned write(int address,int value){return device_write(address,value,255);}
int read(int address){return device_read(address);}
int pins(uint64_t at,int mask,int levels){return device_inject_digital_ps(at,mask,levels);}
void cycles(unsigned count){device_advance(count);}
void reset_cpu(void){device_reset(SYSTEM_EXTRF);}
int fault(void){return device_fault();}
int detail(void){return device_fault_detail();}
uint64_t dropped(void){return device_dropped_pin_events();}
uint64_t audio_dropped(void){return board.audio_dropped;}
int ready(unsigned limit){return pin_buffer_ready(limit);}
int periodic(unsigned edges,uint64_t end){
 return device_clki_periodic_ps(board.base,device_clki_level(),500000,500000,edges,end);
}
int span(uint64_t halves,uint64_t wall,int buffered){
 return buffered?device_advance_half_until_ps_buffered(halves,wall,&consumed):
  device_advance_half_until_ps(halves,wall,&consumed);
}
uint64_t used(void){return consumed;}
uint64_t now(void){return board.base;}
uint64_t half(void){return board.half;}
unsigned architecture(void){
 memcpy(&image,&board,sizeof image);
 image.pin_trace_mask=image.pin_trace_retain=image.audio_pin_mask=0;
 image.pin_head=image.pin_count=image.audio_pin_head=image.audio_pin_count=0;
 image.dropped=image.audio_dropped=0;
 memset(image.pin_events,0,sizeof image.pin_events);memset(image.audio_pin_events,0,sizeof image.audio_pin_events);
 return (unsigned)(uintptr_t)&image;
}
unsigned architecture_size(void){return sizeof image;}
unsigned data_ptr(void){return (unsigned)(uintptr_t)data;}
`);

function make(mode=0){const c=create();assert.equal(c.initialize(mode),1);assert.equal(c.fault(),0);return c;}
function record(c,pointer){const v=new DataView(c.memory.buffer,pointer,16);return {
  at:v.getBigUint64(0,true),levels:v.getUint8(8),driven:v.getUint8(9),pullups:v.getUint8(10),
  floating:v.getUint8(11),contention:v.getUint8(12),reserved:[v.getUint8(13),v.getUint8(14),v.getUint8(15)],
};}
function drain(c,audio=false){const prefix=audio?'audio':'host',result=[];
  while(c[prefix+'_count']()){
    const count=c[prefix+'_contiguous'](),pointer=c[prefix+'_ptr']();
    for(let n=0;n<count;n++)result.push(record(c,pointer+16*n));
    c[audio?'consume_audio':'consume_host'](count);
  }
  return result;
}
function force(c,at,levels,metadata=[0,0,0,0]){c.force(BigInt(at),levels,...metadata);}
function architecture(c){return new Uint8Array(c.memory.buffer,c.architecture(),c.architecture_size()).slice();}

test('cold init restores full trace; invalid observer/audio requests preserve configuration and queues',()=>{
  const c=make();assert.equal(c.trace_configuration(),63);const initial=drain(c);assert.equal(initial.length,1);
  assert.equal(c.observe(2,1),1);assert.equal(c.trace_configuration(),258);assert.equal(c.audio(3),1);
  force(c,1,2);const host=c.host_count(),audio=c.audio_count(),live=record(c,c.live_ptr());
  for(const [mask,retain] of [[64,0],[0,2],[0xffffffff,1],[63,0xffffffff]]){
    assert.equal(c.observe(mask,retain),0);assert.equal(c.trace_configuration(),258);
    assert.equal(c.host_count(),host);assert.equal(c.audio_count(),audio);
  }
  for(const mask of [1,4,63])assert.equal(c.audio(mask),0);
  assert.equal(c.audio_count(),audio);assert.deepEqual(record(c,c.live_ptr()),live);
  assert.equal(c.initialize(0),1);assert.equal(c.trace_configuration(),63);assert.equal(c.audio_count(),0);
});

test('default history exactly preserves the former same-timestamp, wrapped and overflowing prefix',()=>{
  const c=make();assert.equal(c.prefix_equal(),1);
  for(let n=1;n<2300;n++){
    const time=BigInt(Math.floor(n/3));
    force(c,time,n&63,[(n>>1)&63,(n>>2)&63,(n>>3)&63,(n>>4)&63]);
    assert.equal(c.prefix_equal(),1,'record '+n);
    if(n===1700)c.consume_host(400);
  }
  for(let n=2300;n<5000;n++){
    force(c,BigInt(n),n&63);assert.equal(c.prefix_equal(),1,'fault prefix '+n);
  }
  assert.equal(c.fault(),9);assert.equal(c.detail(),1024);assert.ok(c.dropped()>0n);
});

test('host mask filters all pin metadata while current pins always retain full live state',()=>{
  const c=make();force(c,0,0);c.clear_host();assert.equal(c.observe(1,1),1);
  force(c,1,8,[0,0,0,0]);assert.equal(c.host_count(),0);
  assert.equal(record(c,c.live_ptr()).levels,8);
  force(c,2,8,[1,0,0,0]);assert.equal(c.host_count(),1,'selected DDR metadata changes');
  force(c,3,8,[1,1,0,0]);force(c,4,8,[1,1,1,0]);force(c,5,8,[1,1,1,1]);
  assert.deepEqual(drain(c).map(e=>e.at),[2n,3n,4n,5n]);
  force(c,6,9,[1,1,1,1]);assert.equal(c.host_count(),1,'selected level changes');
  force(c,7,1,[1,1,1,1]);assert.equal(c.host_count(),1,'later unselected change creates no row');
  assert.equal(record(c,c.host_ptr()).levels,9,'later unselected change must not rewrite old row');
  assert.equal(record(c,c.live_ptr()).levels,1);
});

test('subscriptions preserve queued history, create no fake baseline, and coalesce only matching timestamps',()=>{
  const c=make();c.clear_host();c.observe(1,1);force(c,10,1);
  c.observe(0,1);force(c,10,9);
  assert.equal(c.host_count(),1);assert.equal(record(c,c.host_ptr()).levels,9,'same-time final snapshot');
  force(c,11,1);assert.equal(record(c,c.host_ptr()).levels,9,'older row is immutable');
  c.observe(8,1);assert.equal(c.host_count(),1,'new subscription does not invent a transition');
  force(c,12,9);assert.deepEqual(drain(c).map(e=>[e.at,e.levels]),[[10n,9],[12n,9]]);
});

test('private PCM contains only subscribed level changes; host drain/clear cannot steal them',()=>{
  const c=make();c.clear_host();c.observe(0,0);assert.equal(c.audio(2),1);
  assert.equal(c.audio_count(),0,'audio baseline is sampled live, never queued synthetically');
  force(c,1,1);force(c,2,1,[2,0,0,0]);assert.equal(c.audio_count(),0);
  force(c,3,3,[2,0,0,0]);force(c,3,11,[2,0,0,0]);assert.equal(c.audio_count(),1);
  assert.equal(record(c,c.audio_ptr()).levels,11);
  c.clear_host();assert.deepEqual(drain(c),[]);assert.equal(c.audio_count(),1);
  force(c,4,9,[2,0,0,0]);const events=drain(c,true);
  assert.deepEqual(events.map(e=>[e.at,e.levels&2]),[[3n,2],[4n,0]]);
  assert.equal(c.fault(),0);
});

test('new audio timeline clears only PCM backlog; MCU reset preserves streams and subscriptions',()=>{
  const c=make();c.observe(3,1);c.audio(3);c.write(IO.DDRB,3);c.write(IO.PORTB,3);c.cycles(1);
  const host=drain(c);assert.ok(host.length);assert.ok(c.audio_count());
  c.write(IO.PORTB,0);const before=c.host_count();assert.equal(c.audio(2),1);
  assert.equal(c.audio_count(),0);assert.equal(c.host_count(),before);
  c.write(IO.PORTB,2);c.cycles(1);const pending=c.audio_count();assert.ok(pending);
  c.reset_cpu();assert.equal(c.trace_configuration(),259);assert.ok(c.audio_count()>=pending);
  assert.equal(record(c,c.live_ptr()).levels&3,0,'reset remains visible on live pins');
  assert.equal(drain(c,true).at(-1).levels&2,0,'PCM retains the reset edge after its prior history');
});

test('legacy audio discard removes only host rows through its frontier; retained ownership prevents discard',()=>{
  const c=make();c.clear_host();c.audio(3);
  for(let n=1;n<=5;n++)force(c,n,n&3);
  assert.equal(c.audio_count(),5);c.discard(3n);
  assert.deepEqual(drain(c).map(e=>e.at),[4n,5n]);assert.equal(c.audio_count(),5);
  c.observe(63,1);force(c,6,2);c.discard(100n);
  assert.deepEqual(drain(c).map(e=>e.at),[6n]);assert.equal(c.audio_count(),6);
});

test('PCM wrapping and overflow preserve its own chronological prefix and host dropped accounting',()=>{
  const c=make();c.clear_host();c.observe(0,0);c.audio(3);
  for(let n=1;n<=800;n++)force(c,n,n&3);
  c.consume_audio(700);
  for(let n=801;n<=1725;n++)force(c,n,n&3);
  assert.equal(c.audio_count(),1024);assert.equal(c.audio_dropped(),1n);
  assert.equal(c.dropped(),0n);assert.equal(c.fault(),9);assert.equal(c.detail(),1024);
  const events=drain(c,true);assert.equal(events.length,1024);
  assert.equal(events[0].at,701n);assert.equal(events.at(-1).at,1724n);
  assert.equal(record(c,c.live_ptr()).at,1725n);
});

test('buffer pressure uses PCM and legacy host queues, never an explicitly retained host queue',()=>{
  const c=make();c.clear_host();c.observe(63,1);
  for(let n=1;n<=512;n++)force(c,n,(n&1)?8:0);
  assert.equal(c.ready(512),0);c.observe(63,0);assert.equal(c.ready(512),1);
  c.clear_host();c.observe(0,1);c.audio(2);
  for(let n=513;n<=1024;n++)force(c,n,(n&1)?2:0);
  assert.equal(c.ready(512),1);assert.equal(c.ready(0),0);
});

test('retained CLKI history actually faults on capacity rather than yielding into an undrainable loop',()=>{
  const c=make(2);c.clear_host();c.observe(63,1);assert.equal(c.periodic(1100,550000000n),1);
  assert.equal(c.span(1100n,550000000n,1),-1);
  assert.equal(c.fault(),9);assert.equal(c.detail(),1024);assert.equal(c.host_count(),1024);
  assert.equal(c.used(),1025n);assert.equal(c.now(),512500000n);
});

test('legacy CLKI history yields at the same watermark, then native discard permits forward progress',()=>{
  const c=make(2);c.clear_host();assert.equal(c.periodic(1100,550000000n),1);
  assert.equal(c.span(1100n,550000000n,1),2);assert.equal(c.used(),512n);
  assert.equal(c.now(),256000000n);c.discard(c.now());
  assert.equal(c.span(588n,550000000n,1),2);assert.equal(c.used(),512n);
  c.discard(c.now());assert.equal(c.span(76n,550000000n,1),1);assert.equal(c.fault(),0);
});

test('unobserved CLKI still advances all live GPIO/ADC/timer/IRQ phases with independent PCM',()=>{
  const traced=make(2),quiet=make(2);
  for(const c of [traced,quiet]){
    c.audio(3);c.write(IO.DDRB,3);c.write(IO.OCR0A,31);c.write(IO.OCR0B,63);
    c.write(IO.TCCR0A,0xa3);c.write(IO.TCCR0B,1);c.write(IO.ADMUX,3);c.write(IO.ADCSRA,0xe0);
    c.write(IO.PCMSK,MASK.PCINT2|MASK.PCINT3);c.write(IO.GIMSK,MASK.PCIE);c.clear_host();
    assert.equal(c.pins(750001n,MASK.PCINT2,MASK.PCINT2),1);
  }
  quiet.observe(0,0);
  for(let block=0;block<3;block++){
    const end=BigInt((block+1)*120000000);
    for(const c of [traced,quiet]){assert.equal(c.periodic(240,end),1);assert.equal(c.span(240n,end,0),1);}
    assert.deepEqual(architecture(quiet),architecture(traced));
    assert.deepEqual(drain(quiet,true),drain(traced,true));
    assert.ok(drain(traced).length>=240);assert.deepEqual(drain(quiet),[]);
  }
  assert.equal(quiet.half(),720n);assert.equal(quiet.read(IO.ADCSRA)&0x10,0x10);
  assert.equal(quiet.read(IO.GIFR)&MASK.PCIE,MASK.PCIE);assert.equal(quiet.fault(),0);
});
