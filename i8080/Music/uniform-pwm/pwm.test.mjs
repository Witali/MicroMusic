import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { parseIntelHex } from '../../Emulator/formats.mjs';
import { auditAll } from './audit.mjs';
import { cReference } from './reference.mjs';

const root = new URL('./', import.meta.url);
const read = name => readFileSync(new URL(name, root));
const meta = JSON.parse(read('uniform26-pwm108.json'));

test('All 80 kernels: fixed edges and periods, phase carry/reset, record boundaries, EOF, no RAM writes', () => {
  for (let phase = 0; phase < 5; phase++) for (let level = 0; level < 16; level++) {
    const cases = phase < 2 ? [1, 0x7123, 0xfeff, 0xff00] : phase === 2 ? [2, 1, 0] : [2];
    for (const variant of cases) {
      const memory = new Uint8Array(read('uniform26-pwm108.bin')), edges = [];
      const at = phase < 2 ? 0x3000 : 0x3004;
      memory[at] = variant & 255; memory[at+1] = variant >> 8;
      const bus = { level: 0, advance() {}, edge(value, t) {
        if (this.level !== value) { this.level = value; edges.push([t, value]); }
      } };
      const cpu = new CPU8080(memory, { pc: parseInt(meta.labels[`P${phase}_L${level}`], 16), sp: at, audio: bus });
      cpu.setpair(0, 0xfffe); cpu.setpair(1, 0xabcd);
      cpu.setpair(2, (0x10+phase)*256+level*16);
      cpu.r[7] = phase === 2 ? variant === 2 ? 2 : 1 : 2;
      let nextPhase = phase+1, nextLevel = level;
      if (phase === 2 && variant === 0) nextPhase = 4;
      if (phase === 3) { nextPhase = 0; nextLevel = (0xff+0xab) >> 5; }
      const destination = (0x10+nextPhase)*256+nextLevel*16;
      while (!cpu.halted && cpu.pc !== destination && cpu.count < 100) cpu.step();
      assert.equal(cpu.t, 108, `phase ${phase}, level ${level}, case ${variant}`);
      assert.equal(cpu.memWrites, 0); assert.equal(cpu.inte, 0);
      assert.deepEqual(edges, level ? [[4, 1], [4+level*4, 0]] : []);
      if (phase < 2) {
        const initial = phase ? 0xabcd : 0xfffe;
        assert.equal(cpu.pair(phase), variant === 0xff00 ? 0x8000 : (initial+variant)&65535);
        assert.equal(cpu.r[7], 2); assert.equal(cpu.sp, 0x3002);
      } else if (phase === 2) {
        assert.equal(cpu.sp, variant === 2 ? 0x3000 : 0x3006);
        assert.equal(cpu.r[7], variant === 2 ? 1 : variant);
      } else if (phase === 3) assert.equal(cpu.r[7], 2);
      else assert.equal(cpu.halted, true);
    }
  }
});

test('Portable C stays selectable on 8080; assembly availability requires the real CPU macro and explicit opt-in', async () => {
  const configurations = [[], ['__8080=1'], ['MICROMUSIC_ENABLE_I8080_ASM=1'],
    ['__8080=1', 'MICROMUSIC_ENABLE_I8080_ASM=1']];
  for (const [index, defines] of configurations.entries()) {
    // These are preprocessor fixtures, not a claim to have cross-compiled C for 8080.
    const { api } = await cReference({ defines, suffix: '-gate'+index });
    assert.equal(api.asm_enabled(), +(index === 3));
    api.reset();
    let bc = 0, de = 0, level = 0, random = 0x12345678;
    for (let i = 0; i < 10000; i++) {
      random = (Math.imul(random, 1664525)+1013904223) >>> 0;
      const steps = [i%17 === 0 ? 0xff00 : random & 65535, i%29 === 0 ? 0xff00 : random >>> 16];
      assert.equal(api.frame(...steps), level);
      bc = steps[0] === 0xff00 ? 0x8000 : (bc+steps[0])&65535;
      de = steps[1] === 0xff00 ? 0x8000 : (de+steps[1])&65535;
      level = ((bc >>> 8)+(de >>> 8)) >>> 5;
      assert.equal(api.phase_bc(), bc); assert.equal(api.phase_de(), de);
    }
  }
});

test('Intel HEX contains the complete same 32K ROM', () => {
  for (const name of ['uniform26-pwm108', 'balanced27-pwm108'])
    assert.deepEqual(parseIntelHex(read(name+'.hex').toString()), new Uint8Array(read(name+'.bin')));
});

test('Both complete original scores and new ROMs agree with the compiled C fallback, including every PWM slot', async () => {
  assert.deepEqual(await auditAll(), JSON.parse(read('AUDIT.json')));
});
