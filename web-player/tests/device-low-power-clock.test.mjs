// DS40002307A figure6-1 and6.2.3: CKSEL11 selects the watchdog oscillator.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A,runtimeModule,getRuntimeBytes} from '../lib/attiny13a.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {compileAnalog} from './analog-test-build.mjs';
const create=compileAnalog('low-power-clock',[
  'device','timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog',
].map(n=>`web-player/native/peripherals/${n}.c`),`
#include "device.h"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
int init(int physical,int hz,int rate,int low) {
 device_clear_osccal_hz();
 device_configure(DEVICE_CFG_OSCILLATOR_HZ,hz);device_configure(DEVICE_CFG_WATCHDOG_HZ,rate);
 device_configure(DEVICE_CFG_FUSE_LOW,low);device_configure(DEVICE_CFG_FUSE_HIGH,0xff);
 device_configure(DEVICE_CFG_FUSE_STARTUP_PROFILE,0);
 if(physical)device_configure_osccal_hz(0,(low&3)==1||(low&3)==2?hz:9600000);
 memset(data,0xa6,sizeof data);memset(flash,0x5b,sizeof flash);memset(eeprom,0xc3,sizeof eeprom);
 return device_init(data,flash,eeprom);
}
int untouched(void) {
 for(unsigned i=0;i<sizeof data;i++)if(data[i]!=0xa6)return 0;
 for(unsigned i=0;i<sizeof flash;i++)if(flash[i]!=0x5b)return 0;
 for(unsigned i=0;i<sizeof eeprom;i++)if(eeprom[i]!=0xc3)return 0;
 return 1;
}
int fault(void){return device_fault();} int detail(void){return device_fault_detail();}
int read_io(int io){return device_read(io);} void write_io(int io,int value){device_write(io,value,255);}
void cycles(int n){device_advance(n);} void halves(int n){device_advance_half(n);}
uint64_t now(void){return device_time_ps();} int hz(void){return device_oscillator_hz();}
`);

test('physical CKSEL11 rejects contradictory frequencies before touching caller memories',()=>{
  for(const low of [0x73,0x63,0x77])for(const [main,wdt]of [[96000,128000],[128000,96000],[1000000,128000]]){
    const c=create();assert.equal(c.init(1,main,wdt,low),0);
    assert.equal(c.fault(),1);assert.equal(c.detail(),18);assert.equal(c.untouched(),1);
    assert.equal(c.init(1,wdt,wdt,low),1);assert.equal(c.fault(),0);
  }
});

test('valid shared oscillator rates and separate calibrated/external sources remain supported',()=>{
  for(const hz of [64000,128000,173111])for(const low of [0x73,0x63]){
    const c=create();assert.equal(c.init(1,hz,hz,low),1);assert.equal(c.hz(),hz);
  }
  for(const source of [0,1,2]){
    const c=create();assert.equal(c.init(1,1000000,128000,0x70|source),1);
  }
  const legacy=create();assert.equal(legacy.init(0,1000000,128000,0x73),1);
});

const loop=Uint8Array.of(0xff,0xcf),curve=Array(128).fill(9600000);
test('public runtime rejects mismatched shared clocks before runtime instantiation',()=>{
  for(const low of [0x73,0x63])assert.throws(()=>new ATtiny13A(loop,null,{fuseLow:low,
    osccalHz:curve,oscillatorHz:96000,watchdogHz:128000,runtimeModule:{}}),/CKSEL11.*watchdogHz/);
});

test('distributed native runtime also rejects mismatched shared clocks',()=>{
  const e=new WebAssembly.Instance(runtimeModule).exports;
  assert.equal(e.avr_device_configure(1,96000),1);assert.equal(e.avr_device_configure(2,128000),1);
  assert.equal(e.avr_device_configure(5,0x73),1);assert.equal(e.avr_device_configure_osccal_hz(0,9600000),1);
  e.avr_reset(0,0);assert.equal(e.avr_device_fault(),1);assert.equal(e.avr_device_fault_detail(),18);
});

test('CKDIV8 divides CPU/Timer0 while WDT still counts the shared undivided oscillator',()=>{
  const c=create();assert.equal(c.init(1,128000,128000,0x63),1);
  c.write_io(IO.WDTCR,MASK.WDTIE);c.write_io(IO.TCCR0B,1);c.cycles(255);
  assert.equal(c.now(),15937500000n);assert.equal(c.read_io(IO.TCNT0),255);
  assert.equal(c.read_io(IO.WDTCR)&MASK.WDTIF,0);c.halves(1);
  assert.equal(c.now(),15968750000n);assert.equal(c.read_io(IO.WDTCR)&MASK.WDTIF,0);c.halves(1);
  assert.equal(c.now(),16000000000n);assert.equal(c.read_io(IO.WDTCR)&MASK.WDTIF,MASK.WDTIF);
  assert.equal(c.read_io(IO.TCNT0),0);assert.equal(c.fault(),0);
});

test('resumable CPU and package reload preserve shared-source timing through OSCCAL writes',async()=>{
  const binary=new Uint8Array(1024); // NOPs expose one retirement per CPU cycle.
  const configuration={resumable:true,fuseLow:0x63,oscillatorHz:128000,watchdogHz:128000,osccalHz:curve};
  const c=new ATtiny13A(binary,null,configuration);
  const pkg=await createPackage({flash:binary,runtime:getRuntimeBytes(),configuration,
    translated:c.transpiledBytes,manifest:c.transpilation});
  const restored=await ATtiny13A.fromPackage(pkg);
  for(const core of [c,restored]){
    core.writeIO(IO.WDTCR,MASK.WDTIE);core.writeIO(IO.TCCR0B,1);core.writeIO(IO.OSCCAL,1);
    assert.equal(core.state().oscillatorHz,128000);
    assert.equal(core.runUntilPs(15999999999n),255);assert.equal(core.readIO(IO.WDTCR)&MASK.WDTIF,0);
    assert.equal(core.runUntilPs(16000000000n),1);assert.equal(core.pc,256);assert.equal(core.cyc,256);
    assert.equal(core.readIO(IO.WDTCR)&MASK.WDTIF,MASK.WDTIF);assert.equal(core.readIO(IO.TCNT0),0);
    assert.equal(core.state().cpuPhase.retired,256n);assert.equal(core.state().deviceFault,0);
  }
  assert.deepEqual(c.data,restored.data);assert.deepEqual(c.state(),restored.state());
});
