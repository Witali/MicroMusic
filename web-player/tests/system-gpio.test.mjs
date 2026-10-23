import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const sdk = [process.env.EMSDK,
  join(root, 'build/toolchains/emscripten-6.0.12'),
  resolve(root, '../../build/toolchains/emscripten-6.0.12')].find(p => p && existsSync(join(p, 'upstream/bin/clang.exe')));
if (!sdk) throw new Error('Set EMSDK to the read-only Emscripten SDK to run system GPIO tests.');
const out = join(root, 'build/system-gpio-test/gpio.wasm');
mkdirSync(dirname(out), { recursive: true });
const wrapper = join(dirname(out), 'wrapper.c');
writeFileSync(wrapper, `#include "system_gpio.h"
static system_gpio_t gpio;
static system_gpio_t0_event_t events[4];
void reset(int reset_pin) { system_gpio_reset(&gpio, reset_pin); }
int read_io(int io) { uint8_t v = 0; return system_gpio_read(&gpio, io, &v) ? v : -1; }
int write_io(int io,int value,uint64_t at) { return system_gpio_write(&gpio,io,value,at); }
int write_bit(int io,int value,int mask,uint64_t at) { return system_gpio_write_masked(&gpio,io,value,mask,at); }
void external(int mask,int levels,uint64_t at) { system_gpio_external(&gpio,mask,levels,at); }
void floating(int levels,uint64_t at) { system_gpio_floating(&gpio,levels,at); }
void outputs(int mask,int levels,uint64_t at) { system_gpio_timer_outputs(&gpio,mask,levels,at); }
void sleep_mode(int running,int deep,uint64_t at) { system_gpio_sleep(&gpio,running,deep,at); }
int clock_edge(int rising,uint64_t at) { return system_gpio_clock(&gpio,rising,at); }
int advance(uint64_t begin,uint64_t end) { return system_gpio_advance(&gpio,begin,end,events); }
uint64_t next_event(uint64_t at) { return system_gpio_next_event_half(&gpio,at); }
int settled(void) { return system_gpio_settled(&gpio); }
uint64_t event_time(int i) { return events[i].half_cycle; }
int event_edge(int i) { return events[i].edge; }
unsigned state(void) { return (unsigned)&gpio; }
unsigned size(void) { return sizeof(gpio); }
int pending(void) { return system_gpio_pending(&gpio); }
void ack(int vector) { system_gpio_ack(&gpio,vector); }
int pins(int field) { switch(field) {
case 0: return gpio.pins.levels; case 1: return gpio.pins.driven;
case 2: return gpio.pins.pullups; case 3: return gpio.pins.floating;
case 4: return gpio.pins.contention; default: return -1; } }
uint64_t timestamp(void) { return gpio.pins.half_cycle; }
`);
const exports = ['reset','read_io','write_io','write_bit','external','floating','outputs','sleep_mode',
  'clock_edge','advance','next_event','settled','event_time','event_edge','state','size',
  'pending','ack','pins','timestamp'];
const sysroot = join(sdk, 'upstream/emscripten/cache/sysroot');
const result = spawnSync(join(sdk, 'upstream/bin/clang.exe'), [
  '--target=wasm32-unknown-unknown', '-O3', '-std=c11', '-ffreestanding', '-nostdlib',
  '-Wall', '-Wextra', '-Werror', '--sysroot=' + sysroot,
  '-isystem', join(sysroot, 'include'), '-I', join(root, 'web-player/native/peripherals'),
  '-Wl,--no-entry', '-Wl,--export-memory', ...exports.map(n => '-Wl,--export=' + n),
  join(root, 'web-player/native/peripherals/system_gpio.c'), wrapper, '-o', out
], { encoding: 'utf8' });
if (result.error || result.status !== 0) throw result.error || new Error(result.stderr);
const module = await WebAssembly.compile(readFileSync(out));
const g = (await WebAssembly.instantiate(module)).exports;
const IO = { DIDR:0x14, MASK:0x15, PIN:0x16, DDR:0x17, PORT:0x18, MCU:0x35, FLAG:0x3a, ENABLE:0x3b };
const write = (io,value,at=0) => assert.equal(g.write_io(io,value,BigInt(at)),1);
const external = (mask,levels,at=0) => g.external(mask,levels,BigInt(at));
const rise = (at=0) => g.clock_edge(1,BigInt(at));
const fall = (at=1) => g.clock_edge(0,BigInt(at));
const cycles = n => { for(let c=0;c<n;c++) { fall(c*2+1); rise(c*2+2); } };

test('GPIO module compiles to WASM without any host imports', () => {
  assert.deepEqual(WebAssembly.Module.imports(module), []);
});

test('GPIO direction, reserved bits, pull-up and PUD truth table', () => {
  g.reset(0);
  write(IO.PORT,255); assert.equal(g.read_io(IO.PORT),63);
  assert.equal(g.pins(0),63); assert.equal(g.pins(1),0); assert.equal(g.pins(2),63);
  write(IO.MCU,255); assert.equal(g.read_io(IO.MCU),0x7b);
  assert.equal(g.pins(0),0); assert.equal(g.pins(2),0); assert.equal(g.pins(3),63);
  write(IO.DDR,255); assert.equal(g.read_io(IO.DDR),63);
  assert.equal(g.pins(0),63); assert.equal(g.pins(1),63);
  write(IO.PORT,0); assert.equal(g.pins(0),0);
  assert.equal(g.read_io(0),-1); assert.equal(g.write_io(0,255,0n),0);
});

test('PINB write-one toggle works for both input pull-ups and driven outputs', () => {
  g.reset(0); write(IO.PORT,0x15); write(IO.DDR,0x07);
  write(IO.PIN,0x3f); assert.equal(g.read_io(IO.PORT),0x2a);
  write(IO.PIN,0); assert.equal(g.read_io(IO.PORT),0x2a);
  write(IO.PIN,0x82); assert.equal(g.read_io(IO.PORT),0x28);
  assert.equal(g.pins(1),7); assert.equal(g.pins(2),0x28);
});

test('masked SBI/CBI touch only selected PINB and flag bits', () => {
  g.reset(0); write(IO.DDR,3); write(IO.PORT,3); cycles(3);
  assert.equal(g.read_io(IO.PIN),3);
  g.write_bit(IO.PIN,2,2,0n); assert.equal(g.read_io(IO.PORT),1);
  g.write_bit(IO.PIN,0,1,0n); assert.equal(g.read_io(IO.PORT),1);
  write(IO.MASK,1); write(IO.MCU,1); external(2,2); cycles(4);
  assert.equal(g.read_io(IO.FLAG),0x60);
  g.write_bit(IO.FLAG,0x40,0x40,0n); assert.equal(g.read_io(IO.FLAG),0x20);
  g.write_bit(IO.FLAG,0,0x20,0n); assert.equal(g.read_io(IO.FLAG),0x20);
});

test('external levels override weak pull-ups and contention is explicit', () => {
  g.reset(0); write(IO.PORT,3); external(1,0,42);
  assert.equal(g.pins(0),2); assert.equal(g.pins(2),3); assert.equal(g.pins(4),0);
  write(IO.DDR,1,43); assert.equal(g.pins(0),3); assert.equal(g.pins(4),1);
  assert.equal(g.timestamp(),43n);
  g.floating(0x3c,44n); assert.equal(g.pins(0),63); assert.equal(g.pins(3),0x3c);
});

test('RSTDISBL chooses GPIO PB5 versus reset pull-up and disabled digital input', () => {
  g.reset(1); write(IO.DDR,0x20); write(IO.MCU,0x40); cycles(2);
  assert.equal(g.pins(1)&0x20,0); assert.equal(g.pins(2)&0x20,0x20);
  assert.equal(g.pins(0)&0x20,0x20); assert.equal(g.read_io(IO.PIN)&0x20,0);
  g.reset(0); write(IO.DDR,0x20); write(IO.PORT,0x20); cycles(2);
  assert.equal(g.pins(1)&0x20,0x20); assert.equal(g.read_io(IO.PIN)&0x20,0x20);
});

test('PINB sampling distinguishes changes before and after the falling edge', () => {
  g.reset(0); fall(1); external(1,1,1); rise(2);
  assert.equal(g.read_io(IO.PIN),0);
  fall(3); rise(4); assert.equal(g.read_io(IO.PIN),1);
  g.reset(0); external(1,1,0); fall(1); rise(2);
  assert.equal(g.read_io(IO.PIN),1);
  write(IO.DDR,2,2); write(IO.PORT,2,2);
  assert.equal(g.read_io(IO.PIN),1); fall(3); rise(4);
  assert.equal(g.read_io(IO.PIN),3);
});

test('digital disable bits follow PB pin order and do not alter physical drive', () => {
  g.reset(0); external(63,63); cycles(2); assert.equal(g.read_io(IO.PIN),63);
  write(IO.DIDR,255); cycles(2);
  assert.equal(g.read_io(IO.DIDR),63); assert.equal(g.read_io(IO.PIN),0);
  assert.equal(g.pins(0),63);
});

test('Timer0 OC overrides affect PB0/PB1 only when DDRB enables outputs', () => {
  g.reset(0); write(IO.PORT,0x3c); g.outputs(255,255,1n);
  assert.equal(g.pins(0),0x3c); write(IO.DDR,3); assert.equal(g.pins(0),0x3f);
  g.outputs(3,0,2n); assert.equal(g.pins(0),0x3c);
  write(IO.PORT,63); assert.equal(g.pins(0),0x3c);
  g.outputs(0,0,3n); assert.equal(g.pins(0),63);
});

test('INT0 level is live and INTF0 stays clear, edge flags latch without GIMSK', () => {
  g.reset(0); external(2,2); cycles(3); write(IO.ENABLE,0x40);
  assert.equal(g.pending(),0); external(2,0); assert.equal(g.pending(),0x40);
  assert.equal(g.read_io(IO.FLAG),0); g.ack(1); assert.equal(g.pending(),0x40);
  external(2,2); assert.equal(g.pending(),0);
  write(IO.ENABLE,0); write(IO.MCU,2); external(2,0); cycles(3);
  assert.equal(g.read_io(IO.FLAG),0x40); assert.equal(g.pending(),0);
  write(IO.ENABLE,0xff); assert.equal(g.read_io(IO.ENABLE),0x60);
  assert.equal(g.pending(),0x40); write(IO.FLAG,0x20); assert.equal(g.pending(),0x40);
  write(IO.FLAG,0x40); assert.equal(g.pending(),0);
});

test('INT0 change/rising/falling modes and interrupt acknowledge', () => {
  for (const sense of [1,2,3]) {
    g.reset(0); write(IO.MCU,sense); write(IO.ENABLE,0x40);
    external(2,2); cycles(3);
    assert.equal(g.pending(),sense===2 ? 0 : 0x40);
    g.ack(1); external(2,0); cycles(3);
    assert.equal(g.pending(),sense===3 ? 0 : 0x40);
    write(IO.MCU,0); assert.equal(g.read_io(IO.FLAG)&0x40,0);
  }
});

test('PCINT masks, software-generated output edges, W1C and vector acknowledgement', () => {
  g.reset(0); write(IO.MASK,0xff); assert.equal(g.read_io(IO.MASK),63);
  write(IO.MASK,1); external(2,2); cycles(4); assert.equal(g.read_io(IO.FLAG),0);
  external(3,3); cycles(4); assert.equal(g.read_io(IO.FLAG),0x20);
  assert.equal(g.pending(),0); write(IO.ENABLE,0x20); assert.equal(g.pending(),0x20);
  g.ack(1); assert.equal(g.pending(),0x20); g.ack(2); assert.equal(g.pending(),0);
  write(IO.DDR,1); write(IO.PORT,1); cycles(4); g.ack(2);
  write(IO.PIN,1); cycles(4); assert.equal(g.pending(),0x20);
  write(IO.FLAG,0); assert.equal(g.pending(),0x20);
  write(IO.FLAG,255); assert.equal(g.pending(),0);
});

test('stopped clkI/O retains PINB and accepts asynchronous PCINT and INT0 level', () => {
  g.reset(0); write(IO.MASK,1); write(IO.ENABLE,0x60); cycles(4);
  g.sleep_mode(0,1,10n); external(3,3,11); cycles(4);
  assert.equal(g.read_io(IO.PIN),0); assert.equal(g.pending(),0x20);
  external(3,1,12); assert.equal(g.pending(),0x60);
  g.sleep_mode(1,0,13n); cycles(4); assert.equal(g.read_io(IO.PIN),1);
});

test('T0 edge detector returns pulses after 2.5–3.5 clkI/O cycles', () => {
  g.reset(0); external(4,4,0); fall(1);
  assert.equal(rise(2),0); fall(3); assert.equal(rise(4),0);
  fall(5); assert.equal(rise(6),1); fall(7); assert.equal(rise(8),0);
  g.reset(0); fall(1); external(4,4,1);
  assert.equal(rise(2),0); fall(3); assert.equal(rise(4),0);
  fall(5); assert.equal(rise(6),0); fall(7); assert.equal(rise(8),1);
  external(4,0,8); fall(9); assert.equal(rise(10),0);
  fall(11); assert.equal(rise(12),0); fall(13); assert.equal(rise(14),2);
});

test('bounded GPIO advance timestamps T0 and skips a trillion settled half-cycles',()=>{
  g.reset(0); external(4,4,0);
  assert.equal(g.next_event(0n),1n);
  assert.equal(g.advance(0n,1000000000000n),1);
  assert.equal(g.event_time(0),6n); assert.equal(g.event_edge(0),1);
  assert.equal(g.settled(),1); assert.equal(g.next_event(1000000000000n),-1n);
  assert.equal(g.advance(1000000000000n,2000000000000n),0);
  assert.equal(g.advance(10n,9n),255);
});

test('seeded bounded advancement matches every clock edge across GPIO mutations',async()=>{
  const slow=(await WebAssembly.instantiate(module)).exports;
  g.reset(0); slow.reset(0); let seed=0x13a44,now=0n;
  const random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;};
  const state=instance=>new Uint8Array(instance.memory.buffer,instance.state(),instance.size()).slice();
  for(let run=0;run<2000;run++) {
    const value=random()&63, mask=random()&63, choice=random()%5;
    for(const x of [g,slow]) {
      if(choice===0) x.external(mask,value,now);
      if(choice===1) x.outputs(mask,value,now);
      if(choice===2) x.floating(value,now);
      if(choice===3) x.sleep_mode(value&1,(value>>1)&1,now);
      if(choice===4) {
        const registers=[IO.DDR,IO.PORT,IO.PIN,IO.MASK,IO.ENABLE,IO.MCU,IO.DIDR,IO.FLAG];
        // Choice must be identical for both instances.
        x.write_io(registers[run%registers.length],value,now);
      }
    }
    const end=now+BigInt(random()%32), expected=[];
    for(let at=now+1n;at<=end;at++) {
      const edge=slow.clock_edge(Number(!(at&1n)),at);
      if(edge) expected.push([at,edge]);
    }
    const count=g.advance(now,end);
    assert.equal(count,expected.length,'T0 count at run '+run);
    assert.deepEqual(Array.from({length:count},(_,i)=>[g.event_time(i),g.event_edge(i)]),expected);
    assert.deepEqual(state(g),state(slow),'peripheral state at run '+run);
    now=end;
  }
});
