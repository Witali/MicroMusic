import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder, parseHeader } from '../lpx/codec.js';
import { readRecordedBuildFile } from './helpers/recorded-build-source.mjs';

// Pin the shipped exhaustive implementation, independently of future edits.
const revision = '688fc4f618f9ed6176501e0f5d6e55bcb8fc80cf';
const baseline = readRecordedBuildFile(revision, 'web-player/lpx/encoder.wasm');
assert.equal(createHash('sha256').update(baseline).digest('hex'),
  'f59002ca5e46f6bee2616f28edf3fe61ff91972df93ded823b6af21c64355a49');
const reference = await createEncoder(baseline);
const encode = await createEncoder(readFileSync(process.env.LPX_CANDIDATE_WASM || new URL('../lpx/encoder.wasm', import.meta.url)));
const fallback = process.env.LPX_EXHAUSTIVE_WASM
  ? await createEncoder(readFileSync(process.env.LPX_EXHAUSTIVE_WASM)) : null;
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));

function same(pcm, rate, profile) {
  const expected = reference(pcm, rate, profile), actual = encode(pcm, rate, profile);
  assert.deepEqual(actual, expected, `LPX P${profile}/${rate}/${pcm.length}`);
  assert.deepEqual(decode(actual).pcm, decode(expected).pcm, 'decoded PCM');
  if (fallback) assert.deepEqual(fallback(pcm, rate, profile), expected, 'exhaustive C fallback');
  return actual;
}
function noise(length) {
  let seed = 0x45e2a17;
  return Int16Array.from({ length }, () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed >> 16; });
}

test('optimized search retains exhaustive bytes and PCM at every packet/block tail', () => {
  for (const profile of [4, 6]) for (const length of [1, 19, 20, 39, 40, 41, 159, 160, 161, 319, 320, 321]) {
    same(noise(length), [8000, 12000, 16000][length % 3], profile);
  }
});

test('ties, aliased zero/unit steps, gain saturation, clipping and transient history stay exact', () => {
  const signals = [new Int16Array(641), Int16Array.from({ length: 641 }, (_, i) => i % 3 - 1),
    new Int16Array(641).fill(32767), new Int16Array(641).fill(-32768),
    Int16Array.from({ length: 641 }, (_, i) => i & 1 ? 32767 : -32768),
    Int16Array.from({ length: 961 }, (_, i) => i % 160 === 0 ? (i & 32 ? -32768 : 32767) : 0),
    Int16Array.from({ length: 961 }, (_, i) => Math.round(31000 * Math.sin(i * .17))), noise(961)];
  for (const profile of [4, 6]) for (const rate of [8000, 12000, 16000]) {
    for (const pcm of signals) same(pcm, rate, profile);
  }
});

test('real decoded speech remains byte exact in P4/P6 at all supported rates', () => {
  const pcm = decode(readFileSync(new URL('../audio/lpx-speech/chego/quality.v9.lpx', import.meta.url))).pcm;
  for (const profile of [4, 6]) for (const rate of [8000, 12000, 16000]) same(pcm, rate, profile);
});

test('continuous V9 Long crosses both legacy sample boundaries without changing bytes or PCM', () => {
  for (const profile of [4, 6]) {
    const length = profile === 4 ? 131073 : 65537;
    const pcm = Int16Array.from({ length }, (_, i) => Math.round(6000 * Math.sin(i * .14)));
    assert.ok(parseHeader(same(pcm, 12000, profile)).long);
  }
});

test('encoded uint32 payload lengths and long silent ties remain exact', () => {
  const bytes = same(new Int16Array(1280001), 16000, 6);
  assert.ok(bytes.length > 65535);
  assert.equal(parseHeader(bytes).samples, 1280001);
});

test('leading silence, zero pauses and resumed excitation retain exact filter/ring history', () => {
  for (const profile of [4, 6]) for (const rate of [8000, 12000, 16000]) {
    const pcm = Int16Array.from({ length: 9601 }, (_, i) => i < 641 || (i >= 1920 && i < 7681)
      ? 0 : Math.round(9000 * Math.sin(i * .14) + 2000 * Math.sin(i * .31)));
    same(pcm, rate, profile);
  }
});
