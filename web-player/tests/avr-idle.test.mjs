import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';
import { parseHex } from '../lib/hex.js';

const rr = (op, d, s) => op | (d << 4) | (s & 15) | ((s & 16) << 5);
const imm = (op, d, k) => op | ((d - 16) << 4) | (k & 15) | ((k & 240) << 4);
const out = (a, d) => 0xb800 | (d << 4) | (a & 15) | ((a & 48) << 5);
const loop = [rr(0x2c00, 16, 22), rr(0x1800, 16, 28),
  imm(0x7000, 16, 15), imm(0x3000, 16, 13), 0xf400 | (123 << 3)];

function cpu(words, start = 8, options) {
  const binary = new Uint8Array(1024);
  for (let i = 0; i < words.length; i++) {
    const p = ((start + i) & 511) * 2;
    binary[p] = words[i]; binary[p + 1] = words[i] >> 8;
  }
  const core = new AVRCore(binary, null, options);
  core.pc = start; core.r[22] = 142; core.r[28] = 128;
  return core;
}

function sameState(fast, slow) {
  assert.deepEqual(fast.data, slow.data);
  assert.deepEqual(fast.irqFrames, slow.irqFrames);
  for (const key of ['pc', 'cyc', 'duty', 'writes', 'overflowAt', 'prescalerAt',
    'irqDelay', 'irqCount', 'irqStart', 'inIRQ', 'lost', 'workLost', 'maxIRQ', 'minSP']) {
    assert.equal(fast[key], slow[key], key);
  }
}

test('RJMP and BRTC self-loops retain exact IRQ timing and honor the T flag', () => {
  for (const word of [0xcfff, 0xf7fe]) for (const t of [0, 1]) for (const phase of [0, 1]) {
    const fast = cpu([word, out(0x29, 16)]), slow = cpu([word, out(0x29, 16)], 8, {fastIdle:false});
    for (const core of [fast, slow]) {
      core.rom[6] = out(0x29, 16) & 255; core.rom[7] = out(0x29, 16) >> 8; core.decode(3);
      core.clock(phase); core.writeIO(0x33, 1); core.writeIO(0x39, 2); core.i = 1; core.t = t;
    }
    assert.equal(fast.nextDuty(), slow.nextDuty());
    sameState(fast, slow);
    assert.equal(fast.idleCycles > 0, word === 0xcfff || !t);
  }
});

test('buffer polling preserves partial instructions at every Timer0/IRQ alignment', () => {
  for (const start of [8, 509]) for (const source of [1, 2, 3, 4, 5]) for (const mode of [0, 3]) {
    for (const phase of [0, 1, 2, 3, 4, 5, 6, 7, 15, 31]) {
      const fast = cpu(loop, start), slow = cpu(loop, start, {fastIdle:false});
      for (const core of [fast, slow]) {
        // Interrupt vector: OUT OCR0B, r16. Observe tmp before the ISR changes it.
        core.rom[6] = out(0x29, 16) & 255; core.rom[7] = out(0x29, 16) >> 8; core.decode(3);
        core.clock(phase); core.writeIO(0x2f, mode);
        core.writeIO(0x33, source); core.writeIO(0x32, 192 + phase);
        core.writeIO(0x39, 2); core.sreg = 0xc0;
        core.writeIO(0x1c, 4); core.writeIO(0x26, 128);
      }
      assert.equal(fast.idle[start], 3);
      assert.equal(fast.nextDuty(), slow.nextDuty());
      sameState(fast, slow);
      assert.ok(fast.idleCycles > 0);
    }
  }
});

test('polling skips complete laps and reproduces every subtraction/compare flag', () => {
  for (let a = 0; a < 256; a++) for (const b of [0, 1, 128, 255]) {
    for (const flags of [0x80, 0xff]) {
      const fast = cpu(loop), slow = cpu(loop);
      for (const core of [fast, slow]) {
        core.r[22] = a; core.r[28] = b; core.sreg = flags;
        core.writeIO(0x33, 1); core.writeIO(0x39, 2);
      }
      const waiting = ((a - b) & 15) >= 13;
      assert.equal(fast.skipIdle(), waiting);
      if (waiting) while (slow.cyc < fast.cyc) slow.step();
      sameState(fast, slow);
    }
  }
});

test('polling falls back with pending, masked, delayed or disabled interrupts', () => {
  for (const change of [c => c.pending = true, c => c.i = 0,
    c => c.irqDelay = 1, c => c.writeIO(0x39, 0), c => c.writeIO(0x33, 0)]) {
    const fast = cpu(loop), slow = cpu(loop);
    for (const core of [fast, slow]) {
      core.writeIO(0x33, 1); core.writeIO(0x39, 2); core.i = 1; change(core);
    }
    assert.equal(fast.skipIdle(), false);
    sameState(fast, slow);
  }
});

test('self-dependent loops and changed instructions cannot retain polling acceleration', () => {
  for (const word of [rr(0x2c00, 16, 16), rr(0x1800, 16, 16),
    imm(0x7000, 17, 15), imm(0x3000, 17, 13), 0xf400 | (122 << 3)]) {
    const core = cpu(loop, 509);
    const offset = word === rr(0x2c00, 16, 16) ? 0 : word === rr(0x1800, 16, 16) ? 1 :
      word === imm(0x7000, 17, 15) ? 2 : word === imm(0x3000, 17, 13) ? 3 : 4;
    const p = (509 + offset) & 511;
    core.rom[p * 2] = word; core.rom[p * 2 + 1] = word >> 8; core.decode(p);
    assert.equal(core.idle[509], 0);
    core.rom[p * 2] = loop[offset]; core.rom[p * 2 + 1] = loop[offset] >> 8; core.decode(p);
    assert.equal(core.idle[509], 3);
  }
});

const catalog = JSON.parse(readFileSync(new URL('../firmware.json', import.meta.url)));
for (const entry of catalog.entries) test(`${entry.id}: accelerated polling matches every PWM boundary`, () => {
  const flash = parseHex(entry.flashHex), ep = entry.eepromHex ? parseHex(entry.eepromHex, 64) : null;
  const fast = new AVRCore(flash, ep), slow = new AVRCore(flash, ep, {fastIdle:false});
  for (let i = 0; i < 37500; i++) {
    assert.equal(fast.nextDuty(), slow.nextDuty());
    sameState(fast, slow);
  }
  assert.ok(fast.idleCycles > 0);
});
