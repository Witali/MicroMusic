import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

test('SIMD build provenance is current and the module has no host imports', () => {
  const root = new URL('../../', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('web-player/lpx/encoder-simd-build.json', root)));
  const binary = readFileSync(new URL('web-player/lpx/encoder-simd.wasm', root));
  const hash = value => createHash('sha256').update(value).digest('hex');
  assert.equal(hash(binary), manifest.sha256);
  assert.equal(manifest.backend, 'wasm-simd128-pulse4');
  for (const [path, expected] of Object.entries(manifest.inputs)) {
    assert.equal(hash(readFileSync(new URL(path, root), 'utf8').replaceAll('\r\n', '\n')), expected, path);
  }
  assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)), []);
});

test('SIMD batches preserve every possible winner, exact error and ties across 972000 lane/bound cases',
  { skip: !process.env.LPX_SIMD_SELFTEST_WASM }, async () => {
    const { instance } = await WebAssembly.instantiate(readFileSync(process.env.LPX_SIMD_SELFTEST_WASM));
    assert.equal(instance.exports.lpx_simd_selftest(), 972000);
  });
