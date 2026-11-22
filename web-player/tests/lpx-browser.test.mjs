import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createDecoder, parseHeader, encodeWav } from '../lpx/codec.js';
import { createEncoder } from '../lpx/encoder.js';

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
  assert.throws(() => encode(new Int16Array(32000001), 8000, 6));
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
test('short encodes retain the original byte-exact V9 representation', () => {
  const hashes = ['fa5f6b2d1aa14dbc9da1a78216cfd8c19e57b94a6d3984dd7f38cab759896948',
    '987ffbd09bade2493db4a955bf0b35e7b3544a01ddbc2c6a2027e32551e75637',
    '60600f86c70d17b5a835e545b50669378c4bb3a85eb4021fb0e59be8b4af7aa8',
    '0336fad908dbc2f83cef70492e88d615aeed58ceddc0d1648b3fed1079e7020b'];
  let at = 0;
  for (const profile of [4, 6]) for (const length of [1, 321]) {
    const pcm = Int16Array.from({ length }, (_, i) => Math.round(8000 * Math.sin(i * .137) + 1500 * Math.sin(i * .317)));
    assert.equal(createHash('sha256').update(encode(pcm, 8000, profile)).digest('hex'), hashes[at++]);
  }
});
test('V9 Long promotion preserves all legacy profiles, extras and PCM at all three rates', () => {
  for (const item of cases) {
    const original = parseHeader(item.bytes), bytes = Buffer.alloc(item.bytes.length + 4);
    item.bytes.copy(bytes, 0, 0, 5); bytes[2] |= 64;
    bytes.writeUInt32LE(original.samples, 5); item.bytes.copy(bytes, 9, 7, 11);
    bytes.writeUInt32LE(item.bytes.length - 13, 13); item.bytes.copy(bytes, 17, 13);
    const result = decode(bytes);
    assert.ok(result.long); assert.deepEqual(result.pcm, decode(item.bytes).pcm);
    encodedCases.push({ name: `promoted ${item.name}`, bytes, rate: item.rate });
  }
});
test('long audio is encoded as one continuous stream across the old sample limits', () => {
  for (const profile of [4, 6]) {
    const length = profile === 4 ? 131073 : 65537;
    const pcm = Int16Array.from({ length }, (_, i) => Math.round(5000 * Math.sin(i * .14)));
    const bytes = encode(pcm, 12000, profile), result = decode(bytes);
    assert.ok(result.long); assert.equal(result.samples, length); assert.equal(result.pcm.length, length);
    assert.equal(bytes.readUInt32LE ? bytes.readUInt32LE(5) : new DataView(bytes.buffer).getUint32(5, true), length);
    encodedCases.push({ name: `continuous P${profile}`, bytes, rate: 12000 });
  }
});
test('wide payload sizes, full progress, strict final padding and allocation limits are validated', () => {
  const length = 1280001, payload = []; let bits = 0;
  const put = (value, count) => { for (let bit = 0; bit < count; bit++) { if (!(bits & 7)) payload.push(0); payload[bits >> 3] |= ((value >> bit) & 1) << (bits & 7); bits++; } };
  for (let frame = 0; frame * 320 < length; frame++) {
    put(frame === 0 ? 1 : 0, 1);
    if (frame === 0) { put(0, 1); for (let j = 0; j < 10; j++) { const value = j ? 5 : 3; put(0, value >> 2); put(1, 1); put(value & 3, 2); } }
    for (let half = 0; half < 2 && frame * 320 + half * 160 < length; half++) {
      put(0, 8);
      for (let packet = 0; packet < 4 && frame * 320 + half * 160 + packet * 40 < length; packet++) { put(0, 9); put(8, 4); put(8, 4); }
    }
  }
  const bytes = Buffer.alloc(17 + payload.length); bytes.write('L9'); bytes[2] = 64 | 6;
  bytes.writeUInt16LE(16000, 3); bytes.writeUInt32LE(length, 5); bytes.writeUInt16LE(13926, 9); bytes.writeUInt32LE(payload.length, 13); bytes.set(payload, 17);
  assert.ok(bytes.length > 65535); assert.deepEqual(decode(bytes).pcm, new Int16Array(length));
  encodedCases.push({ name: 'payload above 65535 bytes', bytes, rate: 16000 });
  const trailing = Buffer.concat([bytes, Buffer.from([0])]); trailing.writeUInt32LE(trailing.length - 17, 13); assert.throws(() => decode(trailing));
  const invalid = Buffer.from(bytes); invalid.writeUInt32LE(0xffffffff, 5); assert.throws(() => decode(invalid));
  invalid.writeUInt32LE(length, 5); invalid[invalid.length - 1] |= 128; assert.throws(() => decode(invalid));
  assert.ok(decode(readFileSync(clips[0])).pcm.length, 'small files still decode after large memory growth and failures');
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
test('the unchanged default C configuration still rejects V9 Long', { skip: !process.env.LPX_LEGACY_REFERENCE }, () => {
  const samples = encodedCases.filter(item => parseHeader(item.bytes).long);
  const input = Buffer.concat(samples.flatMap(item => { const size = Buffer.alloc(4); size.writeUInt32LE(item.bytes.length); return [size, item.bytes]; }));
  const result = spawnSync('wsl', ['-d', 'Ubuntu', '--', process.env.LPX_LEGACY_REFERENCE], { input });
  assert.equal(result.status, 0, result.stderr?.toString());
  assert.deepEqual(result.stdout, Buffer.alloc(samples.length * 4));
});
