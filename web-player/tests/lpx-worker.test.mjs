import test from 'node:test';
import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';
import { readFileSync } from 'node:fs';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

// Run the shipped worker and its default backend loader. Only the browser's
// transport primitives are adapted; no encoder or backend logic is mocked.
const workerSource = `
  const { parentPort, workerData } = require('node:worker_threads');
  const { readFile } = require('node:fs/promises');
  globalThis.self = { postMessage: (message, transfer) => parentPort.postMessage(message, transfer) };
  globalThis.fetch = async url => {
    const target = new URL(url); target.search = '';
    if (!/encoder-adaptive(?:-simd)?\\.wasm$/.test(target.pathname)) throw Error('Unexpected asset');
    return new Response(await readFile(target));
  };
  import(workerData).then(() => parentPort.on('message', data => self.onmessage({ data })));
`;
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
const reference = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));

test('shipped worker loads adaptive assets, forwards allowances and returns one validated file', async () => {
  for (const backend of ['scalar', 'simd', 'auto']) for (const normalization of ['preserve', 'loudness', 'file']) {
    const worker = new Worker(workerSource, { eval: true, workerData: new URL('../lpx/encode-worker.js', import.meta.url).href });
    const pcm = Int16Array.from({ length: 6001 }, (_, i) => Math.round(6000 * Math.sin(i * .14)));
    const expected = reference(pcm, 12000, 6, () => {}, { sizeAllowancePercent: 25, normalization });
    const expectedLoudness = reference.loudness;
    const progress = [];
    try {
      const result = await new Promise((resolve, reject) => {
        worker.on('error', reject);
        worker.on('message', data => {
          if (data.error) reject(Error(data.error));
          if (data.progress !== undefined) progress.push(data.progress);
          if (data.result) resolve(data.result);
        });
        worker.postMessage({ pcm: pcm.buffer, sampleRate: 12000, profile: 6, backend, sizeAllowancePercent: 25, normalization }, [pcm.buffer]);
      });
      assert.deepEqual(result.bytes, expected);
      assert.deepEqual(progress, [0, 1]);
      assert.equal(result.backend, backend === 'scalar' ? 'scalar' : 'simd');
      assert.equal(result.samples, 6001);
      assert.equal(decode(result.bytes).pcm.length, 6001);
      assert.deepEqual(result.loudness, expectedLoudness);
      if (normalization === 'loudness') assert.equal(result.loudness.status, 1);
      assert.ok(result.elapsedMs >= 0);
    } finally { await worker.terminate(); }
  }
});
