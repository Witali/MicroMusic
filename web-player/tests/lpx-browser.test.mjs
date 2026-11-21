import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createDecoder, parseHeader, encodeWav } from '../lpx/codec.js';

const root = new URL('../', import.meta.url);
const binary = readFileSync(new URL('lpx/decoder.wasm', root));
const decode = await createDecoder(binary);
function corpus(folder) {
  return readdirSync(folder, { withFileTypes: true }).flatMap(entry => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), folder);
    return entry.isDirectory() ? corpus(url) : entry.name.endsWith('.v9.lpx') ? [url] : [];
  });
}
const clips = ['audio/lpx-speech/', 'audio/lpx-bread/', 'audio/lpx-dialogue/'].flatMap(path => corpus(new URL(path, root)));
const cases = clips.flatMap(path => [8000, 12000, 16000].map(rate => {
  const bytes = Buffer.from(readFileSync(path)); bytes.writeUInt16LE(rate, 3);
  return { name: fileURLToPath(path), bytes, rate };
}));
test('C/WASM build provenance matches current sources and contains no imports', () => {
  const manifest = JSON.parse(readFileSync(new URL('lpx/build.json', root)));
  const hash = data => createHash('sha256').update(data).digest('hex');
  assert.equal(hash(binary), manifest.sha256);
  for (const [path, expected] of Object.entries(manifest.inputs)) {
    assert.equal(hash(readFileSync(new URL('../' + path, root), 'utf8').replaceAll('\r\n', '\n')), expected, path);
  }
  assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)), []);
});
test('all retained V9 samples decode at 8/12/16 kHz with identical PCM', () => {
  assert.ok(clips.length >= 10);
  const profiles = new Set();
  for (const path of clips) {
    const original = Buffer.from(readFileSync(path)), expected = decode(original).pcm;
    for (const rate of [8000, 12000, 16000]) {
      const bytes = Buffer.from(original); bytes.writeUInt16LE(rate, 3);
      const result = decode(bytes); profiles.add(result.profile);
      assert.equal(result.sampleRate, rate); assert.deepEqual(result.pcm, expected);
      assert.equal(result.pcm.length, result.samples);
    }
  }
  assert.deepEqual([...profiles].sort((a, b) => a - b), [4, 6, 15]);
});
test('strictly rejects wrong version, malformed headers, truncation, and trailing payload', () => {
  const original = Buffer.from(readFileSync(clips[0]));
  const invalid = [Buffer.alloc(0), Buffer.alloc(65536), original.subarray(0, 12), original.subarray(0, -1)];
  for (const [offset, value] of [[0, 0], [2, 15 | 128], [3, 1], [5, 0], [5, 64001], [7, 16385], [9, 11470]]) {
    const bytes = Buffer.from(original);
    if (offset < 3) bytes[offset] = value; else bytes.writeUInt16LE(value, offset);
    invalid.push(bytes);
  }
  const trailing = Buffer.concat([original, Buffer.from([0])]); trailing.writeUInt16LE(trailing.length - 13, 11); invalid.push(trailing);
  const truncated = original.subarray(0, -1); truncated.writeUInt16LE(truncated.length - 13, 11); invalid.push(truncated);
  invalid.forEach(bytes => assert.throws(() => decode(bytes)));
  assert.ok(decode(readFileSync(clips[0])).pcm.length, 'valid file still works after failures');
});
test('PCM16 WAV export preserves sample values, rate and channel count', () => {
  for (const rate of [8000, 12000, 16000]) {
    const pcm = new Int16Array([-32768, -123, 0, 32767]);
    const wav = Buffer.from(encodeWav(pcm, rate));
    assert.equal(wav.toString('ascii', 0, 4), 'RIFF'); assert.equal(wav.readUInt32LE(24), rate);
    assert.equal(wav.readUInt16LE(22), 1); assert.equal(wav.readUInt16LE(34), 16);
    assert.deepEqual(wav.subarray(44), Buffer.from(pcm.buffer));
  }
});
test('WASM PCM matches independent native C reference for the full rate matrix', { skip: !process.env.LPX_WSL_REFERENCE }, () => {
  const input = Buffer.concat(cases.flatMap(item => { const size = Buffer.alloc(4); size.writeUInt32LE(item.bytes.length); return [size, item.bytes]; }));
  const result = spawnSync('wsl', ['-d', 'Ubuntu', '--', process.env.LPX_WSL_REFERENCE], { input, maxBuffer: 32 * 1024 * 1024 });
  assert.equal(result.status, 0, result.stderr?.toString());
  let offset = 0;
  for (const item of cases) {
    const size = result.stdout.readUInt32LE(offset); offset += 4;
    assert.equal(size, parseHeader(item.bytes).samples * 2);
    const pcm = decode(item.bytes).pcm;
    assert.deepEqual(Buffer.from(pcm.buffer), result.stdout.subarray(offset, offset + size), `${item.name} @ ${item.rate}`);
    offset += size;
  }
  assert.equal(offset, result.stdout.length);
});
