import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { parseIntelHex } from '../../Emulator/formats.mjs';
import { cReference } from './reference.mjs';
import { auditAll } from './audit.mjs';

const read = name => readFileSync(new URL(name, import.meta.url));
const rom = read('dualcrc-voice32.bin'), meta = JSON.parse(read('dualcrc-voice32.json'));

function crc(bytes, polynomial) {
  let value = 0;
  for (const byte of bytes) {
    value ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) value = ((value << 1) ^ (value & 0x8000 ? polynomial : 0)) & 65535;
  }
  return value;
}

test('32K image, HEX, eight dual CRC residues, all physical address signatures and retained packed samples', () => {
  assert.equal(rom.length, 32768);
  assert.equal(createHash('sha256').update(rom).digest('hex'), meta.sha256);
  assert.deepEqual(parseIntelHex(read('dualcrc-voice32.hex').toString()), new Uint8Array(rom));
  for (let bank = 0; bank < 8; bank++) for (const polynomial of [7, 9])
    assert.equal(crc(rom.subarray(bank*4096, (bank+1)*4096), polynomial), 0);
  for (let bit = 0; bit < 15; bit++) {
    assert.notEqual(rom[0], rom[1 << bit]);
    assert.notEqual(rom[32767], rom[32767 ^ (1 << bit)]);
  }
  const extracted = [];
  for (const part of meta.segments) {
    assert.equal(rom[part.header], part.words & 255);
    assert.equal(rom.readUInt16LE(part.link), part.target);
    extracted.push(rom.subarray(part.data, part.data+part.words*2));
  }
  const packed = Buffer.from(JSON.parse(read('pcm4.json')).packed_hex, 'hex');
  assert.deepEqual(Buffer.concat(extracted), packed);
  assert.equal(createHash('sha256').update(packed).digest('hex'), JSON.parse(read('SOURCE.json')).packed_sha256);
});

test('All 64 kernels, all branch paths: two exact-width pulses, 109T periods, 218T/sample, no writes', () => {
  for (let phase = 0; phase < 4; phase++) for (let level = 0; level < 16; level++) {
    for (const variant of phase === 3 ? ['normal', 'wrap256', 'link', 'eof'] : ['normal']) {
      const memory = new Uint8Array(rom), edges = [];
      memory.set([0xc2, 0x39], 0x6000);
      if (variant === 'link') { memory.set([0x20, 0x61], 0x6000); memory.set([3, 0, 0xc2, 0x39], 0x6120); }
      if (variant === 'eof') memory.set([0, 0], 0x6000);
      const bus = { level: 0, advance() {}, edge(value, t) {
        if (value !== this.level) { this.level = value; edges.push([t, value]); }
      } };
      const cpu = new CPU8080(memory, { pc: parseInt(meta.labels[`P${phase}_L${level}`], 16), sp: 0x6000, audio: bus });
      cpu.setpair(0, 0xa5e7);
      cpu.r[3] = variant === 'wrap256' ? 0 : ['link', 'eof'].includes(variant) ? 1 : 2;
      const nextPhase = (phase+1)%4, nextLevel = [14, 5, 10, 2][phase];
      const destination = parseInt(meta.labels[`P${nextPhase}_L${nextLevel}`], 16);
      while (!cpu.halted && cpu.pc !== destination && cpu.count < 150) cpu.step();
      assert.equal(cpu.t, 218, `${phase}/${level}/${variant}`);
      assert.equal(cpu.memWrites, 0); assert.equal(cpu.inte, 0);
      assert.deepEqual(edges, [[4, 1], [8+4*level, 0], [113, 1], [117+4*level, 0]]);
      assert.equal(cpu.halted, variant === 'eof');
      if (!cpu.halted) assert.equal(cpu.pc, destination);
      if (phase < 3) { assert.equal(cpu.pair(0), 0xa5e7); assert.equal(cpu.sp, 0x6000); }
      else if (variant !== 'eof') {
        assert.equal(cpu.pair(0), 0x39c2);
        assert.equal(cpu.sp, variant === 'link' ? 0x6124 : 0x6002);
        assert.equal(cpu.r[3], variant === 'link' ? 3 : variant === 'wrap256' ? 255 : 1);
      }
    }
  }
});

test('Portable C for all packed byte values; ASM availability requires both CPU and explicit enable', async () => {
  for (const [index, defines] of [[], ['__8080=1'], ['MICROMUSIC_ENABLE_I8080_ASM=1'],
    ['__8080=1', 'MICROMUSIC_ENABLE_I8080_ASM=1']].entries()) {
    const { api } = await cReference({ defines, suffix: '-gate'+index });
    assert.equal(api.asm_enabled(), +(index === 3));
    for (let byte = 0; byte < 256; byte++) for (let half = 0; half < 2; half++) {
      const level = (byte >> (half*4)) & 15;
      assert.equal(api.nibble(byte, half), level);
      assert.equal(api.width(level), 4+4*level);
    }
  }
});

test('Full execution matches C for every source sample twice, unchanged diagnostics/ramp, all eight bank faults', async () => {
  assert.deepEqual(await auditAll(), JSON.parse(read('AUDIT.json')));
});
