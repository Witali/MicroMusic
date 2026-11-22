import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('cached pulse prefixes preserve exact loss, ring/filter state and bounds for lags 18/19 and ring wrap',
  { skip: !process.env.LPX_PREFIX_SELFTEST_WASM }, async () => {
    const { instance } = await WebAssembly.instantiate(readFileSync(process.env.LPX_PREFIX_SELFTEST_WASM));
    assert.equal(instance.exports.lpx_prefix_selftest(), 918000,
      '918000 direct candidate/bound checks; negative return values identify a state/loss/bound failure');
  });
