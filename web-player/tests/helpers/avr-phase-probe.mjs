// Instrument native bridges in a test-only WASM build, never execute opcodes
// in the probe. The CPU is the real generated module from ATtiny13A.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../../lib/attiny13a-runtime.js';
import {compileAnalog} from '../analog-test-build.mjs';

const native=fileURLToPath(new URL('../../native/avr.c',import.meta.url)).replaceAll('\\','/');
const hasPhaseClock=/\bint\s+avr_device_phase_clock\s*\(/.test(
  readFileSync(new URL('../../native/avr-device.inc',import.meta.url),'utf8'));
const create=compileAnalog('avr-phase-probe',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc',
  'analog_comparator','analog','power_reset','device',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#define AVR_FULL_DEVICE
#define avr_clock actual_avr_clock
#define avr_read_io actual_avr_read_io
#define avr_write_io actual_avr_write_io
#define avr_write_io_masked actual_avr_write_io_masked
#define avr_device_control actual_avr_device_control
#define avr_device_lpm actual_avr_device_lpm
${hasPhaseClock?'#define avr_device_phase_clock actual_avr_device_phase_clock':''}
#include ${JSON.stringify(native)}
#undef avr_clock
#undef avr_read_io
#undef avr_write_io
#undef avr_write_io_masked
#undef avr_device_control
#undef avr_device_lpm
#undef avr_device_phase_clock

enum { PROBE_CLOCK_ENTER=1, PROBE_CLOCK_EXIT, PROBE_READ, PROBE_WRITE,
 PROBE_CONTROL, PROBE_LPM, PROBE_AFTER_READ, PROBE_PHASE_ENTER, PROBE_PHASE_EXIT };
enum { PROBE_FIELDS=17, PROBE_CAPACITY=256 };
static uint32_t probe_trace[PROBE_CAPACITY][PROBE_FIELDS], probe_count, probe_overflow;
static int probe_replace_io=-1, probe_replace_value;
static void probe_record(uint32_t kind,uint32_t arg,uint32_t value) {
 if(probe_count==PROBE_CAPACITY){probe_overflow++;return;}
 uint32_t *row=probe_trace[probe_count++];
 uint64_t half=device_virtual_half(),at=device_physical_mode()?device_time_ps():device_base_half();
 row[0]=kind;row[1]=arg;row[2]=value;
 row[3]=(uint32_t)half;row[4]=(uint32_t)(half>>32);
 row[5]=(uint32_t)at;row[6]=(uint32_t)(at>>32);
 row[7]=(uint32_t)S(pc);row[8]=SP;row[9]=FLAGS;
 row[10]=data[16];row[11]=data[17];row[12]=data[26];row[13]=data[30];
 row[14]=data[AT13_MEMORY_RAMEND];row[15]=data[AT13_MEMORY_RAMEND-1];row[16]=(uint32_t)ERROR;
}
void avr_clock(double n) {
 probe_record(PROBE_CLOCK_ENTER,(uint32_t)(n*2),0);
 actual_avr_clock(n);
 probe_record(PROBE_CLOCK_EXIT,(uint32_t)(n*2),0);
}
${hasPhaseClock?`int avr_device_phase_clock(double n) {
 probe_record(PROBE_PHASE_ENTER,(uint32_t)(n*2),0);
 int status=actual_avr_device_phase_clock(n);
 probe_record(PROBE_PHASE_EXIT,(uint32_t)(n*2),(uint32_t)status);
 return status;
}`:''}
int avr_read_io(int io) {
 int value=actual_avr_read_io(io);probe_record(PROBE_READ,io,value);
 if(io==probe_replace_io){
  probe_replace_io=-1;
  actual_avr_write_io_masked(io,probe_replace_value,255);
  probe_record(PROBE_AFTER_READ,io,probe_replace_value);
 }
 return value;
}
int avr_write_io_masked(int io,int value,int mask) {
 probe_record(PROBE_WRITE,io,((uint32_t)mask<<8)|(uint8_t)value);
 return actual_avr_write_io_masked(io,value,mask);
}
int avr_write_io(int io,int value){return avr_write_io_masked(io,value,255);}
int avr_device_control(int command,int z,int word) {
 probe_record(PROBE_CONTROL,command,word);return actual_avr_device_control(command,z,word);
}
int avr_device_lpm(int z) {
 int value=actual_avr_device_lpm(z);probe_record(PROBE_LPM,z,value);return value;
}
void phase_probe_clear(void){probe_count=probe_overflow=0;probe_replace_io=-1;}
void phase_probe_replace_after_read(int io,int value){probe_replace_io=io;probe_replace_value=value;}
uint32_t phase_probe_count(void){return probe_count;}
uint32_t phase_probe_overflow(void){return probe_overflow;}
uint32_t phase_probe_field(uint32_t event,uint32_t field){
 return event<probe_count&&field<PROBE_FIELDS?probe_trace[event][field]:UINT32_MAX;
}
`,{fixedMemoryPages:4});

export const PHASE_EVENT=Object.freeze({CLOCK_ENTER:1,CLOCK_EXIT:2,READ:3,WRITE:4,CONTROL:5,LPM:6,AFTER_READ:7,
  PHASE_ENTER:8,PHASE_EXIT:9});
export function makePhaseProbe(binary,options={}){
  // compileAnalog asserts no host imports; every generated bridge below is a
  // WASM export too. There are no JS calls during generated CPU execution.
  const core=new ATtiny13A(binary,null,{fuseLow:0x7a,wakeStartupHalf:0,...options,runtimeModule:create.module});
  core._exports.phase_probe_clear();return core;
}
export function clearPhaseProbe(core){core._exports.phase_probe_clear();}
export function replaceAfterRead(core,io,value){core._exports.phase_probe_replace_after_read(io,value);}
export function phaseTrace(core){
  const e=core._exports;assert.equal(e.phase_probe_overflow(),0,'Native phase trace overflow');
  return Array.from({length:e.phase_probe_count()},(_,n)=>{
    const f=i=>e.phase_probe_field(n,i),u64=i=>BigInt(f(i))|(BigInt(f(i+1))<<32n);
    const at=u64(5);
    return {kind:f(0),argument:f(1),value:f(2),status:f(2)|0,half:u64(3),at,
      ...(e.avr_device_physical_mode()?{timePs:at}:{baseHalf:at}),pc:f(7),sp:f(8),sreg:f(9),
      r16:f(10),r17:f(11),x:f(12),z:f(13),stackLow:f(14),stackHigh:f(15),error:f(16)};
  });
}
