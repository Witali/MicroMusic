import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

const sources=['timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','power_reset'].map(n=>`web-player/native/peripherals/${n}.c`);
const builds=[0,1].map(enabled=>compileAnalog('gpio-idle-'+enabled,sources,`
#include "system_gpio.h"
#include <string.h>
static uint64_t advances,queries;
static uint8_t counted_advance(system_gpio_t *g,uint64_t begin,uint64_t end,system_gpio_t0_event_t *e){
 ++advances;return system_gpio_advance(g,begin,end,e);
}
static uint64_t counted_query(const system_gpio_t *g,uint64_t after){
 ++queries;return system_gpio_next_event_half(g,after);
}
#define system_gpio_advance counted_advance
#define system_gpio_next_event_half counted_query
#define DEVICE_GPIO_IDLE_CACHE ${enabled}
#include "device.c"
#undef system_gpio_advance
#undef system_gpio_next_event_half
static uint8_t data[160],flash[1024],eeprom[64];
static device_t image;
static uint64_t used;
_Static_assert(offsetof(device_t,gpio_settled)==offsetof(device_t,vcc_uv)+sizeof(int32_t),"cache follows VCC");
_Static_assert(offsetof(device_t,gpio_settled)+1<=offsetof(device_t,wdt_reset_end),"cache occupies existing padding");
int initialize(int mode,int supply){
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 device_configure(DEVICE_CFG_OSCILLATOR_HZ,1000000);device_configure(DEVICE_CFG_FUSE_LOW,mode==2?0xf0:0xf2);
 device_configure(DEVICE_CFG_FUSE_HIGH,0xef);device_configure(DEVICE_CFG_SPM_COMMAND_CYCLES,2);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,1);device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,1000000);
 if(mode==1){device_configure_osccal_hz(0,1000000);device_configure_osccal_hz(1,2000000);}
 if(mode==2){device_configure_clki(1,1);device_configure_clki(0,1);}
 if(supply){const uint32_t p[]={1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000};
  for(unsigned i=0;i<10;i++)if(!device_configure_power(i,p[i]))return 0;}
 int result=device_init(data,flash,eeprom);advances=queries=0;return result;
}
void clear_counts(void){advances=queries=0;}
uint64_t advance_count(void){return advances;}
uint64_t query_count(void){return queries;}
int certificate(void){return board.gpio_settled;}
int coherent(void){return !board.gpio_settled||system_gpio_settled(&board.gpio);}
int fault(void){return device_fault();}
int detail(void){return device_fault_detail();}
int backwards(void){service_clocks(board.half+1);return device_fault();}
void exhausted_half(void){board.half=UINT64_MAX;deadline_invalidate(DEADLINE_ELAPSE);}
int write(int io,int value){return device_write(io,value,255);}
int read(int io){return device_read(io);}
int pins(int mask,int value){return board.physical?device_inject_digital_ps(board.base,mask,value):device_inject_digital(board.base,mask,value);}
int queued(uint64_t after,int mask,int value){return board.physical?device_inject_digital_ps(board.base+after,mask,value):device_inject_digital(board.base+after,mask,value);}
int vcc(uint64_t after,int uv){return device_inject_vcc_ps(board.base+after,uv);}
void ack(int vector){device_ack_irq(vector);}
void reset_cpu(void){device_reset(SYSTEM_EXTRF);}
void enter_sleep(int mode){device_write(SYSTEM_MCUCR,32|(mode<<3),255);device_control(DEVICE_CONTROL_SLEEP,0,0);}
uint64_t scan(void){return next_event_scan();}
uint64_t now(void){return board.base;}
uint64_t half(void){return board.half;}
int halves(unsigned n){
 if(!board.clki_enabled){device_advance_half(n);return !board.fault;}
 uint64_t end=board.base+(uint64_t)n*500000;
 if(n&&!device_clki_periodic_ps(board.base,device_clki_level(),500000,500000,n,end))return 0;
 return device_advance_half_until_ps(n,end,&used)==1;
}
void clear_pins(void){device_clear_pin_events();}
uintptr_t canonical(void){image=board;image.gpio_settled=0;return (uintptr_t)&image;}
unsigned size(void){return sizeof board;}
uintptr_t data_view(void){return (uintptr_t)data;}
uintptr_t flash_view(void){return (uintptr_t)flash;}
uintptr_t eeprom_view(void){return (uintptr_t)eeprom;}
`,{fixedMemoryPages:2}));
const make=(mode,supply=0)=>builds.map(create=>{const c=create();assert.equal(c.initialize(mode,supply),1);return c;});
function same(cs){
  for(const c of cs)assert.equal(c.coherent(),1,'a certificate must imply the full GPIO predicate');
  const a=cs.map(c=>({board:new Uint8Array(c.memory.buffer,c.canonical(),c.size()).slice(),
    data:new Uint8Array(c.memory.buffer,c.data_view(),160).slice(),
    flash:new Uint8Array(c.memory.buffer,c.flash_view(),1024).slice(),
    eeprom:new Uint8Array(c.memory.buffer,c.eeprom_view(),64).slice()}));
  assert.deepEqual(a[1],a[0],'all canonical private controllers, queues, timestamps, phases and memories');
}
const call=(cs,name,...args)=>{const values=cs.map(c=>c[name](...args));assert.deepEqual(values[1],values[0],name);same(cs);return values[0];};
const advance=(cs,n)=>{call(cs,'halves',n);call(cs,'clear_pins');};

for(const mode of [0,1])test(`settled internal GPIO suppresses recurring calls and preserves every phase: mode=${mode}`,()=>{
  const cs=make(mode);advance(cs,12);cs.forEach(c=>c.clear_counts());
  for(let n=0;n<64;n++){advance(cs,n%3);call(cs,'scan');}
  assert.equal(cs[1].advance_count(),0n);assert.equal(cs[1].query_count(),0n);
  assert.ok(cs[0].advance_count()>0n);assert.ok(cs[0].query_count()>0n);
  same(cs);
});
for(const mode of [0,1,2])test(`GPIO mutations, Timer0 overrides and T0 preserve full canonical state: mode=${mode}`,()=>{
  const cs=make(mode);advance(cs,12);
  for(const [io,value]of [[IO.DDRB,3],[IO.PORTB,3],[IO.PINB,1],[IO.PCMSK,0x3f],
    [IO.GIMSK,0x60],[IO.MCUCR,1],[IO.DIDR0,0x1f],[IO.DIDR0,0],[IO.GIFR,0x60],
    [IO.OCR0A,7],[IO.OCR0B,3],[IO.TCCR0A,0x42],[IO.TCCR0B,1]]){
    call(cs,'write',io,value);call(cs,'scan');advance(cs,1);advance(cs,0);advance(cs,9);
  }
  call(cs,'write',IO.TCCR0B,7);call(cs,'write',IO.DDRB,0);
  for(let n=0;n<8;n++){call(cs,'pins',4,n&1?4:0);advance(cs,8);call(cs,'ack',2);}
  assert.ok(call(cs,'read',IO.TCNT0)>0);same(cs);
});
for(const mode of [0,1,2])test(`same-time inputs, clock gating and IRQ acknowledgement refresh GPIO: mode=${mode}`,()=>{
  const cs=make(mode);advance(cs,12);call(cs,'write',IO.PCMSK,1);call(cs,'write',IO.GIMSK,MASK.PCIE);
  call(cs,'pins',1,1);call(cs,'scan');advance(cs,8);call(cs,'ack',2);
  call(cs,'enter_sleep',2);call(cs,'scan');call(cs,'pins',1,0);call(cs,'scan');advance(cs,12);
  call(cs,'write',IO.PRR,3);advance(cs,3);call(cs,'write',IO.PRR,0);advance(cs,8);
  call(cs,'reset_cpu');advance(cs,0);advance(cs,1);advance(cs,0);advance(cs,1);
  assert.equal(cs[1].fault(),0);same(cs);
});
test('power reset assertion and preapplied acknowledgement clear settled ownership',()=>{
  const cs=make(1,1);advance(cs,13);call(cs,'vcc',0n,0);call(cs,'reset_cpu');advance(cs,0);
  call(cs,'vcc',0n,5000000);advance(cs,0);advance(cs,1);advance(cs,8);same(cs);
});
test('CLKI keeps its original GPIO path and all source-edge observations',()=>{
  const cs=make(2);cs.forEach(c=>c.clear_counts());
  for(let n=0;n<80;n++)advance(cs,7);
  assert.equal(cs[1].advance_count(),cs[0].advance_count());
  assert.equal(cs[1].query_count(),cs[0].query_count());assert.equal(cs[1].half(),560n);same(cs);
});
for(const mode of [0,1,2])test(`queued input before/at/after a falling edge retains PINB latency: mode=${mode}`,()=>{
  const half=mode===0?1n:500000n,offsets=mode===0?[0n,1n,2n]:[0n,499999n,500000n,500001n];
  for(const offset of offsets){
    const cs=make(mode);advance(cs,12);call(cs,'write',IO.PCMSK,1);
    call(cs,'queued',offset,1,1);call(cs,'scan');advance(cs,1);
    assert.equal(call(cs,'read',IO.PINB)&1,0);
    advance(cs,1);assert.equal(call(cs,'read',IO.PINB)&1,offset<half?1:0);
    advance(cs,2);assert.equal(call(cs,'read',IO.PINB)&1,1);
  }
});
test('a settled certificate cannot hide reversed GPIO time',()=>{
  const cs=make(1);advance(cs,12);assert.equal(call(cs,'backwards'),2);assert.equal(call(cs,'detail'),3);same(cs);
});
test('stable and pending GPIO pipelines retain phase across CLKPR and OSCCAL changes',()=>{
  const cs=make(1);advance(cs,12);
  for(const pending of [false,true]){
    if(pending)call(cs,'pins',1,1);
    for(const [io,value]of [[IO.CLKPR,128],[IO.CLKPR,2],[IO.OSCCAL,1],
      [IO.CLKPR,128],[IO.CLKPR,0],[IO.OSCCAL,0]]){
      call(cs,'write',io,value);call(cs,'scan');advance(cs,1);advance(cs,0);advance(cs,7);
    }
  }
  assert.equal(cs[1].fault(),0);same(cs);
});
test('a gated clock cannot certify an unsettled GPIO pipeline from an infinite deadline',()=>{
  const cs=make(1);advance(cs,12);call(cs,'enter_sleep',1);call(cs,'pins',16,16);
  call(cs,'scan');assert.equal(cs[1].certificate(),0);assert.equal(call(cs,'read',IO.PINB)&16,0);
  advance(cs,8);call(cs,'scan');assert.equal(cs[1].certificate(),0);same(cs);
});
test('the raw GPIO time-limit sentinel does not certify an unsettled pipeline',()=>{
  const cs=make(0);call(cs,'pins',16,16);
  // Seed the private boundary directly: physical ns/time bounds can reject a
  // real advance before the virtual half counter reaches UINT64_MAX.
  call(cs,'exhausted_half');call(cs,'scan');assert.equal(cs[1].certificate(),0);same(cs);
});
test('seeded GPIO register/input changes match original dispatch at odd, even and zero spans',()=>{
  for(const mode of [0,1,2]){
    const cs=make(mode);let seed=0x13a;const random=()=>seed=(Math.imul(seed,1664525)+1013904223)>>>0;
    const regs=[IO.PORTB,IO.DDRB,IO.PINB,IO.PCMSK,IO.DIDR0,IO.MCUCR,IO.GIFR,IO.GIMSK];
    for(let n=0;n<160;n++){
      const r=random();
      if(r&1){const io=regs[(r>>>2)%regs.length];let v=(r>>>8)&63;if(mode===2&&io===IO.DDRB)v&=~8;
        if(io===IO.MCUCR)v&=3;if(io===IO.GIFR||io===IO.GIMSK)v&=0x60;call(cs,'write',io,v);
      }else call(cs,'pins',0x17,(r>>>8)&0x17);
      call(cs,'scan');advance(cs,random()%9);assert.equal(cs[1].fault(),0);
    }
  }
});
