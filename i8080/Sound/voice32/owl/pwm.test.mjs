import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseIntelHex } from '../../../Emulator/formats.mjs';
import { auditOwl } from './audit.mjs';
const read = name => readFileSync(new URL(name, import.meta.url));

test('Owl 32K ROM/HEX and every retained PCM nibble agree; direct reset, no diagnostic or CRC payload', () => {
  const rom = read('owl-voice32.bin'), meta = JSON.parse(read('owl-voice32.json'));
  assert.equal(rom.length, 32768); assert.equal(createHash('sha256').update(rom).digest('hex'), meta.sha256);
  assert.deepEqual(parseIntelHex(read('owl-voice32.hex').toString()), new Uint8Array(rom));
  assert.deepEqual([...rom.subarray(0, 3)], [0xc3, 0, 0x11]);
  assert.equal(meta.diagnostics, false); assert.equal(meta.soft_start, false);
  assert.equal(meta.address_tests, 0); assert.deepEqual(meta.footers, []);
  const parts = meta.segments.map(part => {
    assert.equal(rom[part.header], part.words & 255); assert.equal(rom.readUInt16LE(part.link), part.target);
    return rom.subarray(part.data, part.data+part.words*2);
  });
  assert.deepEqual(Buffer.concat(parts), Buffer.from(JSON.parse(read('pcm4.json')).packed_hex, 'hex'));
});

test('Owl starts without beeps or ramp and fully matches the portable C decoder at uniform 109T PWM', async () => {
  assert.deepEqual(await auditOwl(), JSON.parse(read('AUDIT.json')));
});

test('Owl independent instruction timing: all samples, 16 levels, segment links and 1552 branch cases', () => {
  execFileSync(process.execPath, [fileURLToPath(new URL('../timing-check.mjs', import.meta.url)), '--profile', 'owl', '--check']);
});
