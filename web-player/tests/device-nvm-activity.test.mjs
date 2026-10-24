import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

// Count board dispatches, including calls later inlined by the native compiler.
// The reference restores the former unconditional dispatch policy in this
// ignored fixture only; it keeps the same real controllers and event ordering.
const device=readFileSync(new URL('../native/peripherals/device.c',import.meta.url),'utf8');
const activeDefinition='static int nvm_active(void) {';
assert.equal(device.split(activeDefinition).length,2);
const before=`
#include "nvm.h"
#include <string.h>
static uint64_t advances,cycle_scans,ns_scans;
static void counted_advance(attiny13a_nvm_t *n,uint64_t cycle,uint64_t ns) {
 advances++;nvm_advance(n,cycle,ns);
}
static uint64_t counted_cycles(const attiny13a_nvm_t *n) {
 cycle_scans++;return nvm_next_event_cycle(n);
}
static uint64_t counted_ns(const attiny13a_nvm_t *n) {
 ns_scans++;return nvm_next_event_ns(n);
}
#define nvm_advance counted_advance
#define nvm_next_event_cycle counted_cycles
#define nvm_next_event_ns counted_ns
`;
const after=`
#undef nvm_advance
#undef nvm_next_event_cycle
#undef nvm_next_event_ns
static uint8_t data[160],flash[1024],eeprom[64];
static uint64_t used;
int initialize(int mode,int supply) {
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 device_configure(DEVICE_CFG_OSCILLATOR_HZ,1000000);
 device_configure(DEVICE_CFG_FUSE_LOW,mode==2?0xf0:0xf2);
 device_configure(DEVICE_CFG_FUSE_HIGH,0xef);
 device_configure(DEVICE_CFG_SPM_COMMAND_CYCLES,2);
 device_configure(DEVICE_CFG_FUSE_STARTUP_PROFILE,0);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS);
 device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,1000000);
 if(mode==1)device_configure_osccal_hz(0,1000000);
 if(mode==2){device_configure_clki(1,1);device_configure_clki(0,1);}
 if(supply){const uint32_t p[]={1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000};
  for(unsigned i=0;i<10;i++)if(!device_configure_power(i,p[i]))return 0;}
 int result=device_init(data,flash,eeprom);advances=cycle_scans=ns_scans=0;return result;
}
void clear_counts(void){advances=cycle_scans=ns_scans=0;}
uint64_t advance_count(void){return advances;}
uint64_t cycle_scan_count(void){return cycle_scans;}
uint64_t ns_scan_count(void){return ns_scans;}
uint64_t scan(void){return next_event_scan();}
uint64_t now(void){return board.base;}
uint64_t half(void){return board.half;}
uint64_t ns(void){return board.ns;}
uint64_t nvm_cycle(void){return board.nvm.cycle;}
uint64_t nvm_ns(void){return board.nvm.now_ns;}
int active(void){return nvm_active();}
int fault(void){return device_fault();}
int detail(void){return device_fault_detail();}
int irq(void){return device_pending_irqs();}
void ack(void){device_ack_irq(4);}
int peek(int io){return data[32+io];}
int read(int io){return device_read(io);}
unsigned write(int io,int value){return device_write(io,value,255);}
int lpm(int z){return device_lpm(z);}
unsigned spm(int z,int word){return device_control(DEVICE_CONTROL_SPM,z,word);}
void reset_cpu(void){device_reset(SYSTEM_EXTRF);}
void sleep_now(int mode){
 device_write(SYSTEM_MCUCR,32|(mode<<3),255);device_control(DEVICE_CONTROL_SLEEP,0,0);
}
int ee(int address){return eeprom[address];}
void seed_ee(int address,int value){eeprom[address]=value;}
int fl(int address){return flash[address];}
uint64_t generation(void){return device_flash_generation();}
unsigned dirty(void){return device_take_dirty_pages();}
int halted(void){return device_halted();}
int hold(uint64_t at){return device_clki_enqueue(NULL,0,at);}
int cycles(unsigned n){
 if(!board.clki_enabled){device_advance(n);return !board.fault;}
 uint64_t halves=(uint64_t)n*2,end=board.base+halves*500000;
 if(!device_clki_periodic_ps(board.base,device_clki_level(),500000,500000,halves,end))return 0;
 return device_advance_half_until_ps(halves,end,&used)==1;
}
int span_wall(uint64_t at){return device_advance_half_until_ps(1000000000,at,&used);}
uint64_t wait_wall(uint64_t at){return device_wait_until_ps(at);}
int vcc(uint64_t at,int uv){return device_inject_vcc_ps(at,uv);}
int reset_at(uint64_t at){return device_inject_digital_ps(at,32,0);}
static uint8_t snapshot_data[sizeof(attiny13a_nvm_t)+160+1024+64+
 sizeof board.pins+sizeof board.pin_events+18*sizeof(uint64_t)];
unsigned snapshot(void){
 attiny13a_nvm_t n=board.nvm;
 /* An idle module may retain older private timestamps. Normalize exactly
  * those bookkeeping fields; all registers, payloads, windows and faults
  * must still match the unconditional reference byte for byte. */
 n.flash=NULL;n.eeprom=NULL;n.cycle=cpu_cycle();n.now_ns=board.ns;
 uint64_t state[]={board.base,board.half,board.ns,board.phase,board.ns_remainder,
  board.wdt_ticks,board.wdt_remainder,board.pin_count,board.pin_head,board.dropped,
  device_pending_irqs(),device_fault(),device_fault_detail(),device_reset_requested(),
  device_reset_held(),board.domains,board.sleep.phase,device_halted()};
 uint8_t *p=snapshot_data;
#define COPY(v) do{memcpy(p,&(v),sizeof(v));p+=sizeof(v);}while(0)
 COPY(n);COPY(data);COPY(flash);COPY(eeprom);COPY(board.pins);COPY(board.pin_events);COPY(state);
#undef COPY
 return (unsigned)(uintptr_t)snapshot_data;
}
unsigned snapshot_size(void){return sizeof snapshot_data;}
`;
const dependencies=[
  ...['timer0','system_gpio','system_watchdog','system_sleep','nvm',
    'analog_adc','analog_comparator','analog','power_reset']
    .map(name=>`web-player/native/peripherals/${name}.c`),
  ...['reset_input','clki_input','clki_clock','clki_validation','clki_periodic']
    .map(name=>`web-player/native/devices/attiny13a/${name}.c`),
];
const optimized=compileAnalog('nvm-activity',dependencies,before+'\n#include "device.c"\n'+after);
const reference=compileAnalog('nvm-activity-reference',dependencies,before+
  device.replace(activeDefinition,activeDefinition+' return 1;')+after);

const names=['compatible','physical','clki'];
function make(mode=0,supply=0){
  const a=optimized(),b=reference();
  assert.equal(a.initialize(mode,supply),1);assert.equal(b.initialize(mode,supply),1);
  const result={a,b,call(name,...args){
    const actual=a[name](...args),expected=b[name](...args);assert.equal(actual,expected,name);
    parity(result,name);return actual;
  }};
  parity(result,'initialization');return result;
}
function parity({a,b},context){
  const aStart=a.snapshot(),bStart=b.snapshot();
  const actual=new Uint8Array(a.memory.buffer,aStart,a.snapshot_size());
  const expected=new Uint8Array(b.memory.buffer,bStart,b.snapshot_size());
  assert.deepEqual(actual,expected,context);
}
function call({call},...args){return call(...args);}
function clean(c){assert.equal(c.a.fault(),0,`fault=${c.a.fault()}/${c.a.detail()}`);}
function put(c,io,value){return call(c,'write',io,value);}

for(const [mode,name] of names.entries()){
  test(`idle NVM removes recurring advance/deadline entries and catches up on observation (${name})`,()=>{
    const c=make(mode);call(c,'cycles',257);call(c,'scan');clean(c);
    assert.equal(c.a.active(),0);assert.equal(c.a.advance_count(),0n);
    assert.equal(c.a.cycle_scan_count(),0n);assert.equal(c.a.ns_scan_count(),0n);
    assert.ok(c.b.advance_count()>0n);assert.ok(c.b.cycle_scan_count()>0n);
    assert.ok(c.a.nvm_cycle()<c.a.half()/2n,'idle bookkeeping was deferred');
    assert.equal(call(c,'read',IO.EECR),0);
    assert.equal(c.a.nvm_cycle(),c.a.half()/2n);assert.equal(c.a.nvm_ns(),c.a.ns());
    assert.equal(put(c,IO.EECR,8),0);call(c,'cycles',11);
    assert.equal(c.a.active(),0);assert.equal(c.a.advance_count(),0n);
    assert.equal(c.a.irq()&16,16,'idle ready IRQ remains a live level');
    call(c,'ack');assert.equal(c.a.irq()&16,16);
    put(c,IO.EECR,0);assert.equal(c.a.irq()&16,0);clean(c);
  });

  test(`four-cycle EEPE/SPM and three-cycle LPM windows expire on exact delivered clocks (${name})`,()=>{
    const c=make(mode);call(c,'cycles',257);put(c,IO.EECR,4);
    call(c,'cycles',3);assert.equal(c.a.peek(IO.EECR)&4,4);
    call(c,'cycles',1);assert.equal(c.a.peek(IO.EECR)&4,0);
    assert.equal(c.a.active(),0);assert.equal(put(c,IO.EECR,2),0);
    for(const command of [1,3,5,17]){
      put(c,IO.SPMCSR,command);call(c,'cycles',3);
      assert.equal(c.a.peek(IO.SPMCSR),command);
      call(c,'cycles',1);assert.equal(c.a.peek(IO.SPMCSR),0);
    }
    put(c,IO.SPMCSR,9);call(c,'cycles',2);
    assert.equal(call(c,'lpm',0),mode===2?0xf0:0xf2);assert.equal(c.a.peek(IO.SPMCSR),0);
    put(c,IO.SPMCSR,9);call(c,'cycles',3);
    assert.equal(c.a.peek(IO.SPMCSR),0);assert.equal(call(c,'lpm',0),255);
    call(c,'clear_counts');call(c,'cycles',31);call(c,'scan');
    assert.equal(c.a.advance_count(),0n);assert.equal(c.a.cycle_scan_count(),0n);
    clean(c);
  });
}

test('a held CLKI source freezes CPU protection windows but not EEPROM completion',()=>{
  const c=make(2);call(c,'cycles',23);put(c,IO.EECR,4);
  const holdAt=c.a.now()+100000000n;assert.equal(call(c,'hold',holdAt),1);
  assert.equal(call(c,'span_wall',holdAt),0);assert.equal(c.a.peek(IO.EECR)&4,4);
  call(c,'cycles',3);assert.equal(c.a.peek(IO.EECR)&4,4);
  call(c,'cycles',1);assert.equal(c.a.peek(IO.EECR)&4,0);
  put(c,IO.EEARL,7);put(c,IO.EEDR,0x5a);put(c,IO.EECR,12);
  assert.equal(put(c,IO.EECR,10),2);
  const begin=c.a.now(),half=c.a.half(),end=begin+3400000000n;
  assert.equal(call(c,'hold',end+1000000n),1);
  call(c,'span_wall',end-1n);assert.equal(c.a.ee(7),255);assert.equal(c.a.irq()&16,0);
  call(c,'span_wall',end);assert.equal(c.a.ee(7),0x5a);assert.equal(c.a.irq()&16,16);
  assert.equal(c.a.half(),half);assert.equal(c.a.active(),0);
  call(c,'clear_counts');call(c,'span_wall',end+1000000n);call(c,'scan');
  assert.equal(c.a.advance_count(),0n);assert.equal(c.a.ns_scan_count(),0n);clean(c);
});

for(const mode of [0,1])for(const programming of [0,1,2])
test(`EEPROM mode ${programming} reactivates after idle and retains read/program stalls (${names[mode]})`,()=>{
  const c=make(mode);call(c,'cycles',997);call(c,'seed_ee',4,programming===1?0:255);
  put(c,IO.EEARL,4);put(c,IO.EEDR,0x36);put(c,IO.EECR,(programming<<4)|12);
  assert.equal(put(c,IO.EECR,(programming<<4)|10),2);
  const cycles=programming===0?3400:1800;
  call(c,'cycles',cycles-1);assert.equal(c.a.peek(IO.EECR)&2,2);assert.equal(c.a.irq()&16,0);
  call(c,'cycles',1);assert.equal(c.a.peek(IO.EECR)&2,0);assert.equal(c.a.irq()&16,16);
  assert.equal(c.a.ee(4),programming===1?255:0x36);
  assert.equal(put(c,IO.EECR,9),4);assert.equal(c.a.peek(IO.EEDR),programming===1?255:0x36);
  assert.equal(c.a.active(),0);clean(c);
});

for(const reset of [false,true])
test(`Flash programming completes while CPU is halted${reset?' across reset':''}`,()=>{
  const c=make(1);call(c,'cycles',501);
  put(c,IO.SPMCSR,1);assert.equal(call(c,'spm',0x100,0x1234),2);
  put(c,IO.SPMCSR,5);assert.equal(call(c,'spm',0x100,0),0);
  const end=c.a.now()+4500000000n;
  assert.equal(c.a.halted(),1);if(reset)call(c,'reset_cpu');
  call(c,'wait_wall',end-1n);assert.equal(c.a.fl(0x100),255);assert.equal(c.a.generation(),0n);
  call(c,'wait_wall',end);assert.equal(c.a.fl(0x100),0x34);assert.equal(c.a.fl(0x101),0x12);
  assert.equal(c.a.generation(),1n);assert.equal(call(c,'dirty'),1<<8);
  assert.equal(c.a.active(),0);assert.equal(c.a.halted(),0);clean(c);
});

for(const mode of [0,1,2])
test(`EEPROM completion remains asynchronous in sleep mode ${mode} with PRR set`,()=>{
  const c=make(1);call(c,'cycles',103);put(c,IO.PRR,3);
  put(c,IO.EEARL,5);put(c,IO.EEDR,0x48);put(c,IO.EECR,4);put(c,IO.EECR,2);
  const end=c.a.now()+3400000000n;call(c,'sleep_now',mode);assert.equal(c.a.halted(),1);
  call(c,'wait_wall',end-1n);assert.equal(c.a.ee(5),255);
  call(c,'wait_wall',end);assert.equal(c.a.ee(5),0x48);assert.equal(c.a.active(),0);
  assert.equal(c.a.halted(),1,'completion without EERIE must not wake the CPU');
  call(c,'clear_counts');call(c,'wait_wall',end+1000000000n);call(c,'scan');
  assert.equal(c.a.advance_count(),0n);assert.equal(c.a.cycle_scan_count(),0n);
  assert.equal(c.a.ns_scan_count(),0n);clean(c);
});

for(const mode of [1,2])for(const offset of [-1n,0n])
test(`EEPROM completion retains exact supply-tie ordering at deadline${offset}ps (${names[mode]})`,()=>{
  const c=make(mode,1);call(c,'cycles',100);put(c,IO.EEARL,3);put(c,IO.EEDR,0x25);
  put(c,IO.EECR,4);put(c,IO.EECR,2);const end=c.a.now()+3400000000n;
  if(mode===2)assert.equal(call(c,'hold',end+1000000n),1);
  assert.equal(call(c,'vcc',end+offset,1800000),1);call(c,'span_wall',end+1000000n);
  // CLKI explicitly preapplies supply/reset inputs before its async service;
  // retain that established tie policy rather than assuming oscillator order.
  if(offset<0n||mode===2){assert.equal(c.a.fault(),5);assert.equal(c.a.detail(),128);assert.equal(c.a.ee(3),255);}
  else {clean(c);assert.equal(c.a.ee(3),0x25);assert.equal(c.a.active(),0);}
});

for(const mode of [1,2])
test(`EEPROM pending payload survives an exact asynchronous RESET assertion (${names[mode]})`,()=>{
  const c=make(mode);call(c,'cycles',100);put(c,IO.EEARL,9);put(c,IO.EEDR,0x67);
  put(c,IO.EECR,4);put(c,IO.EECR,2);const end=c.a.now()+3400000000n;
  if(mode===2)assert.equal(call(c,'hold',end+1000000n),1);
  assert.equal(call(c,'reset_at',end-1n),1);assert.equal(call(c,'span_wall',end+1000000n),-1);
  assert.equal(c.a.ee(9),255);call(c,'reset_cpu');assert.equal(c.a.active(),1);
  call(c,'wait_wall',end);assert.equal(c.a.ee(9),0x67);assert.equal(c.a.active(),0);clean(c);
});
