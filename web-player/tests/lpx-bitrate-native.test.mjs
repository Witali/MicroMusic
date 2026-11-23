import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

const helper = process.env.LPX_BITRATE_NATIVE;
test('bitrate native C++ and scalar/SIMD WASM retain identical complete streams', { skip: !helper }, async () => {
  const encoders = await Promise.all(['encoder-adaptive', 'encoder-adaptive-simd'].map(name =>
    createEncoder(readFileSync(new URL(`../lpx/${name}.wasm`, import.meta.url)))));
  const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
  const tone = n => Int16Array.from({ length: n }, (_, i) => Math.round(5000 * Math.sin(i * .14) + 700 * Math.sin(i * .31)));
  const cases = [tone(3201), tone(8193), Int16Array.from(tone(8193), x => Math.round(x / 128)),
    Int16Array.from({ length: 8001 }, (_, i) => i < 320 || i > 6000 ? 0 : Math.round(5000 * Math.sin(i * .14))),
    new Int16Array(65537)];
  for (const kbps of [3, 8]) for (const pcm of cases) {
    const wsl = process.env.LPX_BITRATE_WSL;
    const command = wsl ? 'wsl' : helper;
    const args = [...(wsl ? ['-d', wsl, '--', helper] : []), String(kbps), '4'];
    const input = Buffer.alloc(pcm.length * 2);
    pcm.forEach((value, i) => input.writeInt16LE(value, i * 2));
    const native = spawnSync(command, args, { input, maxBuffer: 8 * 1024 * 1024 });
    assert.equal(native.status, 0, `native ${kbps}k/${pcm.length}: ${native.stderr?.toString()}`);
    for (const encode of encoders) {
      const actual = encode(pcm, 8000, kbps);
      assert.deepEqual(Buffer.from(actual), native.stdout, `${kbps}k/${pcm.length} native/WASM`);
      assert.ok(actual.length <= Math.floor(pcm.length * kbps / 64));
      const decoded = decode(actual);
      assert.equal(decoded.samples, pcm.length);
      assert.equal(decoded.long, pcm.length > 64000);
      if (!pcm.some(x => x)) assert.ok(decoded.pcm.every(x => x === 0), 'silence stays exact');
    }
  }
});
