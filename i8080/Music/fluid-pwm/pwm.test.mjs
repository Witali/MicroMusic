import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { parseIntelHex } from '../../Emulator/formats.mjs';
import { cReference } from './reference.mjs';
import { auditAll } from './audit.mjs';
const read = name => readFileSync(new URL(name, import.meta.url));
const bank = JSON.parse(read('bank.json')), meta = JSON.parse(read('uniform26-fluid-pwm108.json'));
const entry = (phase, level) => parseInt(meta.labels[`P${phase}_L${level}`], 16);
const mix = (a, b) => Math.max(0, Math.min(15, Math.floor(((a+b-meta.mix_minimum_sum)*15+(meta.mix_maximum_sum-meta.mix_minimum_sum)/2)/(meta.mix_maximum_sum-meta.mix_minimum_sum))));

test('FluidR3 provenance, 256-point source waves, original capture hashes, complete 32K ROM/HEX and bank bounds', () => {
  const sources = JSON.parse(read('SOURCE.json'));
  assert.equal(sources.soundfont_sha256, '74594e8f4250680adf590507a306655a299935343583256f3b722c48a1bc1cb0');
  assert.match(read('FluidR3-MIT.txt').toString(), /Permission is hereby granted/);
  for (const source of sources.sources) {
    assert.equal(createHash('sha256').update(read(source.file)).digest('hex'), source.sha256);
    assert.equal(read(source.file).readUInt32LE(24), 48000);
  }
  for (const item of bank.banks) for (const wave of item.waves) {
    assert.equal(wave.length, 256); assert.equal(wave[0], 8);
    assert.ok(wave.every(q => Number.isInteger(q) && q >= 0 && q <= 15));
  }
  for (const name of ['uniform26-fluid-pwm108', 'balanced27-fluid-pwm108']) {
    const rom = read(name+'.bin'), m = JSON.parse(read(name+'.json'));
    assert.equal(rom.length, 32768); assert.ok(m.used_bytes <= 32768);
    assert.equal(createHash('sha256').update(rom).digest('hex'), m.sha256);
    assert.deepEqual(parseIntelHex(read(name+'.hex').toString()), new Uint8Array(rom));
    assert.ok(m.score_at+m.score_bytes <= m.bank_at);
    assert.equal(m.bank_at+m.bank_bytes, m.used_bytes);
  }
});

test('All 80 Fluid kernels: exact 108T slots and widths, carry/reset, chunk transitions and EOF, no RAM writes', () => {
  const rom = read('uniform26-fluid-pwm108.bin');
  for (let phase = 0; phase < 5; phase++) for (let level = 0; level < 16; level++) {
    const variants = phase < 2 ? [1, 0x7123, 0xfeff, 0xff00] : phase === 2 ? [1, 2] : phase === 4 ? [0, 2] : [2];
    for (const value of variants) {
      const memory = new Uint8Array(rom), edges = [];
      memory.set([phase < 2 ? value & 255 : value, phase < 2 ? value >> 8 : meta.first_wave_page], 0x7f00);
      const bus = { level: 0, advance() {}, edge(v, t) { if (v !== this.level) { this.level = v; edges.push([t, v]); } } };
      const c = new CPU8080(memory, { pc: entry(phase, level), sp: phase === 2 ? 0x7f06 : 0x7f00, audio: bus });
      c.setpair(0, 0xfffe); c.setpair(1, 0xabcd); c.r[7] = phase === 2 ? value : 2;
      const next = phase < 2 ? phase+1 : phase === 2 ? value === 1 ? 4 : 3 : 0;
      const nextLevel = phase >= 3 ? mix(bank.banks[0].waves[0][255], bank.banks[2].waves[0][0xab]) : level;
      const destination = entry(next, nextLevel);
      while (!c.halted && c.pc !== destination && c.count < 150) c.step();
      assert.equal(c.t, 108, `${phase}/${level}/${value}`); assert.equal(c.memWrites, 0); assert.equal(c.inte, 0);
      assert.deepEqual(edges, level ? [[4, 1], [4+4*level, 0]] : []);
      assert.equal(c.halted, phase === 4 && value === 0);
      if (!c.halted) assert.equal(c.pc, destination);
      if (phase < 2) assert.equal(c.pair(phase), value === 0xff00 ? 0 : ((phase ? 0xabcd : 0xfffe)+value)&65535);
      if (phase === 2) assert.equal(c.sp, value === 1 ? 0x7f06 : 0x7f00);
      if (phase >= 3) assert.equal(c.sp, 0x7f02);
      if (phase === 4 && value) assert.equal(c.r[7], value);
    }
  }
});

test('Portable C remains the default on every target; explicit ASM gate and randomized phase/mix arithmetic', async () => {
  for (const [index, defines] of [[], ['__8080=1'], ['MICROMUSIC_ENABLE_I8080_ASM=1'],
    ['__8080=1', 'MICROMUSIC_ENABLE_I8080_ASM=1']].entries()) {
    const { api } = await cReference({ defines, suffix: '-gate'+index });
    assert.equal(api.asm_enabled(), +(index === 3));
    for (let a = 0; a < 16; a++) for (let b = 0; b < 16; b++) assert.equal(api.mix(a, b, 0, 30), Math.floor((a+b+1)/2));
    for (const [id, item] of bank.banks.entries()) for (const [stage, wave] of item.waves.entries())
      for (const [i, q] of wave.entries()) api.set_wave(id, stage, i, q);
    api.set_mix(0, 30); api.reset();
    let bc = 0, de = 0, level = 8, random = 1234567;
    for (let i = 0; i < 10000; i++) {
      random = (Math.imul(random, 1664525)+1013904223) >>> 0;
      const a = i%17 ? (random & 65535)%0xff00 : 0xff00, b = i%23 ? (random >>> 16)%0xff00 : 0xff00;
      const reg = i%2, stage = i%4, guitar = i%2;
      assert.equal(api.frame(a, b, reg, stage, guitar, 0), level);
      bc = a === 0xff00 ? 0 : (bc+a)&65535; de = b === 0xff00 ? 0 : (de+b)&65535;
      level = Math.floor((bank.banks[reg].waves[stage][bc>>8]+bank.banks[2].waves[guitar][de>>8]+1)/2);
      assert.equal(api.phase_bc(), bc); assert.equal(api.phase_de(), de);
    }
  }
});

test('Both complete FluidR3 ROMs match portable C at every sample, all PWM slots and score boundaries', async () => {
  assert.deepEqual(await auditAll(), JSON.parse(read('AUDIT.json')));
});
