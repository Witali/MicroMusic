import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';

const rr = (op, d = 17, s = 18) => op | (d << 4) | (s & 15) | ((s & 16) << 5);
const imm = (op, d, k) => op | ((d - 16) << 4) | (k & 15) | ((k & 240) << 4);
const out = (a, d = 17) => 0xb800 | (d << 4) | (a & 15) | ((a & 48) << 5);
const input = (a, d = 17) => 0xb000 | (d << 4) | (a & 15) | ((a & 48) << 5);
const jump = delta => 0xc000 | (delta & 4095);
function cpu(words, start = 16, options) {
  const rom = new Uint8Array(1024).fill(255);
  words.forEach((w, i) => { const p = ((start + i) & 511) * 2; rom[p] = w; rom[p + 1] = w >> 8; });
  const core = new AVRCore(rom, null, options); core.pc = start;
  return core;
}
function same(fast, slow) {
  assert.deepEqual(fast.data, slow.data);
  assert.deepEqual(fast.irqFrames, slow.irqFrames);
  for (const key of ['pc', 'cyc', 'timer', 'timerDivisor', 'prescalerAt', 'overflowAt',
    'irqDelay', 'irqStart', 'irqCount', 'inIRQ', 'minSP', 'lost', 'workLost', 'maxIRQ',
    'duty', 'writes', 'eempeUntil', 'clkprUntil']) assert.equal(fast[key], slow[key], key);
}
function advance(fast, slow) {
  if (!fast.runBlock()) fast.step();
  while (slow.cyc < fast.cyc) slow.step();
  same(fast, slow);
}

for (const [name, opcode, immediate] of [
  ['ADD', 0x0c00], ['ADC', 0x1c00], ['SUB', 0x1800], ['CPI', 0x3000, true],
  ['SUBI', 0x5000, true], ['AND', 0x2000], ['EOR', 0x2400], ['OR', 0x2800],
  ['ANDI', 0x7000, true], ['ORI', 0x6000, true],
]) test(`block ${name}: all byte operands and flag carry/preservation inputs`, () => {
  const fast = cpu([rr(opcode), out(0x29)]), slow = cpu([rr(opcode), out(0x29)]);
  for (let y = 0; y < 256; y++) {
    if (immediate) for (const c of [fast, slow]) {
      const w = imm(opcode, 17, y); c.rom[32] = w; c.rom[33] = w >> 8; c.decode(16);
    }
    for (let x = 0; x < 256; x++) for (const flags of [0, 0xff]) {
      for (const c of [fast, slow]) { c.pc = 16; c.cyc = 0; c.r[17] = x; c.r[18] = y; c.sreg = flags; }
      assert.equal(fast.runBlock(), true); slow.step();
      assert.equal(fast.r[17], slow.r[17], `${name} ${x},${y}`);
      assert.equal(fast.sreg, slow.sreg, `${name} SREG ${x},${y},${flags}`);
      assert.equal(fast.pc, slow.pc); assert.equal(fast.cyc, slow.cyc);
    }
  }
});

for (const [name, opcode] of [['INC', 0x9403], ['DEC', 0x940a], ['COM', 0x9400],
  ['LSR', 0x9406], ['ASR', 0x9405], ['ROR', 0x9407], ['SWAP', 0x9402]]) {
  test(`block ${name}: every byte and SREG value`, () => {
    const fast = cpu([opcode | (17 << 4), out(0x29)]), slow = cpu([opcode | (17 << 4), out(0x29)]);
    for (let x = 0; x < 256; x++) for (let flags = 0; flags < 256; flags++) {
      for (const c of [fast, slow]) { c.pc = 16; c.cyc = 0; c.r[17] = x; c.sreg = flags; }
      assert.equal(fast.runBlock(), true); slow.step();
      assert.equal(fast.r[17], slow.r[17]); assert.equal(fast.sreg, slow.sreg);
      assert.equal(fast.cyc, slow.cyc); assert.equal(fast.pc, slow.pc);
    }
  });
}

test('blocks stop before each possible Timer0 overflow position and preserve all IRQ counters', () => {
  const program = [imm(0xe000, 26, 96), imm(0xe000, 30, 128),
    imm(0xe000, 17, 0x81), rr(0x2c00, 18, 17), 0x9405 | (18 << 4),
    rr(0x0c00, 17, 18), rr(0x1c00, 18, 17), 0x900d | (19 << 4),
    0x9201 | (19 << 4), 0x9005 | (20 << 4), jump(-11)];
  for (const source of [1, 2, 3, 4, 5]) for (const mode of [0, 3]) {
    const positions = source === 1 ? Array.from({length:80}, (_, i) => i + 1) : [1, 2, 3];
    for (const position of positions) for (const phase of [0, 3]) {
      const fast = cpu(program), slow = cpu(program);
      for (const c of [fast, slow]) {
        c.rom[6] = out(0x29) & 255; c.rom[7] = out(0x29) >> 8; c.decode(3);
        c.r[26] = 96; c.r[30] = 128;
        c.clock(phase); c.writeIO(0x2f, mode); c.writeIO(0x33, source);
        c.writeIO(0x32, (mode === 3 ? 255 : 256) - position);
        c.writeIO(0x39, 2); c.sreg = 0xc0;
        c.writeIO(0x1c, 4); c.writeIO(0x26, 128);
      }
      while (!fast.writes) advance(fast, slow);
      assert.equal(fast.irqCount, 1); assert.equal(fast.lost, 0); assert.equal(fast.pending, false);
    }
  }
});

test('I/O, EEPROM stalls, SEI/RETI latency, masked IRQs and nested IRQs keep single-step semantics', () => {
  const program = [imm(0xe000, 17, 1), out(0x33), imm(0xe000, 17, 2), out(0x39),
    imm(0xe000, 17, 0xff), out(0x32), 0x9478, input(0x32, 18),
    imm(0xe000, 17, 1), out(0x1c), input(0x1d, 19), jump(-4)];
  const fast = cpu(program), slow = cpu(program);
  for (const c of [fast, slow]) {
    // Nested IRQ: re-enable I before returning from the outer ISR.
    const words = [0x9478, 0, 0x9518];
    words.forEach((w, i) => { c.rom[(3 + i) * 2] = w; c.rom[(3 + i) * 2 + 1] = w >> 8; c.decode(3 + i); });
    c.eeprom[0] = 0xa5;
  }
  let nested = false;
  while (fast.cyc < 2000) {
    if (fast.inIRQ && fast.i && fast.irqDelay === 0 && !nested) {
      for (const c of [fast, slow]) c.pending = true;
      nested = true;
    }
    advance(fast, slow);
  }
  assert.ok(nested); assert.ok(fast.irqCount > 2); assert.equal(fast.r[19], 0xa5);
  assert.ok(fast.blockInstructions > 0);
});

test('blocks preserve branch and skip widths across the end of Flash and refresh after decode', () => {
  for (let bit = 0; bit < 8; bit++) for (const value of [0, 1]) for (const sense of [0, 1]) {
    const branch = (sense ? 0xf000 : 0xf400) | (1 << 3) | bit;
    const program = [branch, imm(0xe000, 17, 44), imm(0xe000, 18, 33), out(0x29)];
    const fast = cpu(program, 511), slow = cpu(program, 511);
    for (const c of [fast, slow]) c.sreg = value << bit;
    advance(fast, slow); assert.equal(fast.pc, 2);
  }
  for (const bit of [0, 1, 6, 7]) for (const value of [0, 1]) for (const sense of [0, 1]) {
    for (const width of [1, 2]) {
      const skip = 0xfc00 | (sense << 9) | (17 << 4) | bit;
      const program = [skip, ...(width === 2 ? [0x9000, 96] : [0]), out(0x29)];
      const fast = cpu(program, 511), slow = cpu(program, 511);
      for (const c of [fast, slow]) c.r[17] = value << bit;
      while (fast.pc !== (511 + 1 + width) % 512) advance(fast, slow);
    }
  }
  const fast = cpu([imm(0xe000, 17, 4), 0, out(0x29)]), slow = cpu([imm(0xe000, 17, 4), 0, out(0x29)]);
  for (const c of [fast, slow]) { c.rom[34] = out(0x29) & 255; c.rom[35] = out(0x29) >> 8; c.decode(17); }
  advance(fast, slow); assert.equal(fast.pc, 17); assert.equal(fast.blockInstructions, 1);
});

test('blocks reproduce the single-step no-PWM timeout boundary', () => {
  const fast = new AVRCore(new Uint8Array(1024)), slow = new AVRCore(new Uint8Array(1024), null, {fastIdle:false});
  assert.throws(() => fast.nextDuty(), /no PWM for one emulated second/);
  assert.throws(() => slow.nextDuty(), /no PWM for one emulated second/);
  same(fast, slow);
});

test('invalid memory operations retain the error and state of the reference instruction', () => {
  for (const [word, pointer, value] of [[0x900d | (17 << 4), 26, 160],
    [0x9201 | (31 << 4), 30, 96], [0x9005 | (30 << 4), 30, 96],
    [0x9004 | (17 << 4), 30, 1024]]) {
    const fast = cpu([imm(0xe000, 16, 123), word]), slow = cpu([imm(0xe000, 16, 123), word]);
    for (const c of [fast, slow]) { c.r[pointer] = value & 255; c.r[pointer + 1] = value >> 8; }
    advance(fast, slow);
    assert.equal(fast.pc, 17); assert.equal(fast.runBlock(), false); same(fast, slow);
    assert.throws(() => fast.step()); assert.throws(() => slow.step()); same(fast, slow);
  }
});

const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
for (const entry of catalog.entries) test(`${entry.id}: all acceleration modes agree at every PWM write`, () => {
  const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
  const cores = [{fastIdle:false, fastBlocks:false}, {fastIdle:true, fastBlocks:false},
    {fastIdle:false, fastBlocks:true}, {fastIdle:true, fastBlocks:true}].map(options => new AVRCore(flash, ep, options));
  for (let i = 0; i < 37500; i++) {
    const expected = cores[0].nextDuty();
    for (const c of cores.slice(1)) { assert.equal(c.nextDuty(), expected); same(c, cores[0]); }
  }
  assert.equal(cores[0].blockInstructions, 0); assert.equal(cores[1].blockInstructions, 0);
  assert.ok(cores[2].blockInstructions > 1000); assert.ok(cores[3].blockInstructions > 1000);
});

test('instruction hooks disable blocks so firmware audits still observe every command', () => {
  const entry = catalog.entries[0], flash = parseHex(entry.flashHex), ep = parseHex(entry.eepromHex, 64);
  const hooked = new AVRCore(flash, ep), slow = new AVRCore(flash, ep, {fastBlocks:false});
  const original = hooked.step.bind(hooked); let calls = 0;
  hooked.step = () => { calls++; original(); };
  for (let i = 0; i < 1000; i++) { assert.equal(hooked.nextDuty(), slow.nextDuty()); same(hooked, slow); }
  assert.ok(calls > 1000); assert.equal(hooked.blockInstructions, 0);
});
