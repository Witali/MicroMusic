import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('watchdog-clock',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset',
].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.c"
static uint8_t data[160],flash[1024],eeprom[64];
int initialize(int physical,unsigned hz,unsigned rate) {
 device_clear_osccal_hz();
 if (!device_configure(DEVICE_CFG_OSCILLATOR_HZ,hz)||!device_configure(DEVICE_CFG_WATCHDOG_HZ,rate))return 0;
 device_configure(DEVICE_CFG_FUSE_LOW,0x72);device_configure(DEVICE_CFG_FUSE_HIGH,0xef);
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
