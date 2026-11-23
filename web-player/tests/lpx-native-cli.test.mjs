import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
function removeTemporary(directory) {
  assert.ok(resolve(directory).startsWith(resolve(root, 'build') + sep));
  rmSync(directory, { recursive: true, force: true });
}
const suffix = process.platform === 'win32' ? '.exe' : '';
const native = process.env.LPX_NATIVE_ENCODER || join(root, `build/lpx-native/lpx-encode${suffix}`);
const cuda = process.env.LPX_CUDA_ENCODER || join(root, `build/lpx-native/lpx-encode-cuda${suffix}`);
const enabled = existsSync(native), gpu = enabled && existsSync(cuda);
const fast = await createEncoder(readFileSync(new URL('../lpx/encoder.wasm', import.meta.url)));
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
const { instance } = await WebAssembly.instantiate(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));
instance.exports.__wasm_call_ctors?.();
function adaptive(pcm, profile, rate = 8000, expanded = false, allowance = 0) {
  const a = instance.exports;
  assert.equal(a.enc_reserve(pcm.length), 1);
  new Int16Array(a.memory.buffer, a.enc_input(), pcm.length).set(pcm);
  const size = expanded ? a.enc_adaptive_extended(pcm.length, profile, rate, 0, 0, 4, allowance)
    : a.enc_adaptive(pcm.length, profile, rate, 0, 0, 4);
  assert.ok(size >= 13, `adaptive WASM returned ${size}`);
  return Buffer.from(new Uint8Array(a.memory.buffer, a.enc_adaptive_output(), size));
}
function run(executable, pcm, args = []) {
  return spawnSync(executable, args, { cwd: root, input: Buffer.from(pcm.buffer, pcm.byteOffset, pcm.byteLength), maxBuffer: 100 * 1024 * 1024 });
}
function success(executable, pcm, args) {
  const result = run(executable, pcm, args);
  assert.equal(result.status, 0, result.stderr?.toString());
  const report = JSON.parse(result.stderr.toString().trim());
  assert.equal(report.samples, pcm.length);
  assert.equal(report.bytes, result.stdout.length);
  return { bytes: result.stdout, report };
}
const signal = length => Int16Array.from({ length }, (_, i) => Math.round(15000 * Math.sin(i * .17) + 4000 * Math.sin(i * .051)));

test('native fast CLI matches the browser encoder and checks repeat determinism', { skip: !enabled }, () => {
  for (const profile of [4, 6]) for (const rate of [8000, 12000, 16000]) {
    const pcm = signal(641);
    const { bytes, report } = success(native, pcm, ['--profile', String(profile), '--rate', String(rate), '--quality', 'fast', '--repeat', '3']);
    assert.deepEqual(bytes, Buffer.from(fast(pcm, rate, profile)));
    assert.equal(report.backend, 'cpu'); assert.equal(report.quality, 'fast');
    assert.equal(report.repeatTimesMs.length, 3); assert.ok(report.warmMedianMs >= 0);
    assert.equal(report.encodingMs, report.repeatTimesMs[0]);
  }
});

test('native reference adaptive CLI uses the same Python-reference result as WASM', { skip: !enabled }, () => {
  const inputs = [new Int16Array(1), signal(161), signal(641)];
  for (const pcm of inputs) for (const profile of [4, 6]) {
    const { bytes, report } = success(native, pcm, ['--profile', String(profile), '--quality', 'adaptive', '--search', 'reference', '--repeat', '2']);
    assert.deepEqual(bytes, adaptive(pcm, profile));
    assert.equal(report.refinementCalls, 4); assert.ok(report.candidates >= 1);
    assert.equal(report.search, 'reference'); assert.equal(report.sizeAllowancePercent, 0);
  }
});

test('native default expanded search and size allowance match extended WASM in CPU/CUDA modes', { skip: !enabled }, () => {
  const pcm = signal(641);
  for (const profile of [4, 6]) for (const allowance of [0, 25]) {
    const args = ['--profile', String(profile), '--quality', 'adaptive', '--size-allowance', String(allowance), '--repeat', '2'];
    const expected = adaptive(pcm, profile, 8000, true, allowance);
    const cpu = success(native, pcm, args);
    assert.deepEqual(cpu.bytes, expected);
    assert.equal(cpu.report.search, 'expanded'); assert.equal(cpu.report.sizeAllowancePercent, allowance);
    assert.ok(cpu.report.expandedAccepted >= 0);
    const explicit = success(native, pcm, [...args, '--search', 'expanded']);
    assert.deepEqual(explicit.bytes, expected);
    if (gpu) {
      const accelerated = success(cuda, pcm, [...args, '--backend', 'cuda']);
      assert.deepEqual(accelerated.bytes, expected); assert.equal(accelerated.report.search, 'expanded');
    }
  }
});

test('CUDA executable keeps explicitly selectable CPU and identical CPU/CUDA bytes', { skip: !gpu }, () => {
  for (const profile of [4, 6]) for (const quality of ['fast', 'adaptive']) {
    const pcm = signal(641), common = ['--profile', String(profile), '--quality', quality, '--repeat', '3'];
    const ordinary = success(native, pcm, common);
    const defaultCpu = success(cuda, pcm, common);
    const cpu = success(cuda, pcm, [...common, '--backend', 'cpu']);
    const accelerated = success(cuda, pcm, [...common, '--backend', 'cuda']);
    assert.deepEqual(defaultCpu.bytes, ordinary.bytes); assert.equal(defaultCpu.report.backend, 'cpu');
    assert.deepEqual(cpu.bytes, ordinary.bytes); assert.deepEqual(accelerated.bytes, ordinary.bytes);
    assert.equal(cpu.report.backend, 'cpu'); assert.equal(accelerated.report.backend, 'cuda');
    assert.equal(accelerated.report.repeatTimesMs.length, 3);
    assert.ok(accelerated.report.backendInitializationMs >= 0);
  }
});

test('native fast/adaptive CLI encodes retained speech in CPU and CUDA modes', { skip: !enabled }, () => {
  const pcm = decode(readFileSync(new URL('../audio/lpx-speech/chego/quality.v9.lpx', import.meta.url))).pcm;
  for (const profile of [4, 6]) for (const quality of ['fast', 'adaptive']) {
    const args = ['--profile', String(profile), '--quality', quality];
    const ordinary = success(native, pcm, args);
    assert.equal(decode(ordinary.bytes).pcm.length, pcm.length);
    if (quality === 'fast') assert.deepEqual(ordinary.bytes, Buffer.from(fast(pcm, 8000, profile)));
    if (gpu) {
      const accelerated = success(cuda, pcm, [...args, '--backend', 'cuda']);
      assert.deepEqual(accelerated.bytes, ordinary.bytes);
    }
  }
});

test('native input validation emits no successful stream', { skip: !enabled }, () => {
  const pcm = signal(1);
  for (const args of [['--profile', '5'], ['--rate', '7500'], ['--repeat', '0'], ['--repeat', '21'],
    ['--calls', '5'], ['--max-bytes', '21'], ['--max-bytes', '2147483647'], ['--quality', 'fast', '--auto-quiet'],
    ['--unknown', '1'], ['--backend', 'cuda'], ['--search', 'unknown'], ['--size-allowance', '101'],
    ['--quality', 'fast', '--search', 'reference'], ['--quality', 'fast', '--size-allowance', '25'],
    ['--normalize', '--auto-quiet'], ['--normalize', '--target-lufs', '-31'],
    ['--normalize', '--target-lufs', '-8'], ['--normalize', '--max-gain-db', '25']]) {
    const result = run(native, pcm, args);
    assert.notEqual(result.status, 0); assert.equal(result.stdout.length, 0); assert.ok(JSON.parse(result.stderr.toString()).error);
  }
  for (const input of [Buffer.alloc(0), Buffer.from([1])]) {
    const result = spawnSync(native, [], { input });
    assert.notEqual(result.status, 0); assert.equal(result.stdout.length, 0);
  }
});

test('native configurable input normalization matches WASM and uses ordinary V9', { skip: !enabled }, async () => {
  const encode = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));
  const pcm = Int16Array.from(signal(4001), x => Math.round(x / 16));
  for (const profile of [4, 6]) {
    const common = ['--profile', String(profile), '--search', 'reference'];
    const original = success(native, pcm, common);
    const gained = success(native, pcm, [...common, '--normalize', '--target-lufs', '-21', '--max-gain-db', '9', '--repeat', '2']);
    const expected = encode(pcm, 8000, profile, () => {}, {
      extendedSearch: false, normalization: 'loudness', targetLufs: -21, maxGainDb: 9
    });
    assert.deepEqual(gained.bytes, Buffer.from(expected));
    assert.notDeepEqual(gained.bytes, original.bytes);
    assert.equal(gained.bytes[2]&32,0);
    assert.equal(gained.report.normalized,true);
    assert.ok(gained.report.inputGainDb <= 9);
  }
});

test('native V9 Long retains one continuous output', { skip: !enabled }, () => {
  const pcm = new Int16Array(65537);
  const { bytes, report } = success(native, pcm, ['--profile', '6', '--quality', 'fast']);
  assert.equal(report.long, true); assert.equal(decode(bytes).pcm.length, pcm.length);
  assert.deepEqual(bytes, Buffer.from(fast(pcm, 8000, 6)));
});

test('file wrapper is binary safe and refuses overwrites or failed output', { skip: !enabled }, () => {
  mkdirSync(join(root, 'build'), { recursive: true });
  const directory = mkdtempSync(join(root, 'build/lpx-cli-test-'));
  try {
    const input = join(directory, 'source.pcm'), output = join(directory, 'результат.lpx');
    const pcm = signal(321); writeFileSync(input, Buffer.from(pcm.buffer));
    const wrapper = join(root, 'web-player/scripts/encode-lpx-native.mjs');
    const args = [wrapper, input, output, '--pcm', '--encoder', native, '--quality', 'fast'];
    let result = spawnSync(process.execPath, args, { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const expected = Buffer.from(fast(pcm, 8000, 6)); assert.deepEqual(readFileSync(output), expected);
    result = spawnSync(process.execPath, args, { cwd: root, encoding: 'utf8' });
    assert.notEqual(result.status, 0); assert.deepEqual(readFileSync(output), expected);
    const absent = join(directory, 'failed.lpx');
    result = spawnSync(process.execPath, [wrapper, input, absent, '--pcm', '--encoder', native, '--backend', 'cuda'], { cwd: root, encoding: 'utf8' });
    assert.notEqual(result.status, 0); assert.equal(existsSync(absent), false);
  } finally { removeTemporary(directory); }
});

test('file wrapper averages every channel before encoding', { skip: !enabled || spawnSync('ffmpeg', ['-version']).status !== 0 }, () => {
  const directory = mkdtempSync(join(root, 'build/lpx-cli-audio-'));
  try {
    const input = join(directory, 'three-channel.wav'), output = join(directory, 'out.lpx'), n = 321;
    const bytes = Buffer.alloc(44 + n * 6);
    bytes.write('RIFF'); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8);
    bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(3, 22); bytes.writeUInt32LE(8000, 24);
    bytes.writeUInt32LE(48000, 28); bytes.writeUInt16LE(6, 32); bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(n * 6, 40);
    for (let i = 0; i < n; i++) bytes.writeInt16LE(3000, 44 + i * 6 + 4);
    writeFileSync(input, bytes);
    const result = spawnSync(process.execPath, [join(root, 'web-player/scripts/encode-lpx-native.mjs'), input, output,
      '--encoder', native, '--quality', 'fast'], { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(readFileSync(output), Buffer.from(fast(new Int16Array(n).fill(1000), 8000, 6)));
  } finally { removeTemporary(directory); }
});

test('private CUDA corpus reports reject output junctions before reading media', () => {
  mkdirSync(join(root, 'build'), { recursive: true });
  const directory = mkdtempSync(join(root, 'build/lpx-private-output-'));
  try {
    const target = join(directory, 'target'), link = join(directory, 'redirect');
    mkdirSync(target); symlinkSync(target, link, process.platform === 'win32' ? 'junction' : 'dir');
    const result = spawnSync(process.execPath, [join(root, 'web-player/scripts/benchmark-lpx-cuda.mjs'),
      '--encoder', 'unused', '--manifest', 'unused', '--output', join(link, 'report.json')], { encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /symbolic links or junctions/);
    assert.equal(existsSync(join(target, 'report.json')), false);
  } finally { removeTemporary(directory); }
});

test('native build output cannot escape the ignored build directory', () => {
  const script = join(root, 'web-player/scripts/build-lpx-native.mjs');
  for (const output of ['../outside-native-build', 'build', ...(process.platform === 'win32' ? ['D:/outside-native-build'] : ['/outside-native-build'])]) {
    const result = spawnSync(process.execPath, [script, '--output', output], { cwd: root, encoding: 'utf8' });
    assert.notEqual(result.status, 0); assert.match(result.stderr, /must be a subdirectory/);
  }
});
