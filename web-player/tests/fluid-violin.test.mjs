import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';

const root = new URL('../../ATtiny13A/Music/', import.meta.url);
const read = (folder, name) => readFileSync(new URL(`${folder}/${name}`, root));
const baseline = 'final/attiny13a_synth_release', variant = 'variants/fluid-violin';
const cpu = folder => new AVRCore(read(folder, 'synth.bin'), read(folder, 'eeprom.bin'));
function initialized(folder = variant) {
  const c = cpu(folder);
  while (c.irqCount < 30 || c.inIRQ) c.step();
  return c;
}
function tick(c) {
  c.r[15] = 255; c.r[23] = 255; c.r[22] = 255;
  const target = c.irqCount + 1;
  while (c.irqCount < target || c.inIRQ) c.step();
}

test('Fluid violin changes only the lead tables and reviewed attack words', () => {
  const ep = read(variant, 'eeprom.bin'), oldEp = read(baseline, 'eeprom.bin');
  assert.equal(ep.length, 64); assert.deepEqual(ep.subarray(16), oldEp.subarray(16));
  const waves = JSON.parse(read(variant, 'waveforms.json'));
  for (const [i, values] of Object.values(waves).entries()) {
    const decoded = Array.from(ep.subarray(i * 8, i * 8 + 8)).flatMap(b => [(b & 15) - 8, (b >> 4) - 8]);
    assert.deepEqual(decoded, values); assert.equal(decoded.reduce((a, b) => a + b), 0);
  }
  const rom = read(variant, 'synth.bin'), oldRom = read(baseline, 'synth.bin');
  const report = JSON.parse(read(variant, 'build-report.json'));
  assert.equal(rom.length, 1024);
  const patched = new Set(report.patches.flatMap(p => [p.address, p.address + 1]));
  for (let i = 0; i < rom.length; i++) if (!patched.has(i)) assert.equal(rom[i], oldRom[i], `Flash byte ${i}`);
  for (const name of ['score.inc', 'score.json', 'config.inc']) assert.deepEqual(read(variant, name), read(baseline, name));
});

test('lead attack takes twenty music ticks, saturates, and tapers on release', () => {
  for (let phase = 0; phase < 4; phase++) {
    const c = initialized(); c.r[1] = 128; c.r[24] = phase;
    for (let t = 1; t <= 28; t++) {
      tick(c);
      const increments = Array.from({length: t}, (_, i) => (phase + i + 1) % 4 !== 0).filter(Boolean).length;
      assert.equal(c.r[1], 128 + Math.min(15, increments));
      if (t === 20) assert.equal(c.r[1], 143);
    }
    c.r[1] &= 15;
    for (const level of [13, 11, 9, 7, 6, 5, 4, 3, 2, 1, 0, 0]) { tick(c); assert.equal(c.r[1], level); }
    assert.equal(c.lost, 0);
  }
});

test('legato and retriggered notes preserve level and DDS phase instead of creating gaps', () => {
  for (const level of [0, 1, 5, 8, 15, 128, 129, 133, 136, 143]) {
    const c = initialized();
    c.r[1] = level; c.r[2] = 25; c.r[3] = 173;
    c.r[30] = 0xf0; c.r[31] = 3; c.rom[0x3f0] = 0x39;
    c.pc = 0xc0 / 2; // Execute the real score decoder directly, before its RETI.
    let steps = 0;
    while (c.pc !== 324 / 2 && steps++ < 200) c.step();
    assert.ok(steps < 200);
    assert.equal(c.r[1], level | 128); assert.equal(c.r[2], 25); assert.equal(c.r[3], 173);
    assert.equal(c.r[4] | c.r[5] << 8, 0x050d);
  }
});

test('piano, guitar and drums produce unchanged PWM with the lead muted', () => {
  const old = initialized(baseline), updated = initialized();
  for (const c of [old, updated]) { c.r[1] = 0; c.r[22] = 255; }
  for (let i = 0; i < 3 * 37500; i++) assert.equal(updated.nextDuty(), old.nextDuty(), `PWM ${i}`);
});

test('new firmware retains all note-off masks and visits the complete score without IRQ loss', () => {
  function release(mask) {
    const c = initialized();
    c.r[1] = c.r[19] = c.r[20] = 143; c.r[21] = 0;
    c.r[22] = 1; c.r[15] = c.r[23] = 255;
    c.r[30] = 0xf0; c.r[31] = 3; c.rom[0x3f0] = 0xf0 | mask;
    let steps = 0;
    while (c.pc !== 0xe0 / 2 && steps++ < 1000) c.step();
    assert.ok(steps < 1000);
    return [c.r[1], c.r[19], c.r[20], c.r[21]];
  }
  const control = release(0);
  for (const [mask, index] of [[1, 0], [2, 1], [4, 2], [8, 3]]) {
    const regs = release(mask); assert.notEqual(regs[index], control[index]);
    for (let i = 0; i < 4; i++) if (i !== index) assert.equal(regs[i], control[i]);
  }
  const c = initialized(), sections = new Set(), tokens = new Set();
  for (let k = 0; k < 950; k++) {
    c.r[15] = c.r[23] = 255; c.r[22] = 1;
    const goal = c.irqCount + 4;
    while (c.irqCount < goal || c.inIRQ) {
      if (c.pc === 0xc0 / 2) tokens.add(c.rom[c.r[30] | c.r[31] << 8]);
      c.step();
    }
    sections.add(c.r[28]);
  }
  assert.equal(c.lost, 0); assert.ok(c.maxIRQ < 512, `${c.maxIRQ} ISR cycles`);
  for (let i = 0; i < 15; i++) assert.ok(sections.has(i));
  for (const token of [0xf2, 0xf4, 0xf6, 0xf8, 0xff]) assert.ok(tokens.has(token));
});
