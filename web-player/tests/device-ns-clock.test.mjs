import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('ns-clock',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset',
].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.c"
void initialize(int physical,unsigned hz,uint64_t ns) {
 board=(device_t){0};board.physical=physical;board.config[1]=hz;board.oscillator_hz=hz;board.divisor=1;
 board.clki_enabled=1;board.ns=ns;
 analog_comparator_config_t config={0};analog_reset(&board.analog,5000000,1100000,27,&config,0);
}
/* Isolate real elapse arithmetic: no source-edge processing or service.
 * Reset only its base before each independent interval, retaining ns carry. */
uint64_t interval(uint64_t delta) { board.base=0;elapse(delta);return board.ns; }
uint64_t nvm_deadline(uint64_t ns,int flash) {
 board.nvm.eeprom_busy=!flash;board.nvm.flash_busy=flash;
 board.nvm.eeprom_until_ns=board.nvm.flash_until_ns=ns;
 board.clki_enabled=0;uint64_t at=next_event_scan();board.clki_enabled=1;return at;
}
int fault(void) { return device_fault(); }
int detail(void) { return device_fault_detail(); }
`);
const U64=(1n<<64n)-1n,u=n=>BigInt.asUintN(64,n);
test('physical ns conversion preserves every ps residue and full-width interval without multiply overflow',()=>{
  const c=create();
  for(let phase=0n;phase<1000n;phase++)for(const delta of [0n,1n,999n,1000n,1001n,U64-1000n,U64-1n,U64]){
    c.initialize(1,9600000,0n);c.interval(phase);assert.equal(u(c.interval(delta)),(phase+delta)/1000n);
    assert.equal(c.fault(),0);
  }
  c.initialize(1,9000001,0n);let elapsed=0n,seed=0x82345719237n;
  for(let n=0;n<2000;n++){
    seed=(seed*6364136223846793005n+1442695040888963407n)&U64;const delta=seed>>16n;elapsed+=delta;
    assert.equal(u(c.interval(delta)),elapsed/1000n);assert.equal(c.fault(),0);
  }
});
test('legacy ns fractions retain oscillator-based units and original overflow diagnostics',()=>{
  const c=create();
  for(const hz of [1,1234567,9600000,9000001,1000000000]){
    c.initialize(0,hz,0n);let elapsed=0n;
    for(const delta of [0n,1n,3n,999n,1001n,65537n,0xffffffffn]){
      elapsed+=delta;assert.equal(u(c.interval(delta)),elapsed*1000000000n/(2n*BigInt(hz)));assert.equal(c.fault(),0);
    }
  }
  c.initialize(1,9600000,U64);assert.equal(u(c.interval(1001n)),U64);assert.equal(c.fault(),2);assert.equal(c.detail(),1);
});
test('EEPROM and Flash scanner deadlines retain exact ps rounding for all residues and endpoint overflow',()=>{
  const c=create();
  for(const flash of [0,1])for(let phase=0n;phase<1000n;phase++)for(const ns of [0n,1n,2n,3700000n]){
    c.initialize(1,9000001,0n);c.interval(phase);
    assert.equal(u(c.nvm_deadline(ns,flash)),ns?ns*1000n:phase);assert.equal(c.fault(),0);
  }
  c.initialize(1,9600000,0n);const ns=u(c.interval(U64));
  assert.equal(u(c.nvm_deadline(ns+1n,0)),U64);assert.equal(c.fault(),2);assert.equal(c.detail(),1);
});
