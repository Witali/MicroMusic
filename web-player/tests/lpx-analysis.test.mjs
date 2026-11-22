import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const binary = process.env.LPX_ANALYSIS_SELFTEST_WASM;
test('silent-block shortcut preserves full state, PCM and pulses for every ring alignment and profile',
  { skip: !binary }, async () => {
    const { instance } = await WebAssembly.instantiate(readFileSync(binary));
    assert.equal(instance.exports.lpx_silence_selftest(), 48,
      'negative codes identify state/PCM/pulse failures');
  });
