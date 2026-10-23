import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const sdk = [process.env.EMSDK, join(root,'build/toolchains/emscripten-6.0.12'),
  resolve(root,'../../build/toolchains/emscripten-6.0.12')].find(p => p && existsSync(join(p,'upstream/bin/clang.exe')));
if(!sdk) throw new Error('Set EMSDK to the read-only Emscripten SDK to run system watchdog tests.');
const out = join(root,'build/system-watchdog-test/watchdog.wasm');
mkdirSync(dirname(out),{recursive:true});
const wrapper=join(dirname(out),'wrapper.c');
writeFileSync(wrapper,`#include "system_watchdog.h"
static system_watchdog_t w;
void init(int fuse) { system_watchdog_init(&w,fuse); }
void reset(int source,uint64_t cpu,uint64_t ticks) { system_watchdog_reset(&w,source,cpu,ticks); }
int read_io(int io,uint64_t cpu) { uint8_t v; int r=system_watchdog_read(&w,io,cpu,&v); return r==1?v:-r-1; }
int write_io(int io,int value,int mask,uint64_t cpu) { return system_watchdog_write(&w,io,value,mask,cpu); }
int advance(uint64_t cpu,uint64_t ticks) { return system_watchdog_advance(&w,cpu,ticks); }
int pending(void) { return system_watchdog_pending(&w); }
void ack(void) { system_watchdog_ack(&w); }
void wdr(void) { system_watchdog_wdr(&w); }
unsigned period(void) { return system_watchdog_period(&w); }
unsigned until_timeout(void) { return system_watchdog_until_timeout(&w); }
unsigned counter(void) { return w.counter; }
uint64_t event_tick(void) { return w.last_event_tick; }
uint64_t now_tick(void) { return w.oscillator_tick; }
`);
const exports=['init','reset','read_io','write_io','advance','pending','ack','wdr',
  'period','until_timeout','counter','event_tick','now_tick'];
const sysroot=join(sdk,'upstream/emscripten/cache/sysroot');
const result=spawnSync(join(sdk,'upstream/bin/clang.exe'),[
  '--target=wasm32-unknown-unknown','-O3','-std=c11','-ffreestanding','-nostdlib',
  '-Wall','-Wextra','-Werror','--sysroot='+sysroot,'-isystem',join(sysroot,'include'),
  '-I',join(root,'web-player/native/peripherals'),'-Wl,--no-entry',
  ...exports.map(n=>'-Wl,--export='+n),
  join(root,'web-player/native/peripherals/system_watchdog.c'),wrapper,'-o',out
],{encoding:'utf8'});
if(result.error||result.status!==0) throw result.error||new Error(result.stderr);
const module=await WebAssembly.compile(readFileSync(out));
const w=(await WebAssembly.instantiate(module)).exports;
const WDT=0x21,MCU=0x34,IRQ=1,RESET=2;
const write=(io,value,cpu=0,mask=255)=>assert.equal(w.write_io(io,value,mask,BigInt(cpu)),1);
const read=(io,cpu=0)=>w.read_io(io,BigInt(cpu));
const advance=(ticks,cpu=0)=>w.advance(BigInt(cpu),BigInt(ticks));
const configure=(control,cpu=0)=>{write(WDT,0x18,cpu);write(WDT,control,cpu+1);};

test('watchdog builds to import-free WASM',()=>{
  assert.deepEqual(WebAssembly.Module.imports(module),[]);
});

test('all ten documented WDT prescalers count the independent oscillator',()=>{
  for(let select=0;select<10;select++) {
    w.init(0); const control=0x40|(select&7)|((select&8)<<2);
    configure(control); const period=2048*2**select;
    assert.equal(w.period(),period); assert.equal(w.until_timeout(),period);
    assert.equal(advance(period-1,1),0); assert.equal(w.pending(),0);
    assert.equal(advance(period,1),IRQ); assert.equal(w.pending(),1);
    assert.equal(w.event_tick(),BigInt(period)); assert.equal(w.counter(),0);
    w.ack(); assert.equal(w.pending(),0); assert.equal(read(WDT,1),control);
    assert.equal(advance(period*2,1),IRQ);
  }
});

test('CPU clock advance alone never clocks the watchdog and sleep does not stop WDT',()=>{
  w.init(0); write(WDT,0x40);
  assert.equal(advance(0,1000000000),0); assert.equal(w.counter(),0);
  assert.equal(advance(2048,1000000000),IRQ);
  assert.equal(w.pending(),1);
});

test('WDE and WDP protection, opening write and exact four-cycle deadline',()=>{
  w.init(0); write(WDT,8); write(WDT,0x07,1);
  assert.equal(read(WDT,1),8); assert.equal(w.period(),2048);
  write(WDT,0x18,10); assert.equal(read(WDT,13)&0x10,0x10);
  write(WDT,0,13); assert.equal(read(WDT,13),0);
  write(WDT,0x18,20); assert.equal(read(WDT,24)&0x10,0);
  write(WDT,0x07,24); assert.equal(read(WDT,24),8);
  write(WDT,0x18,30); write(WDT,0x40,31); assert.equal(read(WDT,31),0x40);
});

test('single-bit WDTIF writes neither clear adjacent controls nor extend WDCE',()=>{
  w.init(0); write(WDT,0x40); assert.equal(advance(2048),IRQ);
  write(WDT,0x18|0x40,10); write(WDT,0x80,12,0x80);
  assert.equal(read(WDT,14),0x48);
  write(WDT,0,15,0x40); assert.equal(read(WDT,15),8);
});

test('WDR restarts the counter without altering control bits',()=>{
  w.init(0); write(WDT,0x40); assert.equal(advance(2047),0);
  w.wdr(); assert.equal(w.counter(),0); assert.equal(read(WDT),0x40);
  assert.equal(advance(4094),0); assert.equal(advance(4095),IRQ);
});

test('interrupt-and-reset mode clears WDTIE only at vector acknowledgement',()=>{
  w.init(0); write(WDT,0x48); assert.equal(advance(2048),IRQ);
  assert.equal(read(WDT),0xc8); assert.equal(w.pending(),1);
  w.ack(); assert.equal(read(WDT),8); assert.equal(w.pending(),0);
  assert.equal(advance(4096),RESET); assert.equal(w.event_tick(),4096n);
});

test('unserviced combined watchdog interrupt resets at the second timeout',()=>{
  w.init(0); write(WDT,0x48);
  assert.equal(advance(999999),IRQ|RESET); assert.equal(w.event_tick(),4096n);
  assert.equal(w.now_tick(),4096n);
  w.init(0); write(WDT,0x48); assert.equal(advance(2048),IRQ);
  write(WDT,0x80,0,0x80); assert.equal(w.pending(),0);
  assert.equal(advance(4096),RESET);
});

test('system reset mode halts advancement at the actual reset timestamp',()=>{
  w.init(0); write(WDT,8); assert.equal(advance(1000000),RESET);
  assert.equal(w.event_tick(),2048n); assert.equal(w.now_tick(),2048n);
  assert.equal(w.until_timeout(),0);
  w.reset(8,0n,2048n); assert.equal(read(MCU),9); assert.equal(read(WDT),8);
  assert.equal(advance(4096),RESET);
});

test('MCUSR reset sources accumulate and use write-zero clearing',()=>{
  w.init(0); assert.equal(read(MCU),1);
  w.reset(2,0n,0n); w.reset(4,0n,0n); assert.equal(read(MCU),7);
  write(MCU,0,0,2); assert.equal(read(MCU),5);
  write(MCU,0xff); assert.equal(read(MCU),5);
  w.reset(1,0n,0n); assert.equal(read(MCU),1);
});

test('WDRF must be cleared before WDE can be cleared',()=>{
  w.init(0); w.reset(8,0n,0n); configure(0);
  assert.equal(read(WDT,1),8); write(MCU,0,1);
  configure(0,2); assert.equal(read(WDT,3),0);
});

test('WDTON fuse locks system-reset mode even after a timed write',()=>{
  w.init(1); assert.equal(read(WDT),8); configure(0x40|0x21);
  assert.equal(read(WDT,1),0x29); assert.equal(w.period(),1048576);
  assert.equal(advance(1048576,1),RESET);
});

test('reserved WDP values and backward time report explicit errors',()=>{
  w.init(0); configure(0x40|0x22); assert.equal(w.period(),0);
  assert.equal(advance(2048,1),4); assert.equal(w.now_tick(),0n);
  w.init(0); write(WDT,0x40); assert.equal(advance(23,10),0);
  assert.equal(advance(22,10),8); assert.equal(w.now_tick(),23n);
  assert.equal(advance(24,9),8); assert.equal(w.now_tick(),23n);
});

test('interrupt-only bulk advance coalesces millions of timeout events',()=>{
  w.init(0); write(WDT,0x40);
  const ticks=2048n*10000000n+23n;
  assert.equal(w.advance(0n,ticks),IRQ); assert.equal(w.counter(),23);
  assert.equal(w.event_tick(),ticks-23n); assert.equal(w.now_tick(),ticks);
});

test('seeded batched interrupt-only advances agree with single oscillator ticks',async()=>{
  const slow=(await WebAssembly.instantiate(module)).exports;
  w.init(0); slow.init(0); write(WDT,0x40); slow.write_io(WDT,0x40,255,0n);
  let seed=0x13a,end=0;
  for(let batch=0;batch<100;batch++) {
    seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
    const target=end+(seed>>>0)%4097;
    advance(target);
    for(let tick=end+1;tick<=target;tick++) slow.advance(0n,BigInt(tick));
    assert.equal(w.counter(),slow.counter()); assert.equal(w.pending(),slow.pending());
    assert.equal(w.event_tick(),slow.event_tick()); end=target;
    if(batch%3===0){w.ack();slow.ack();}
    if(batch%7===0){w.wdr();slow.wdr();}
  }
});
