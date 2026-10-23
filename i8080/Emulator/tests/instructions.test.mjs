import test from 'node:test';
import assert from 'node:assert/strict';
import { CPU8080 } from '../core8080.mjs';

const make = code => new CPU8080(Uint8Array.from(code), { memoryMode: 'allram' });
const flags = index => 2 | ((index & 1) ? 1 : 0) | ((index & 2) ? 4 : 0) |
  ((index & 4) ? 16 : 0) | ((index & 8) ? 64 : 0) | ((index & 16) ? 128 : 0);

test('RLC/RRC/RAL/RAR: all A values and all 32 initial PSWs; only CY changes', () => {
  const cpu = make([0]);
  for (const op of [7, 15, 23, 31]) for (let a = 0; a < 256; a++) for (let f = 0; f < 32; f++) {
    cpu.pc = 0; cpu.mem[0] = op; cpu.r[7] = a; cpu.unpackFlags(flags(f));
    const old = cpu.packFlags(), bits = a.toString(2).padStart(8, '0').split('');
    const left = op === 7 || op === 23, throughCarry = op === 23 || op === 31;
    const outgoing = Number(left ? bits.shift() : bits.pop());
    const incoming = String(throughCarry ? old & 1 : outgoing);
    if (left) bits.push(incoming); else bits.unshift(incoming);
    assert.equal(cpu.step(), 4);
    assert.equal(cpu.r[7], parseInt(bits.join(''), 2));
    assert.equal(cpu.packFlags(), (old & 0xfe) | outgoing);
  }
});

test('All MOV/MVI destinations, including old-HL memory addressing and flag preservation', () => {
  for (let dst = 0; dst < 8; dst++) for (let src = 0; src < 8; src++) {
    if (dst === 6 && src === 6) continue; // HLT
    const cpu = make([0x40 | dst << 3 | src]);
    cpu.r.set([0x12, 0x34, 0x56, 0x78, 0x20, 0x10, 0, 0xa5]); cpu.mem[0x2010] = 0x9b;
    cpu.unpackFlags(0xd7); const before = [...cpu.r], value = src === 6 ? 0x9b : before[src];
    assert.equal(cpu.step(), dst === 6 || src === 6 ? 7 : 5);
    assert.equal(cpu.packFlags(), 0xd7);
    for (let reg = 0; reg < 8; reg++) if (reg !== 6) assert.equal(cpu.r[reg], reg === dst ? value : before[reg]);
    assert.equal(cpu.mem[0x2010], dst === 6 ? value : 0x9b);
  }
  for (let dst = 0; dst < 8; dst++) {
    const cpu = make([6 | dst << 3, 0xc3]); cpu.setpair(2, 0x2010); cpu.unpackFlags(0x93);
    assert.equal(cpu.step(), dst === 6 ? 10 : 7);
    assert.equal(dst === 6 ? cpu.mem[0x2010] : cpu.r[dst], 0xc3);
    assert.equal(cpu.packFlags(), 0x93);
  }
});

test('ADC followed by DAA: 10,000 decimal additions with incoming carry', () => {
  const cpu = make([0x88, 0x27]), bcd = n => (Math.floor(n / 10) << 4) | n % 10;
  for (let a = 0; a < 100; a++) for (let b = 0; b < 100; b++) {
    cpu.pc = 0; cpu.r[7] = bcd(a); cpu.r[0] = bcd(b); cpu.f.cy = 1;
    cpu.step(); cpu.step();
    const sum = a + b + 1, value = bcd(sum % 100);
    assert.equal(cpu.r[7], value, `${a}+${b}+1`);
    assert.equal(cpu.f.cy, +(sum >= 100));
    assert.equal(cpu.f.z, +(value === 0)); assert.equal(cpu.f.s, +(value >= 128));
    assert.equal(cpu.f.p, +(value.toString(2).replaceAll('0', '').length % 2 === 0));
  }
});

test('DAD across 16-bit carry boundaries preserves S/Z/AC/P for every initial PSW', () => {
  const values = [0, 1, 15, 0x7fff, 0x8000, 0xfffe, 0xffff];
  for (let pair = 0; pair < 4; pair++) for (const hl of values) for (const arg of values) for (let f = 0; f < 32; f++) {
    const cpu = make([9 | pair << 4]); cpu.setpair(2, hl); cpu.setpair(pair, arg); cpu.unpackFlags(flags(f));
    const lhs = cpu.hl(), rhs = pair === 3 ? cpu.sp : cpu.pair(pair), initial = cpu.packFlags();
    assert.equal(cpu.step(), 10);
    assert.equal(cpu.hl(), (lhs + rhs) & 65535);
    assert.equal(cpu.packFlags(), (initial & 0xfe) | +(lhs + rhs > 65535));
  }
});

test('INX/DCX for BC/DE/HL/SP wrap and preserve all flags; transfers also preserve flags', () => {
  for (let pair = 0; pair < 4; pair++) for (const decrement of [false, true]) for (const value of [0, 1, 0xfffe, 0xffff]) for (let f = 0; f < 32; f++) {
    const cpu = make([(decrement ? 0x0b : 3) | pair << 4]); cpu.setpair(pair, value); cpu.unpackFlags(flags(f));
    assert.equal(cpu.step(), 5);
    assert.equal(pair === 3 ? cpu.sp : cpu.pair(pair), (value + (decrement ? -1 : 1)) & 65535);
    assert.equal(cpu.packFlags(), flags(f));
  }
  for (const op of [0xe9, 0xeb, 0xf9]) for (let f = 0; f < 32; f++) {
    const cpu = make([op]); cpu.setpair(2, 0xabcd); cpu.setpair(1, 0x1234); cpu.unpackFlags(flags(f));
    cpu.step(); assert.equal(cpu.packFlags(), flags(f));
    if (op === 0xe9) assert.equal(cpu.pc, 0xabcd);
    if (op === 0xeb) { assert.equal(cpu.hl(), 0x1234); assert.equal(cpu.pair(1), 0xabcd); }
    if (op === 0xf9) assert.equal(cpu.sp, 0xabcd);
  }
});

test('RET uses a return word in ROM with no memory writes, including SP wrap', () => {
  const rom = new Uint8Array(65536).fill(0xff);
  rom.set([0x31, 0xff, 0xff, 0xc3, 0x10, 0]); // LXI SP,FFFF; JMP routine
  rom[0x10] = 0xc9; rom[0xffff] = 0x34; // Return high byte is ROM[0000]=31h.
  const cpu = new CPU8080(rom, { memoryMode: 'rom' }); cpu.unpackFlags(0xd7);
  cpu.step(); cpu.step(); assert.equal(cpu.step(), 10);
  assert.equal(cpu.pc, 0x3134); assert.equal(cpu.sp, 1);
  assert.equal(cpu.packFlags(), 0xd7); assert.equal(cpu.memWrites, 0);
});

test('SHLD/LHLD wrap at FFFF; all RST vectors push the following PC little endian', () => {
  const cpu = make([0x22, 0xff, 0xff, 0x2a, 0xff, 0xff]); cpu.setpair(2, 0x1234); cpu.unpackFlags(0xd7);
  assert.equal(cpu.step(), 16); assert.equal(cpu.mem[65535], 0x34); assert.equal(cpu.mem[0], 0x12);
  cpu.setpair(2, 0); assert.equal(cpu.step(), 16); assert.equal(cpu.hl(), 0x1234); assert.equal(cpu.packFlags(), 0xd7);
  for (let vector = 0; vector < 8; vector++) {
    const c = make([0xc7 | vector << 3]); c.sp = 1; c.unpackFlags(0x97);
    assert.equal(c.step(), 11); assert.equal(c.pc, vector * 8); assert.equal(c.sp, 65535);
    assert.equal(c.mem[65535], 1); assert.equal(c.mem[0], 0); assert.equal(c.packFlags(), 0x97);
  }
});
