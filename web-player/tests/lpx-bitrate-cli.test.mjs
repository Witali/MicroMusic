import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeWav, createDecoder } from '../lpx/codec.js';
import { main, readPcm16Wav } from '../scripts/encode-lpx.mjs';

test('PC WAV input preserves PCM16 units and rejects damaged or unprepared audio', () => {
  const pcm = Int16Array.of(-32768, -1, 0, 1, 32767);
  const bytes = new Uint8Array(encodeWav(pcm, 8000));
  assert.deepEqual(readPcm16Wav(bytes), pcm);
  for (const offset of [0, 4, 8, 20, 22, 24, 28, 32, 34, 40]) {
    const invalid = bytes.slice(); invalid[offset] ^= 1;
    assert.throws(() => readPcm16Wav(invalid));
  }
  for (const count of [0, 1, 11, 43, bytes.length - 1]) assert.throws(() => readPcm16Wav(bytes.subarray(0, count)));
  assert.throws(() => readPcm16Wav(new Uint8Array(encodeWav(pcm, 16000))));
  assert.throws(() => readPcm16Wav(new Uint8Array(encodeWav(new Int16Array(), 8000))));
});

test('PC CLI produces complete V9 at each cap and protects an existing output', async () => {
  const root = resolve(fileURLToPath(new URL('../../build/lpx-bitrate-cli-tests/', import.meta.url)));
  await mkdir(root, { recursive: true });
  const folder = await mkdtemp(root + '/case-');
  const pcm = Int16Array.from({ length: 3201 }, (_, i) => Math.round(5000 * Math.sin(i * .14) + 300 * Math.sin(i * .31)));
  const input = folder + '/input.wav';
  await writeFile(input, new Uint8Array(encodeWav(pcm, 8000)));
  const decode = await createDecoder(await readFile(new URL('../lpx/decoder.wasm', import.meta.url)));
  try {
    for (const kbps of [3, 8]) {
      const output = folder + `/${kbps}.lpx`;
      const bytes = await main([input, output, '--kbps', String(kbps)]);
      const result = decode(bytes);
      assert.equal(result.samples, pcm.length);
      assert.equal(result.profile, kbps === 3 ? 4 : 6);
      assert.ok(bytes.length <= Math.floor(pcm.length * kbps / 64));
      assert.deepEqual(await readFile(output), Buffer.from(bytes));
      await assert.rejects(main([input, output, '--kbps', String(kbps)]), /already exists/);
      assert.deepEqual(await readFile(output), Buffer.from(bytes));
    }
    await assert.rejects(main([input, input, '--kbps', '3']), /Usage/);
    await assert.rejects(main([input, folder + '/bad.lpx', '--kbps', '4']), /Usage/);
  } finally {
    assert.ok(resolve(folder).startsWith(root + sep));
    await rm(folder, { recursive: true, force: true });
  }
});
