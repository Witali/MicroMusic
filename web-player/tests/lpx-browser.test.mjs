import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createDecoder, parseHeader, encodeWav } from '../lpx/codec.js';
import { createEncoder } from '../lpx/encoder.js';
import { makeZip } from '../lpx/zip.js';

const root = new URL('../', import.meta.url);
const binary = readFileSync(new URL('lpx/decoder.wasm', root));
const decode = await createDecoder(binary);
const encode = await createEncoder(readFileSync(new URL('lpx/encoder.wasm', root)));
const encodedCases = [];
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
test('encoder provenance is current and the bounded WASM module has no host imports', () => {
  const manifest = JSON.parse(readFileSync(new URL('lpx/encoder-build.json', root)));
  const binary = readFileSync(new URL('lpx/encoder.wasm', root));
  const hash = data => createHash('sha256').update(data).digest('hex');
  assert.equal(hash(binary), manifest.sha256);
  for (const [path, expected] of Object.entries(manifest.inputs)) assert.equal(hash(readFileSync(new URL('../' + path, root), 'utf8').replaceAll('\r\n', '\n')), expected, path);
  assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)), []);
});
test('P4/P6 encoder validates exact C synthesis at packet boundaries and partial tails', () => {
  for (const profile of [4, 6]) for (const length of [1, 19, 20, 39, 40, 41, 159, 160, 161, 319, 320, 321]) {
    const pcm = Int16Array.from({ length }, (_, i) => Math.round(8000 * Math.sin(i * .137) + 1500 * Math.sin(i * .317)));
    const rate = [8000, 12000, 16000][length % 3];
    const bytes = encode(pcm, rate, profile), result = decode(bytes);
    assert.equal(result.samples, length); assert.equal(result.profile, profile); assert.equal(result.sampleRate, rate);
    encodedCases.push({ name: `encoded P${profile}/${length}`, bytes, rate });
  }
  assert.throws(() => encode(new Int16Array(), 8000, 6));
  assert.throws(() => encode(new Int16Array(64001), 8000, 6));
  assert.throws(() => encode(new Int16Array(1), 44100, 6));
});
test('encoder preserves full 64000-sample silence, and produces nonzero speech from a real decoded input', () => {
  for (const profile of [4, 6]) {
    const bytes = encode(new Int16Array(64000), 16000, profile);
    assert.deepEqual(decode(bytes).pcm, new Int16Array(64000));
    encodedCases.push({ name: `64000 silent P${profile}`, bytes, rate: 16000 });
  }
  const pcm = decode(readFileSync(new URL('audio/lpx-speech/chego/quality.v9.lpx', root))).pcm;
  const bytes = encode(pcm, 8000, 6), actual = decode(bytes).pcm;
  let energy = 0, signal = 0, error = 0;
  for (let i = 0; i < pcm.length; i++) { energy += actual[i] ** 2; signal += pcm[i] ** 2; error += (pcm[i] - actual[i]) ** 2; }
  assert.ok(energy > 0); assert.ok(error < signal, 'speech reconstruction beats silent output without gain fitting');
  encodedCases.push({ name: 'reencoded speech P6', bytes, rate: 8000 });
});
test('ZIP retains UTF-8 names, payloads, directory offsets, and manifest', async () => {
  const files = [{ name: 'звук-0001.lpx', bytes: new Uint8Array([1, 2, 3]) }, { name: 'playlist.json', bytes: new TextEncoder().encode('{}') }];
  const bytes = Buffer.from(await makeZip(files).arrayBuffer());
  let offset = 0;
  for (const file of files) {
    assert.equal(bytes.readUInt32LE(offset), 0x04034b50); assert.equal(bytes.readUInt16LE(offset + 6), 0x800);
    const size = bytes.readUInt32LE(offset + 18), nameSize = bytes.readUInt16LE(offset + 26);
    assert.equal(bytes.toString('utf8', offset + 30, offset + 30 + nameSize), file.name);
    assert.deepEqual(bytes.subarray(offset + 30 + nameSize, offset + 30 + nameSize + size), Buffer.from(file.bytes));
    offset += 30 + nameSize + size;
  }
  assert.equal(bytes.readUInt32LE(offset), 0x02014b50);
  assert.equal(bytes.readUInt32LE(bytes.length - 22), 0x06054b50);
  assert.equal(bytes.readUInt32LE(bytes.length - 6), offset);
});
test('WASM PCM matches independent native C reference for the full rate matrix', { skip: !process.env.LPX_WSL_REFERENCE }, () => {
  const allCases = [...cases, ...encodedCases];
  const input = Buffer.concat(allCases.flatMap(item => { const size = Buffer.alloc(4); size.writeUInt32LE(item.bytes.length); return [size, item.bytes]; }));
  const result = spawnSync('wsl', ['-d', 'Ubuntu', '--', process.env.LPX_WSL_REFERENCE], { input, maxBuffer: 32 * 1024 * 1024 });
  assert.equal(result.status, 0, result.stderr?.toString());
  let offset = 0;
  for (const item of allCases) {
    const size = result.stdout.readUInt32LE(offset); offset += 4;
    assert.equal(size, parseHeader(item.bytes).samples * 2);
    const pcm = decode(item.bytes).pcm;
    assert.deepEqual(Buffer.from(pcm.buffer), result.stdout.subarray(offset, offset + size), `${item.name} @ ${item.rate}`);
    offset += size;
  }
  assert.equal(offset, result.stdout.length);
});
