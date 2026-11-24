import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const suffix = process.platform === 'win32' ? '.exe' : '';
const native = process.env.LPX_NATIVE_ENCODER || join(root, `build/lpx-native/lpx-encode${suffix}`);
const cuda = process.env.LPX_CUDA_ENCODER || join(root, `build/lpx-native/lpx-encode-cuda${suffix}`);
const enabled = existsSync(native), gpu = enabled && existsSync(cuda);
const scalar = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));
const simd = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive-simd.wasm', import.meta.url)));
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
const wrapper = join(root, 'web-player/scripts/encode-lpx-native.mjs');
const signal = length => Int16Array.from({ length }, (_, i) => Math.round(2000 * Math.sin(i * .15) + 500 * Math.sin(i * .31)));
function run(executable, pcm, args = []) {
  return spawnSync(executable, args, { cwd: root, input: Buffer.from(pcm.buffer, pcm.byteOffset, pcm.byteLength), maxBuffer: 100 * 1024 * 1024 });
}
function success(executable, pcm, args = []) {
  const result = run(executable, pcm, args);
  assert.equal(result.status, 0, result.stderr?.toString());
  const report = JSON.parse(result.stderr.toString().trim());
  assert.equal(report.samples, pcm.length); assert.equal(report.bytes, result.stdout.length);
  assert.equal(report.engine, 'accuracy'); assert.equal(report.search, 'accuracy');
  return { bytes: result.stdout, report };
}
function temporary(action) {
  mkdirSync(join(root, 'build'), { recursive: true });
  const directory = mkdtempSync(join(root, 'build/lpx-common-cli-'));
  try { action(directory); }
  finally {
    assert.ok(resolve(directory).startsWith(resolve(root, 'build') + sep));
    rmSync(directory, { recursive: true, force: true });
  }
}

test('default native CLI uses the same P6 accuracy engine as the Web UI', { skip: !enabled }, () => {
  const pcm = signal(641), expected = Buffer.from(scalar(pcm, 8000, 6, () => {}, { accuracy: true }));
  const ordinary = success(native, pcm);
  assert.deepEqual(ordinary.bytes, expected); assert.equal(ordinary.report.accuracyLevel, 6);
  for (const args of [['--profile', '6'], ['--accuracy', '6'], ['--profile', '6', '--accuracy', '6']])
    assert.deepEqual(success(native, pcm, args).bytes, expected);
});

test('common native P3/P4/P6/P8 match scalar/SIMD accuracy WASM at every rate and quality', { skip: !enabled }, () => {
  const pcm = signal(641);
  for (const rate of [8000, 12000, 16000]) for (const level of [3, 4, 6, 8]) for (const quality of ['fast', 'adaptive']) {
    const options = { accuracy: true, calls: quality === 'fast' ? 0 : 4 };
    const expected = Buffer.from(scalar(pcm, rate, level, () => {}, options));
    assert.deepEqual(Buffer.from(simd(pcm, rate, level, () => {}, options)), expected, `SIMD P${level}/${rate}/${quality}`);
    const args = ['--profile', String(level), '--rate', String(rate), '--quality', quality, '--repeat', '2'];
    const ordinary = success(native, pcm, args);
    assert.deepEqual(ordinary.bytes, expected, `CPU P${level}/${rate}/${quality}`);
    assert.equal(ordinary.report.accuracyLevel, level); assert.equal(ordinary.report.repeatTimesMs.length, 2);
    assert.equal(decode(ordinary.bytes).profile, level <= 4 ? 4 : 6);
    if (gpu) for (const backend of ['cpu', 'cuda']) {
      const accelerated = success(cuda, pcm, [...args, '--backend', backend]);
      assert.deepEqual(accelerated.bytes, expected, `${backend} P${level}/${rate}/${quality}`);
      assert.equal(accelerated.report.backend, backend);
    }
  }
});

test('common native normalization and configurable refinement match shared accuracy WASM', { skip: !enabled }, () => {
  const pcm = signal(4001);
  for (const level of [4, 6]) {
    const options = { accuracy: true, calls: 1, normalization: 'loudness', targetLufs: -21, maxGainDb: 9 };
    const expected = Buffer.from(scalar(pcm, 8000, level, () => {}, options));
    const ordinary = success(native, pcm, ['--accuracy', String(level), '--calls', '1', '--normalize', '--target-lufs', '-21', '--max-gain-db', '9']);
    assert.deepEqual(ordinary.bytes, expected); assert.equal(ordinary.report.normalized, true);
    assert.ok(ordinary.report.inputGainDb <= 9);
  }
});

test('common file wrapper defaults and profile aliases match the shared accuracy engine', { skip: !enabled }, () => temporary(directory => {
  const pcm = signal(641), input = join(directory, 'source.pcm');
  writeFileSync(input, Buffer.from(pcm.buffer));
  const cases = [{ level: 6, args: [] }, ...[3, 4, 6, 8].flatMap(level => ['fast', 'adaptive'].map(quality => ({
    level, quality, args: [level <= 4 ? '--profile' : '--accuracy', String(level), '--quality', quality, '--repeat', '2']
  })))];
  for (const [index, item] of cases.entries()) {
    const output = join(directory, `result-${index}.lpx`);
    const result = spawnSync(process.execPath, [wrapper, input, output, '--pcm', '--encoder', native, ...item.args], { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const expected = Buffer.from(scalar(pcm, 8000, item.level, () => {}, { accuracy: true, calls: item.quality === 'fast' ? 0 : 4 }));
    assert.deepEqual(readFileSync(output), expected);
    const report = JSON.parse(result.stdout.trim());
    assert.equal(report.engine, 'accuracy'); assert.equal(report.accuracyLevel, item.level);
    if (index === 0) {
      const repeated = spawnSync(process.execPath, [wrapper, input, output, '--pcm', '--encoder', native], { cwd: root, encoding: 'utf8' });
      assert.notEqual(repeated.status, 0); assert.match(repeated.stderr, /Output already exists/);
      assert.deepEqual(readFileSync(output), expected);
    }
  }
}));

const incompatible = [
  { args: ['--search', 'expanded'], error: /require --legacy/ },
  { args: ['--search', 'reference'], error: /require --legacy/ },
  { args: ['--size-allowance', '0'], error: /require --legacy/ },
  { args: ['--max-bytes', '0'], error: /require --legacy/ },
  { args: ['--auto-quiet'], error: /require --legacy/ },
  { args: ['--non-speech'], error: /require --legacy/ },
  { args: ['--legacy', '--accuracy', '4'], error: /cannot be combined with --legacy/ },
  { args: ['--legacy', '--profile', '3'], error: /Legacy profile must be 4 or 6/ },
  { args: ['--legacy', '--profile', '8'], error: /Legacy profile must be 4 or 6/ },
  { args: ['--accuracy', '4', '--profile', '6'], error: /must select the same accuracy level/ },
  { args: ['--accuracy', '0'], error: /Accuracy level must be 3, 4, 6 or 8/ },
  { args: ['--profile', '5'], error: /Accuracy level must be 3, 4, 6 or 8/ }
];
test('common native CLI rejects incompatible legacy flags before emitting a stream', { skip: !enabled }, () => {
  for (const item of incompatible) {
    const result = run(native, signal(1), item.args);
    assert.notEqual(result.status, 0); assert.equal(result.stdout.length, 0);
    assert.match(JSON.parse(result.stderr.toString()).error, item.error);
  }
});

test('common file wrapper rejects incompatible legacy flags before reading or writing files', () => temporary(directory => {
  for (const [index, item] of incompatible.entries()) {
    const output = join(directory, `absent-${index}.lpx`);
    const result = spawnSync(process.execPath, [wrapper, join(directory, 'does-not-exist.pcm'), output, '--pcm', ...item.args], { cwd: root, encoding: 'utf8' });
    assert.notEqual(result.status, 0); assert.match(result.stderr, item.error); assert.equal(existsSync(output), false);
  }
}));
