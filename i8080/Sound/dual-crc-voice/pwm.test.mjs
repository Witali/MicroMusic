import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { auditAll } from './audit.mjs';

// Independent bit-serial reference, deliberately different from build.py's LUT.
function crc(bytes, polynomial) {
  let state = 0;
  for (const byte of bytes) {
    state ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) state = ((state << 1) ^ (state & 0x8000 ? polynomial : 0)) & 65535;
  }
  return state;
}

for (const period of [159, 152]) {
  const root = new URL('./', import.meta.url);
  const rom = readFileSync(new URL(`dualcrc-uniform${period}.bin`, root));
  const meta = JSON.parse(readFileSync(new URL(`dualcrc-uniform${period}.json`, root)));
  test(`${period}T: complete 32K ROM, eight independent dual-CRC residues and intact physical address signatures`, () => {
    assert.equal(rom.length, 32768);
    assert.equal(createHash('sha256').update(rom).digest('hex'), meta.sha256);
    for (let bank = 0; bank < 8; bank++) for (const poly of [7, 9]) assert.equal(crc(rom.subarray(bank * 4096, (bank + 1) * 4096), poly), 0);
    for (let bit = 0; bit < 15; bit++) {
      assert.notEqual(rom[0], rom[1 << bit]);
      assert.notEqual(rom[32767], rom[32767 ^ (1 << bit)]);
    }
  });
  test(`${period}T: every PWM kernel and level, including ROM links and EOF, takes 78T and retains exact width`, () => {
    for (let phase = 0; phase < 6; phase++) for (let level = 0; level < 16; level++) for (const target of phase === 5 ? [0, 0x2134] : [0x2134]) {
      const memory = new Uint8Array(rom), events = [];
      memory[0x3000] = target & 255; memory[0x3001] = target >> 8;
      const bus = { level: 0, advance() {}, edge(value, t) { if (value !== this.level) { this.level = value; events.push([t, value]); } } };
      const pc = parseInt(meta.labels[`WIDTH_${phase}_${level}`], 16);
      const after = parseInt(meta.labels[`AFTER_${Math.min(phase, 4)}`], 16);
      const cpu = new CPU8080(memory, { pc, sp: 0x3000, mode: 'inte', audio: bus });
      cpu.r[2] = level * 4; cpu.r[0] = 0x80;
      cpu.r[4] = phase === 4 ? 0x1d : phase === 5 ? 0x1e : 0x1c;
      while (cpu.pc !== after && cpu.count < 100) cpu.step();
      assert.equal(cpu.pc, after); assert.equal(cpu.t, 78);
      assert.deepEqual(events, [[4, 1], [8 + level * 4, 0]]);
      assert.equal(cpu.r[2], level * 4); assert.equal(cpu.memWrites, 0);
      if (phase === 3) assert.equal(cpu.f.s, 1);
      if (phase >= 4) { assert.equal(cpu.r[4], 0x1c); assert.equal(cpu.f.z, +(phase === 5 && target === 0)); }
      if (phase === 5) assert.equal(cpu.sp, target);
    }
  });
}

test('Full execution: all 63,085 source widths, every inter-frame period, diagnostics, ramp and eight corruption cases', () => {
  const result = auditAll();
  const saved = JSON.parse(readFileSync(new URL('AUDIT.json', import.meta.url)));
  assert.deepEqual(result, saved);
});
