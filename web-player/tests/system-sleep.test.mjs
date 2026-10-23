import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=[process.env.EMSDK,join(root,'build/toolchains/emscripten-6.0.12'),
  resolve(root,'../../build/toolchains/emscripten-6.0.12')].find(p=>p&&existsSync(join(p,'upstream/bin/clang.exe')));
if(!sdk) throw new Error('Set EMSDK to the read-only Emscripten SDK to run system sleep tests.');
const out=join(root,'build/system-sleep-test/sleep.wasm');
mkdirSync(dirname(out),{recursive:true});
const wrapper=join(dirname(out),'wrapper.c');
writeFileSync(wrapper,`#include "system_sleep.h"
static system_sleep_t s;
void reset(uint64_t at) { system_sleep_reset(&s,at); }
int enter(int mcucr,uint64_t at) { return system_sleep_enter(&s,mcucr,at); }
int wake_mask(int mode,int level) { return system_sleep_wake_mask(mode,level); }
int wake(int asserted,int enabled,int level,uint64_t startup,uint64_t cpu_ticks,uint64_t at) {
 return system_sleep_wake(&s,asserted,enabled,level,(system_sleep_timing_t){startup,cpu_ticks},at);
}
int advance(uint64_t at) { return system_sleep_advance(&s,at); }
uint64_t next_event(void) { return system_sleep_next_event(&s); }
int domains(int prr,int wdt) { return system_sleep_domains(&s,prr,wdt); }
int clamp(void) { return system_sleep_input_clamp(&s); }
int adc_start(void) { return system_sleep_adc_start(&s); }
int phase(void) { return s.phase; }
int mode(void) { return s.mode; }
int sources(void) { return s.wake_sources; }
uint64_t ready(void) { return s.ready_at; }
`);
const exports=['reset','enter','wake_mask','wake','advance','next_event','domains',
  'clamp','adc_start','phase','mode','sources','ready'];
const sysroot=join(sdk,'upstream/emscripten/cache/sysroot');
const result=spawnSync(join(sdk,'upstream/bin/clang.exe'),[
  '--target=wasm32-unknown-unknown','-O3','-std=c11','-ffreestanding','-nostdlib',
  '-Wall','-Wextra','-Werror','--sysroot='+sysroot,'-isystem',join(sysroot,'include'),
  '-I',join(root,'web-player/native/peripherals'),'-Wl,--no-entry',
  ...exports.map(n=>'-Wl,--export='+n),
  join(root,'web-player/native/peripherals/system_sleep.c'),wrapper,'-o',out
],{encoding:'utf8'});
if(result.error||result.status!==0) throw result.error||new Error(result.stderr);
const module=await WebAssembly.compile(readFileSync(out));
const s=(await WebAssembly.instantiate(module)).exports;
const WAKE={RESET:1,INT0:2,PCINT:4,TIMER:8,NVM:16,COMP:32,TIMERA:64,TIMERB:128,WDT:256,ADC:512};
const CLOCK={CPU:1,FLASH:2,IO:4,ADC:8,WDT:16,ASYNC:32,MAIN:64,TIMER:128};
const enter=(mode,now=0n)=>s.enter(0x20|(mode<<3),now);
const wake=(source,{enabled=source,level=1,startup=0n,cpu=2n,at=0n}={})=>
  s.wake(source,enabled,level,startup,cpu,at);

test('sleep policy compiles into import-free WASM',()=>{
  assert.deepEqual(WebAssembly.Module.imports(module),[]);
});

test('SE disables sleep and reserved SM selection is reported explicitly',()=>{
  s.reset(0n); assert.equal(s.enter(0x18,0n),0); assert.equal(s.phase(),0);
  assert.equal(enter(3),2); assert.equal(s.phase(),0);
  assert.equal(enter(0),1); assert.equal(s.phase(),1);
  assert.equal(enter(1),64); assert.equal(s.mode(),0);
});

test('all documented sleep modes preserve the required clock domains',()=>{
  const expected=[CLOCK.IO|CLOCK.ADC|CLOCK.WDT|CLOCK.ASYNC|CLOCK.MAIN|CLOCK.TIMER,
    CLOCK.ADC|CLOCK.WDT|CLOCK.ASYNC|CLOCK.MAIN,CLOCK.WDT|CLOCK.ASYNC];
  for(let mode=0;mode<3;mode++) {
    s.reset(0n); assert.equal(enter(mode),1); assert.equal(s.domains(0,1),expected[mode]);
    assert.equal(s.domains(0,0),expected[mode]&~CLOCK.WDT);
    assert.equal(s.clamp(),mode===2?1:0); assert.equal(s.adc_start(),mode<2?1:0);
  }
});

test('PRR independently gates ADC and Timer0 without gating clkIO',()=>{
  s.reset(0n); assert.equal(s.domains(0,1),255);
  assert.equal(s.domains(1,1),255&~CLOCK.ADC);
  assert.equal(s.domains(2,1),255&~CLOCK.TIMER);
  assert.equal(s.domains(3,1),255&~(CLOCK.ADC|CLOCK.TIMER));
  assert.equal(s.domains(3,1)&CLOCK.IO,CLOCK.IO);
});

test('wake masks match idle, ADC noise reduction and power-down capabilities',()=>{
  assert.equal(s.wake_mask(0,0),0x3ff);
  const noise=WAKE.RESET|WAKE.PCINT|WAKE.NVM|WAKE.WDT|WAKE.ADC;
  const down=WAKE.RESET|WAKE.PCINT|WAKE.WDT;
  assert.equal(s.wake_mask(1,0),noise); assert.equal(s.wake_mask(1,1),noise|WAKE.INT0);
  assert.equal(s.wake_mask(2,0),down); assert.equal(s.wake_mask(2,1),down|WAKE.INT0);
  assert.equal(s.wake_mask(3,1),0);
});

test('individual masks and INT0 level sensing gate wake requests',()=>{
  s.reset(0n); enter(2);
  assert.equal(wake(WAKE.INT0,{enabled:0}),0); assert.equal(s.phase(),1);
  assert.equal(wake(WAKE.INT0,{level:0}),0); assert.equal(s.phase(),1);
  assert.equal(wake(WAKE.TIMER|WAKE.ADC),0); assert.equal(s.phase(),1);
  assert.equal(wake(WAKE.INT0),8); assert.equal(s.sources(),WAKE.INT0);
});

test('wake startup and four additional sleep cycles have explicit deadlines',()=>{
  s.reset(0n); enter(2);
  assert.equal(wake(WAKE.PCINT,{at:10n,startup:31n,cpu:2n}),8);
  assert.equal(s.phase(),2); assert.equal(s.next_event(),41n); assert.equal(s.ready(),49n);
  assert.equal(s.domains(0,1),CLOCK.WDT|CLOCK.ASYNC); assert.equal(s.clamp(),1);
  assert.equal(s.advance(40n),0); assert.equal(s.phase(),2);
  assert.equal(s.advance(41n),0); assert.equal(s.phase(),3); assert.equal(s.next_event(),49n);
  assert.equal(s.domains(0,1),255); assert.equal(s.clamp(),0);
  assert.equal(s.advance(48n),0); assert.equal(s.advance(49n),16);
  assert.equal(s.phase(),0); assert.equal(s.next_event(),-1n); assert.equal(s.adc_start(),0);
});

test('idle wake with no oscillator startup adds precisely four CPU cycles',()=>{
  s.reset(0n); enter(0); assert.equal(wake(WAKE.TIMER,{at:4n,cpu:10n}),8);
  assert.equal(s.phase(),3); assert.equal(s.ready(),44n);
  assert.equal(s.advance(44n),16); assert.equal(s.phase(),0);
});

test('PCINT and watchdog interrupts wake all three supported modes',()=>{
  for(const mode of [0,1,2]) for(const source of [WAKE.PCINT,WAKE.WDT]) {
    s.reset(0n); enter(mode); assert.equal(wake(source),8); assert.equal(s.advance(8n),16);
  }
});

test('reset wakes immediately without an interrupt enable or wake latency',()=>{
  for(const mode of [0,1,2]) {
    s.reset(0n); enter(mode); assert.equal(wake(WAKE.RESET,{enabled:0,at:10n}),4);
    assert.equal(s.phase(),0); assert.equal(s.sources(),WAKE.RESET); assert.equal(s.next_event(),-1n);
  }
});

test('INT0 wake completion does not force an ISR after its level disappears',()=>{
  s.reset(0n); enter(2); assert.equal(wake(WAKE.INT0,{startup:100n}),8);
  // GPIO can deassert INT0 while the oscillator starts. The policy only resumes
  // execution and leaves live vector arbitration to the CPU/GPIO bus.
  assert.equal(wake(0,{at:50n}),0); assert.equal(s.advance(108n),16);
  assert.equal(s.phase(),0); assert.equal(s.sources(),WAKE.INT0);
});

test('bad clocks, overflowing deadlines and backward scheduler time are explicit',()=>{
  s.reset(5n); assert.equal(s.enter(0x20,4n),32); assert.equal(enter(2,5n),1);
  assert.equal(wake(WAKE.PCINT,{at:5n,cpu:0n}),32); assert.equal(s.phase(),1);
  assert.equal(wake(WAKE.PCINT,{at:5n,startup:18446744073709551615n}),32);
  assert.equal(wake(WAKE.PCINT,{at:5n,cpu:18446744073709551615n}),32);
  assert.equal(s.advance(4n),32); assert.equal(s.phase(),1);
});

test('long sleeping and startup intervals advance directly to deadlines',()=>{
  s.reset(0n); enter(2); assert.equal(s.advance(1000000000000n),0);
  assert.equal(s.phase(),1); assert.equal(s.next_event(),-1n);
  assert.equal(wake(WAKE.WDT,{at:1000000000000n,startup:1000000000000n}),8);
  assert.equal(s.advance(3000000000000n),16); assert.equal(s.phase(),0);
});
