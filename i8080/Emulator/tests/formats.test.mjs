import test from 'node:test';
import assert from 'node:assert/strict';
import { parseIntelHex, validateBinary, processAudio, encodeWav } from '../formats.mjs';

const record = (type, address = 0, data = []) => {
  const bytes = [data.length, address >> 8, address & 255, type, ...data];
  bytes.push((-bytes.reduce((a, b) => a + b, 0)) & 255);
  return ':' + bytes.map(n => n.toString(16).padStart(2, '0')).join('').toUpperCase();
};
const eof = record(1);
test('Intel HEX: checksums, addressing, FF holes, EOF, accepted metadata', () => {
  assert.deepEqual([...parseIntelHex(record(0, 0, [0xfb, 0xf3, 0x76]) + '\n' + eof)], [0xfb, 0xf3, 0x76]);
  const data = parseIntelHex([record(2, 0, [0x01, 0x00]), record(0, 2, [0x76]), record(3, 0, [1, 2, 3, 4]), record(4, 0, [0, 0]), record(5, 0, [1, 2, 3, 4]), eof].join('\r\n'));
  assert.equal(data.length, 0x1003); assert.equal(data[0x1002], 0x76); assert.equal(data[0], 255);
  assert.equal(parseIntelHex('\uFEFF' + record(0, 65535, [0x76]) + '\n' + eof).length, 65536);
});
test('Malformed HEX fails instead of retaining the previous runnable image', () => {
  for (const text of [':010000007600\n' + eof, ':0100000076\n' + eof, ':0000000\n' + eof, record(0, 0, [1]), eof,
    record(1, 1), record(2, 0, [1]) + '\n' + eof, record(4, 1, [0, 0]) + '\n' + eof,
    record(4, 0, [0, 1]) + '\n' + record(0, 0, [1]) + '\n' + eof,
    record(0, 65535, [1, 2]) + '\n' + eof,
    record(0, 0, [1]) + '\n' + record(0, 0, [2]) + '\n' + eof,
    record(0, 0, [1]) + '\n' + eof + '\n' + record(0, 1, [2]),
    record(6) + '\n' + eof, record(3, 0, [1, 2, 3]) + '\n' + eof]) assert.throws(() => parseIntelHex(text), /HEX/);
  assert.deepEqual([...parseIntelHex([record(0, 0, [1]), record(0, 0, [1]), eof].join('\n'))], [1]);
  assert.throws(() => validateBinary(new Uint8Array(0)), /Размер/);
  assert.throws(() => validateBinary(new Uint8Array(65537)), /Размер/);
  assert.equal(validateBinary(new Uint8Array(65536)).length, 65536);
});
test('Audio: DC removal, finite silence, optional normalization, RC attenuation', () => {
  assert.deepEqual([...processAudio(new Float32Array(100).fill(1), 96000)], Array(100).fill(0));
  const signal = Float32Array.from({ length: 9600 }, (_, i) => 0.5 + 0.2 * Math.sin(i * 2 * Math.PI * 20000 / 96000));
  const raw = signal.slice(), pass = processAudio(signal, 96000, 0, 1, false), filtered = processAudio(signal, 96000, 4500, 4, false);
  const energy = x => x.slice(1000).reduce((sum, v) => sum + v * v, 0);
  assert.ok(energy(filtered) < energy(pass) / 100); assert.deepEqual(signal, raw);
  const normalized = processAudio(signal, 96000, 0, 1, true);
  assert.ok(Math.max(...normalized) > 0.8 && Math.max(...normalized) <= 0.851);
  assert.throws(() => processAudio([NaN], 96000), /Non-finite/);
  assert.throws(() => processAudio([0], 96000, 96000), /Invalid/);
});
test('WAV: mono PCM16, actual sample rate, clipping and negative full scale', () => {
  const wav = encodeWav(Float32Array.of(-2, -1, 0, 1, 2), 96000), view = new DataView(wav);
  assert.equal(new TextDecoder().decode(new Uint8Array(wav, 0, 4)), 'RIFF');
  assert.equal(view.getUint32(4, true), wav.byteLength - 8); assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 96000); assert.equal(view.getUint16(34, true), 16); assert.equal(view.getUint32(40, true), 10);
  assert.deepEqual(Array.from({ length: 5 }, (_, i) => view.getInt16(44 + i * 2, true)), [-32768, -32768, 0, 32767, 32767]);
  assert.throws(() => encodeWav([NaN], 96000), /Non-finite/);
});
