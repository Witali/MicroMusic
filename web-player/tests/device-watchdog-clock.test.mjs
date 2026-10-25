import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
const create=compileAnalog('watchdog-clock',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset',
].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.c"
static uint8_t data[160],flash[1024],eeprom[64];
int initialize(int physical,unsigned hz,unsigned rate,int always_on) {
 device_clear_osccal_hz();
 if (!device_configure(DEVICE_CFG_OSCILLATOR_HZ,hz)||!device_configure(DEVICE_CFG_WATCHDOG_HZ,rate))return 0;
 device_configure(DEVICE_CFG_FUSE_LOW,always_on?0x52:0x72);device_configure(DEVICE_CFG_FUSE_HIGH,0xef);
 device_configure(DEVICE_CFG_FUSE_STARTUP_PROFILE,0);device_configure(DEVICE_CFG_FACTORY_OSCCAL96,0);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,1);device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,hz);
 if(physical&&!device_configure_osccal_hz(0,hz))return 0;
 if(!device_init(data,flash,eeprom))return 0;
 /* Isolate elapsed-clock arithmetic and one deadline consumer at a time. */
 board.clki_enabled=1;board.gpio.io_running=0;
 analog_comparator_config_t config={0};analog_reset(&board.analog,5000000,1100000,27,&config,0);
 return 1;
}
uint64_t interval(uint64_t delta) { board.base=0;board.ns=0;elapse(delta);return board.wdt_ticks; }
void clear_counts(void) { board.ns=board.wdt_ticks=0;board.fault=board.detail=0; }
void seed_ticks(uint64_t n) { board.wdt_ticks=n; }
uint64_t timeout(unsigned left) {
 board.watchdog=(system_watchdog_t){.control=SYSTEM_WDTIE,.counter=2048-left,.oscillator_tick=board.wdt_ticks};
 board.clki_enabled=0;uint64_t result=next_event_scan();board.clki_enabled=1;return result;
}
uint64_t startup(int source,unsigned sut,int power,int external) {
 board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE]=1;
 board.config[DEVICE_CFG_FUSE_LOW]=((uint8_t)board.config[DEVICE_CFG_FUSE_LOW]&~15u)|(sut<<2)|(external?0:2);
 board.power_enabled=power;board.clki_enabled=external;reset_startup(source);board.clki_enabled=1;
 return external?board.clki_reset_wait_until:board.reset_until;
}
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
void step(uint64_t delta) { elapse(board.base+delta);service_async(); }
uint64_t observed_ticks(void) { device_read(SYSTEM_WDTCR);return board.wdt_ticks; }
uint64_t observed_fraction(void) { device_read(SYSTEM_WDTCR);return board.wdt_remainder; }
uint64_t module_tick(void) { return board.watchdog.oscillator_tick; }
uint32_t count(void) { return board.watchdog.counter; }
uint8_t control(void) { return board.watchdog.control; }
void write_wdt(int value,int mask) { device_write(SYSTEM_WDTCR,value,mask); }
void wdr(void) { device_control(DEVICE_CONTROL_WDR,0,0); }
void cpu_cycle_at(uint64_t cycle) { board.half=cycle*2;service_async(); }
void reset_source(int source) {
 board.clki_enabled=0;device_reset(source);board.clki_enabled=1;board.gpio.io_running=0;
}
`);
const U64=(1n<<64n)-1n,PS=1000000000000n,u=n=>BigInt.asUintN(64,n),ceil=(n,d)=>(n+d-1n)/d;
const cases=[[1,9600000,1],[1,9600000,128000],[1,9000001,128001],[1,9600000,1000000000],
  [0,9600000,128000],[0,9000001,128000],[0,500000000,1000000000],[0,1,128000],[0,1000000000,1]];
const base=(p,hz)=>p?PS:2n*BigInt(hz);
test('watchdog elapsed ticks match BigInt at period/fallback and uint64 boundaries',()=>{
  const c=create();
  for(const [physical,hz,rate]of cases){
    const B=base(physical,hz),R=BigInt(rate),q=B/R;
    for(const phase of new Set([0n,1n,q,q?q-1n:0n,q+1n]))for(const delta of new Set([0n,1n,q,q?q-1n:0n,q+1n,0xffffffffn,U64-1n,U64])){
      assert.equal(c.initialize(physical,hz,rate),1);c.interval(phase);c.clear_counts();
      const expected=(delta*R+(phase*R)%B)/B,ns=(delta*1000000000n+(phase*1000000000n)%B)/B;
      assert.equal(u(c.interval(delta)),expected>U64?U64:expected);
      assert.equal(c.fault(),expected>U64||ns>U64?2:0);
      if(c.fault())assert.equal(c.detail(),11);
    }
  }
  assert.equal(c.initialize(1,9600000,128000),1);c.seed_ticks(U64);
  assert.equal(u(c.interval(7812500n)),U64);assert.equal(c.fault(),2);assert.equal(c.detail(),1);
});
test('free-running watchdog fractions accumulate while disabled for divisible and arbitrary rates',()=>{
  const c=create();let seed=0x7563819n;
  for(const [physical,hz,rate]of cases){
    assert.equal(c.initialize(physical,hz,rate),1);let elapsed=0n;const B=base(physical,hz);
    for(let n=0;n<500;n++){
      seed=(seed*6364136223846793005n+1442695040888963407n)&U64;const delta=seed>>32n;elapsed+=delta;
      assert.equal(u(c.interval(delta)),elapsed*BigInt(rate)/B);assert.equal(c.fault(),0);
    }
  }
});
test('watchdog timeout scanner preserves fractional endpoints in both time contracts',()=>{
  const c=create();
  for(const [physical,hz,rate]of cases){
    const B=base(physical,hz),R=BigInt(rate),q=B/R;
    for(const phase of new Set([0n,1n,q,q?q-1n:0n,q+1n]))for(const left of [1,2,2048]){
      assert.equal(c.initialize(physical,hz,rate),1);c.interval(phase);
      const expected=phase+ceil(BigInt(left)*B-(phase*R)%B,R);
      assert.equal(u(c.timeout(left)),expected);assert.equal(c.fault(),0);
    }
  }
});
test('internal reset pulse and external CLKI startup keep watchdog numerator phase',()=>{
  const c=create();
  for(const [physical,hz,rate]of cases){
    const B=base(physical,hz),R=BigInt(rate),q=B/R,H=BigInt(hz);
    for(const phase of new Set([0n,1n,q?q-1n:0n,q+1n]))for(const sut of [1,2])for(const source of [2,8])for(const power of [0,1]){
      assert.equal(c.initialize(physical,hz,rate),1);c.interval(phase);
      const pulse=source===8&&!power?ceil(B,H):0n,ticks=sut===1?512n:8192n;
      const carry=((phase+pulse)*R)%B;
      assert.equal(u(c.startup(source,sut,power,0)),phase+pulse+ceil(ticks*B-carry,R)+ceil(20n*B,H));assert.equal(c.fault(),0);
      if(physical){
        assert.equal(c.initialize(physical,hz,rate),1);c.interval(phase);
        assert.equal(u(c.startup(source,sut,power,1)),phase+ceil(ticks*B-(phase*R)%B,R));assert.equal(c.fault(),0);
      }
    }
  }
});
test('disabled watchdog preserves clock and phase across 500 service intervals',()=>{
  const c=create();
  for(const [physical,hz,rate]of cases.filter(([p,h,r])=>BigInt(r)<=base(p,h))){
    assert.equal(c.initialize(physical,hz,rate),1);let elapsed=0n;
    for(let n=0;n<500;n++){const delta=BigInt(n*131+17);c.step(delta);elapsed+=delta;}
    assert.equal(c.count(),0);
    assert.equal(u(c.observed_ticks()),elapsed*BigInt(rate)/base(physical,hz));
    assert.equal(u(c.observed_fraction()),elapsed*BigInt(rate)%base(physical,hz));
    assert.equal(u(c.module_tick()),u(c.observed_ticks()));assert.equal(c.fault(),0);
  }
});
test('enabling watchdog discards disabled history and keeps the first timeout edge',()=>{
  const c=create();
  for(const [physical,hz,rate]of cases.filter(([p,h,r])=>BigInt(r)<=base(p,h))){
    assert.equal(c.initialize(physical,hz,rate),1);let elapsed=0n;
    const B=base(physical,hz),R=BigInt(rate);
    for(let round=0;round<2;round++){
      for(const d of [901n,7777n,19n]){c.step(d);elapsed+=d;}
      c.write_wdt(MASK.WDTIE,255);
      assert.equal(c.count(),0);assert.equal(c.control()&MASK.WDTIF,0);
      const timeout=ceil(2048n*B-elapsed*R%B,R);
      c.step(timeout-1n);assert.equal(c.count(),2047);assert.equal(c.control()&MASK.WDTIF,0);
      c.step(1n);elapsed+=timeout;assert.equal(c.count(),0);assert.equal(c.control()&MASK.WDTIF,MASK.WDTIF);
      assert.equal(u(c.observed_ticks()),elapsed*R/B);
      c.write_wdt(MASK.WDTIF,255);assert.equal(c.control()&(MASK.WDTIE|MASK.WDTIF),0);
      assert.equal(c.fault(),0);
    }
  }
});
test('WDR preserves off-state oscillator phase and clears only the active counter',()=>{
  const c=create(),B=PS,R=128001n;assert.equal(c.initialize(1,9600000,Number(R)),1);
  let elapsed=123456789n;c.step(elapsed);c.wdr();
  assert.equal(u(c.module_tick()),elapsed*R/B);assert.equal(u(c.observed_fraction()),elapsed*R%B);
  c.write_wdt(MASK.WDTIE,255);c.step(987654321n);elapsed+=987654321n;assert.ok(c.count()>0);
  c.wdr();assert.equal(c.count(),0);assert.equal(u(c.observed_fraction()),elapsed*R%B);
  const timeout=ceil(2048n*B-elapsed*R%B,R);c.step(timeout-1n);assert.equal(c.count(),2047);
  c.step(1n);assert.equal(c.control()&MASK.WDTIF,MASK.WDTIF);assert.equal(c.fault(),0);
});
test('WDCE expires on delivered CPU cycles while the watchdog counter is disabled',()=>{
  const c=create();assert.equal(c.initialize(1,9600000,128000),1);
  c.write_wdt(MASK.WDCE|MASK.WDE,255);c.write_wdt(MASK.WDCE,255);
  assert.equal(c.control()&(MASK.WDCE|MASK.WDE),MASK.WDCE);
  c.step(123456n);c.cpu_cycle_at(3n);assert.equal(c.control()&MASK.WDCE,MASK.WDCE);
  c.cpu_cycle_at(4n);assert.equal(c.control()&MASK.WDCE,0);
  c.write_wdt(MASK.WDTIE,255);assert.equal(c.count(),0);assert.equal(c.fault(),0);
});
test('reset preserves off-state oscillator phase and WDRF or WDTON forces enable',()=>{
  const c=create(),elapsed=123456789n;
  for(const source of [MASK.EXTRF,MASK.WDRF]){
    assert.equal(c.initialize(1,9600000,128001),1);c.step(elapsed);
    c.reset_source(source);assert.equal(c.count(),0);
    assert.equal(u(c.observed_ticks()),elapsed*128001n/PS);assert.equal(u(c.observed_fraction()),elapsed*128001n%PS);
    if(source===MASK.WDRF){assert.equal(c.control()&MASK.WDE,MASK.WDE);c.step(1000000n);}
    assert.equal(c.fault(),0);
  }
  assert.equal(c.initialize(1,9600000,128001,1),1);assert.equal(c.control()&MASK.WDE,MASK.WDE);
  c.step(elapsed);assert.ok(c.count()>0);assert.equal(c.fault(),0);
});
test('rates exceeding the base frequency diagnose overflow before a bus observation',()=>{
  const c=create();assert.equal(c.initialize(0,1,128000),1);c.step(1n);
  assert.equal(u(c.observed_ticks()),64000n);assert.equal(c.fault(),0);
  assert.equal(c.initialize(0,1,128000),1);c.step(U64);assert.equal(c.fault(),2);assert.equal(c.detail(),11);
});
