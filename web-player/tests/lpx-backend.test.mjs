import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createEncoderBackend, supportsSimd } from '../lpx/encoder-backend.js';

const binaries = {
  scalar: readFileSync(new URL('../lpx/encoder.wasm', import.meta.url)),
  simd: readFileSync(new URL('../lpx/encoder-simd.wasm', import.meta.url))
};
test('the SIMD feature probe validates in the supported test runtime', () => {
  assert.equal(supportsSimd(), true);
});
test('manual ordinary/SIMD and automatic modes load the selected backend and create identical LPX', async () => {
  const pcm = Int16Array.from({ length: 1001 }, (_, i) => Math.round(24000 * Math.sin(i * .17)));
  const results = [];
  for (const [mode, simdAvailable, expected] of [['scalar', true, 'scalar'], ['simd', true, 'simd'], ['auto', true, 'simd'], ['auto', false, 'scalar']]) {
    const calls = [];
    const { encode, backend } = await createEncoderBackend(mode, {
      simdAvailable, readBinary: async name => { calls.push(name); return binaries[name]; }
    });
    assert.equal(backend, expected); assert.deepEqual(calls, [expected]);
    results.push([4, 6].flatMap(profile => [8000, 12000, 16000].map(rate => encode(pcm, rate, profile))));
  }
  for (const result of results.slice(1)) assert.deepEqual(result, results[0]);
});
test('Auto falls back to ordinary encoding on SIMD download or instantiation failure', async () => {
  for (const broken of [null, new Uint8Array([0])]) {
    const calls = [];
    const result = await createEncoderBackend('auto', { simdAvailable: true, readBinary: async name => {
      calls.push(name);
      if (name === 'simd') { if (broken === null) throw new Error('download failed'); return broken; }
      return binaries.scalar;
    } });
    assert.equal(result.backend, 'scalar'); assert.deepEqual(calls, ['simd', 'scalar']);
    assert.ok(result.encode(new Int16Array(1), 8000, 6).length >= 13);
  }
});
test('manual SIMD never silently switches mode, and unsupported/invalid choices fail before loading', async () => {
  const calls = [], readBinary = async name => { calls.push(name); throw new Error('download failed'); };
  await assert.rejects(createEncoderBackend('simd', { simdAvailable: false, readBinary }), /SIMD недоступен/);
  await assert.rejects(createEncoderBackend('unknown', { simdAvailable: true, readBinary }), /Неизвестный режим/);
  assert.deepEqual(calls, []);
  await assert.rejects(createEncoderBackend('simd', { simdAvailable: true, readBinary }), /download failed/);
  assert.deepEqual(calls, ['simd']);
});
test('encoding errors remain visible without reloading or switching backend', async () => {
  const calls = [];
  const { encode } = await createEncoderBackend('auto', { simdAvailable: true, readBinary: async name => {
    calls.push(name); return binaries[name];
  } });
  assert.throws(() => encode(new Int16Array(), 8000, 6));
  assert.deepEqual(calls, ['simd']);
});
