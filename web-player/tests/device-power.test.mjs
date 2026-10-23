import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('device-power',['device','timer0','system_gpio','system_watchdog','system_sleep','nvm',
 'analog_adc','analog_comparator','analog'].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.h"
static uint8_t data[160],flash[1024],eeprom[64];
int cfg(int key,int value){return device_configure(key,value);}
int power(int field,int value){return device_configure_power(field,value);}
int cal(void){return device_configure_osccal_hz(0,10000000);}
int init(void){for(int i=0;i<1024;i++)flash[i]=255;for(int i=0;i<64;i++)eeprom[i]=255;
 return device_init(data,flash,eeprom);}
void cycles(int n){device_advance(n);}int read(int a){return device_read(a);}
void write(int a,int v){device_write(a,v,255);}
int vcc(uint64_t at,int uv){return device_inject_vcc_ps(at,uv);}
int pins(uint64_t at,int mask,int levels){return device_inject_digital_ps(at,mask,levels);}
int analog(uint64_t at,int pin,int uv){return device_inject_analog_ps(at,pin,uv);}
uint64_t now(void){return device_time_ps();}uint64_t ready(void){return device_startup_deadline_ps();}
uint64_t wait(uint64_t at){return device_wait_until_ps(at);}
int requested(void){return device_reset_requested();}int held(void){return device_reset_held();}
int halted(void){return device_halted();}int starting(void){return device_starting();}
void ack(void){device_reset(device_reset_requested());}void reset(void){device_reset(8);}
void enter(void){device_control(1,0,0);}int disabled(void){return device_bod_disabled();}
int recovering(void){return device_bod_recovering();}int phase(void){return device_sleep_phase();}
int voltage(void){return device_vcc_microvolts();}int enabled(void){return device_power_enabled();}
int fault(void){return device_fault();}int detail(void){return device_fault_detail();}
int ee(int a){return eeprom[a];}int rom(int a){return flash[a];}
void spm(int value){device_control(2,0,value);}uint64_t generation(void){return device_flash_generation();}
`);
const profile=[1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000];
function board({uv=5000000,high=0xfb,startup=0,low=0x72,flashMin=1800000}={}){
 const c=create();
 for(const [key,value] of [[1,10000000],[3,uv],[5,low],[6,high],[13,2],[17,startup],[18,1],[19,10000000]])assert.equal(c.cfg(key,value),1);
 assert.equal(c.cal(),1);for(let field=0;field<profile.length;field++)assert.equal(c.power(field,field===9?flashMin:profile[field]),1);
 assert.equal(c.init(),1);return c;
}
const write=(c,a,v)=>c.write(a,v);
const initialReady=c=>{const t=c.ready();assert.notEqual(t,-1n);c.wait(t);assert.equal(c.halted(),0);return t;};
function startEE(c){write(c,0x1e,4);write(c,0x1d,42);write(c,0x1c,4);write(c,0x1c,2);}
function adc(c){write(c,0x07,1);write(c,0x06,0xc0);c.cycles(100);return c.read(4)|(c.read(5)<<8);}
function sleep(c){
 assert.equal(c.pins(c.now(),2,2),1);write(c,0x3b,0x40);write(c,0x35,0x30);
 write(c,0x30,3);c.cycles(1);write(c,0x30,2);c.cycles(1);c.enter();
 assert.equal(c.disabled(),1);return c.now();
}

test('power profile requires all explicit fields and physical clock, and rejects inconsistent thresholds',()=>{
 const c=create();c.power(0,1);assert.equal(c.init(),0);assert.equal(c.fault(),1);
 const d=create();d.cal();d.cfg(1,10000000);for(let f=0;f<9;f++)d.power(f,profile[f]);assert.equal(d.init(),0);
 const e=create();e.cal();e.cfg(1,10000000);for(let f=0;f<10;f++)e.power(f,profile[f]);e.power(2,1000000);
 assert.equal(e.init(),0);assert.equal(e.fault(),16);
 assert.equal(e.power(10,1),0);assert.equal(e.power(1,0),0);assert.equal(e.power(0,2),0);
});

test('cold supply holds reset and starts one fuse SUT interval only after VCC release',()=>{
 const c=board({uv:0,startup:1,high:0xff});assert.equal(c.held(),1);assert.equal(c.requested(),0);assert.equal(c.read(0x34),1);
 assert.equal(c.ready(),-1n);assert.equal(c.vcc(1000000n,5000000),1);c.wait(1000000n);
 assert.equal(c.held(),0);assert.equal(c.ready(),3000000n);c.wait(2999999n);assert.equal(c.halted(),1);
 c.wait(3000000n);assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});

test('POR interrupts a requested CPU span at exact ps and resets GPIO before CPU acknowledgement',()=>{
 const c=board({high:0xff});write(c,0x17,1);write(c,0x18,1);
 c.vcc(37n,0);c.cycles(4);assert.equal(c.now(),37n);assert.equal(c.requested(),1);assert.equal(c.held(),1);
 assert.equal(c.read(0x17),0);assert.equal(c.read(0x18),0);c.ack();assert.equal(c.held(),1);assert.equal(c.requested(),0);
 c.vcc(1000000n,5000000);c.wait(1000000n);assert.equal(c.halted(),0);assert.equal(c.read(0x34),1);
});

test('BOD qualifies exact physical filter time and preserves hold through its hysteresis band',()=>{
 const c=board();c.vcc(1000000n,2600000);c.cycles(40);
 assert.equal(c.now(),3000000n);assert.equal(c.requested(),4);assert.equal(c.read(0x34),5);c.ack();
 c.vcc(4000000n,2700000);c.vcc(5000000n,5000000);c.wait(4000000n);assert.equal(c.held(),1);
 c.wait(5000000n);assert.equal(c.held(),0);assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});

test('short VCC dip is filtered and current-time VCC injection follows the same reset path',()=>{
 const c=board();c.vcc(1000000n,2600000);c.vcc(2999999n,5000000);c.cycles(40);
 assert.equal(c.requested(),0);assert.equal(c.read(0x34),1);assert.equal(c.voltage(),5000000);
 assert.equal(c.vcc(c.now(),0),1);assert.equal(c.requested(),1);assert.equal(c.held(),1);
});

test('EXTRF and BOD aggregate without another CPU restart; SUT starts on the last source release',()=>{
 const c=board({startup:1}),t=initialReady(c);
 c.vcc(t+1000000n,2600000);c.cycles(40);assert.equal(c.now(),t+3000000n);c.ack();
 c.pins(t+4000000n,32,0);c.vcc(t+5000000n,5000000);c.pins(t+6000000n,32,32);
 c.wait(t+5000000n);assert.equal(c.held(),1);assert.equal(c.requested(),0);assert.equal(c.read(0x34),7);
 c.wait(t+6000000n);assert.equal(c.held(),0);assert.equal(c.ready(),t+8000000n);
 c.wait(t+8000000n);assert.equal(c.halted(),0);assert.equal(c.fault(),0);
});

test('WDT raw reset pulse is one source CK, even with zero SUT, and is not charged twice',()=>{
 const c=board({high:0xff});write(c,0x21,8);c.cycles(200000);
 const at=16000000000n;assert.equal(c.now(),at);assert.equal(c.requested(),8);assert.equal(c.held(),1);c.ack();
 c.wait(at+99999n);assert.equal(c.held(),1);c.wait(at+100000n);
 assert.equal(c.held(),0);assert.equal(c.halted(),0);assert.equal(c.read(0x34),9);assert.equal(c.fault(),0);
});

test('BODS suppresses BOD during Power-down, then low-VCC wake resets before recovery finishes',()=>{
 const c=board(),t=sleep(c);c.vcc(t+1000000n,2000000);c.pins(t+2000000n,2,0);
 c.wait(t+1000000n);assert.equal(c.held(),0);assert.equal(c.disabled(),1);
 c.wait(t+2000000n);assert.equal(c.recovering(),1);assert.equal(c.disabled(),0);
 c.wait(t+4000000n);assert.equal(c.requested(),4);assert.equal(c.held(),1);assert.equal(c.read(0x34),5);
});

test('safe BOD wake recovery overlaps startup and is followed by exactly four CPU cycles',()=>{
 const c=board(),t=sleep(c),wake=t+1000000n;c.pins(wake,2,0);c.wait(wake);
 c.wait(wake+60000000n);assert.equal(c.recovering(),0);assert.equal(c.halted(),1);
 c.wait(wake+60400000n);assert.equal(c.halted(),0);assert.equal(c.read(0x34),1);assert.equal(c.fault(),0);
});

test('VCC inputs change ADC reference while retaining absolute injected pin voltage',()=>{
 const c=board({high:0xff});c.analog(c.now(),2,1000000);assert.equal(adc(c),204);
 c.vcc(c.now(),2500000);assert.equal(c.voltage(),2500000);assert.equal(adc(c),409);assert.equal(c.fault(),0);
 const d=board({high:0xff});write(d,0x17,4);write(d,0x18,4);assert.equal(adc(d),1023);
 d.vcc(d.now(),2500000);assert.equal(adc(d),1023);
});

test('EEPROM start below1.9V faults explicitly and no reset/read can later commit its data',()=>{
 const c=board({uv:1850000,high:0xff});startEE(c);assert.equal(c.fault(),5);assert.equal(c.detail(),128);assert.equal(c.ee(4),255);
 c.reset();c.cycles(100000);c.read(0x1c);assert.equal(c.ee(4),255);assert.equal(c.detail(),128);
});

test('an in-flight EEPROM low-voltage span becomes sticky even before BOD/POR qualification',()=>{
 const c=board({high:0xff});startEE(c);c.vcc(1000000000n,1850000);c.cycles(20000);
 assert.equal(c.fault(),5);assert.equal(c.detail(),128);assert.equal(c.ee(4),255);
 c.reset();c.cycles(100000);c.read(0x1c);assert.equal(c.ee(4),255);
});

test('adequate-voltage EEPROM programming completes during external reset hold',()=>{
 const c=board({high:0xff});startEE(c);c.pins(1000000n,32,0);c.cycles(100);c.ack();
 c.wait(4000000000n);assert.equal(c.held(),1);assert.equal(c.ee(4),42);assert.equal(c.fault(),0);
});

test('Flash uses its separately selected programming-voltage profile and freezes invalidation',()=>{
 const c=board({high:0xef,flashMin:2000000});write(c,0x37,1);c.spm(0x1234);c.cycles(2);
 write(c,0x37,5);c.spm(0);const at=c.now();c.vcc(at+1000000n,1950000);c.wait(at+1000000000n);
 assert.equal(c.fault(),5);assert.equal(c.detail(),256);assert.equal(c.rom(0),255);assert.equal(c.generation(),0n);
 c.reset();c.cycles(100000);c.read(0x37);assert.equal(c.rom(0),255);assert.equal(c.generation(),0n);
});

test('profile-off contract rejects VCC queue API; timestamp order and input bounds are checked',()=>{
 const c=create();c.cfg(1,10000000);c.cal();assert.equal(c.init(),1);assert.equal(c.enabled(),0);
 assert.equal(c.vcc(0n,3000000),0);assert.equal(c.fault(),16);
 const d=board();assert.equal(d.vcc(100n,3000000),1);assert.equal(d.vcc(99n,3000000),0);assert.equal(d.fault(),2);
 const e=board();assert.equal(e.vcc(0n,-1),0);assert.equal(e.fault(),16);
});
