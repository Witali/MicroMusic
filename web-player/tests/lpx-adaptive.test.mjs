import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createDecoder, parseHeader } from '../lpx/codec.js';
import { createEncoder } from '../lpx/encoder.js';

const root = new URL('../../', import.meta.url);
const names = ['encoder-adaptive', 'encoder-adaptive-simd'];
const apis = await Promise.all(names.map(async name => {
  const binary = readFileSync(new URL(`web-player/lpx/${name}.wasm`, root));
  const { instance } = await WebAssembly.instantiate(binary);
  instance.exports.__wasm_call_ctors();
  return instance.exports;
}));
const decode = await createDecoder(readFileSync(new URL('web-player/lpx/decoder.wasm', root)));
const tone = n => Int16Array.from({ length: n }, (_, i) => Math.round(6000 * Math.sin(i * .14) + 900 * Math.sin(i * .31)));
function encode(api, pcm, profile = 4, rate = 8000, { calls = 4, autoQuiet = 0, maxBytes = 0, extended = false, allowance = 0 } = {}) {
  assert.ok(api.enc_reserve(pcm.length));
  new Int16Array(api.memory.buffer, api.enc_input(), pcm.length).set(pcm);
  const size = extended
    ? api.enc_adaptive_extended(pcm.length, profile, rate, autoQuiet, maxBytes, calls, allowance)
    : api.enc_adaptive(pcm.length, profile, rate, autoQuiet, maxBytes, calls);
  assert.ok(size >= 13, `adaptive status ${size}`);
  const pointer = api.enc_adaptive_output();
  assert.ok(pointer > 0, 'getters retain the initialized output vector');
  assert.ok(api.enc_adaptive_candidates() >= 1, 'getters retain the completed report');
  assert.ok(api.enc_adaptive_stages() <= calls);
  return new Uint8Array(api.memory.buffer, pointer, size).slice();
}
function same(pcm, profile = 4, rate = 8000, options) {
  const scalar = encode(apis[0], pcm, profile, rate, options);
  const simd = encode(apis[1], pcm, profile, rate, options);
  assert.deepEqual(simd, scalar, `P${profile}/${rate}/${pcm.length}`);
  const result = decode(scalar);
  assert.equal(result.samples, pcm.length);
  assert.equal(result.pcm.length, pcm.length);
  assert.equal(result.profile, profile);
  assert.equal(result.sampleRate, rate);
  return scalar;
}

test('adaptive scalar/SIMD binaries have current provenance and no host imports', () => {
  const hash = bytes => createHash('sha256').update(bytes).digest('hex');
  for (const name of names) {
    const binary = readFileSync(new URL(`web-player/lpx/${name}.wasm`, root));
    const manifest = JSON.parse(readFileSync(new URL(`web-player/lpx/${name}-build.json`, root)));
    assert.equal(hash(binary), manifest.sha256);
    assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)), []);
    for (const [path, expected] of Object.entries(manifest.inputs)) {
      assert.equal(hash(readFileSync(new URL(path, root), 'utf8').replaceAll('\r\n', '\n')), expected, path);
    }
  }
});

test('adaptive scalar/SIMD match on partial packets, clipping, silence and transitions', () => {
  for (const profile of [4, 6]) {
    for (const n of [1, 19, 20, 39, 40, 41, 159, 160, 161, 319, 320, 321]) same(tone(n), profile, [8000, 12000, 16000][n % 3]);
    let state = 0x45e2a17;
    const noise = Int16Array.from({ length: 961 }, () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return state >> 16; });
    for (const pcm of [new Int16Array(961), new Int16Array(961).fill(32767), new Int16Array(961).fill(-32768),
      Int16Array.from({ length: 961 }, (_, i) => i & 1 ? 32767 : -32768),
      Int16Array.from({ length: 961 }, (_, i) => i % 160 === 0 ? 32767 : 0), noise,
      Int16Array.from({ length: 1921 }, (_, i) => i < 320 || i >= 640 && i < 1280 ? 0 : Math.round(8000 * Math.sin(i * .14)))]) same(pcm, profile);
  }
});

test('bounded passes and opt-in quiet gain are deterministic across adaptive backends', () => {
  const pcm = Int16Array.from(tone(961), x => Math.round(x / 128));
  for (const calls of [0, 1, 2, 3, 4]) same(pcm, 6, 8000, { calls });
  assert.equal(apis[0].enc_adaptive_gain(), 0, 'input level is preserved by default');
  same(pcm, 6, 8000, { autoQuiet: 1 });
  assert.ok(apis[0].enc_adaptive_gain() > 0, 'quiet gain requires an explicit option');
});

test('adaptive API rejects malformed requests and remains usable afterwards', () => {
  for (const api of apis) {
    assert.ok(api.enc_reserve(641));
    for (const args of [[0,4,8000,0,0,4], [32000001,4,8000,0,0,4], [641,15,8000,0,0,4],
      [641,4,44100,0,0,4], [641,4,8000,2,0,4], [641,4,8000,0,-1,4],
      [641,4,8000,0,1,4], [641,4,8000,0,0,-1], [641,4,8000,0,0,5]]) {
      assert.equal(api.enc_adaptive(...args), -1);
    }
    new Int16Array(api.memory.buffer, api.enc_input(), 641).set(tone(641));
    assert.equal(api.enc_adaptive(641, 4, 8000, 0, 22, 0), -6, 'an infeasible complete-file budget fails');
    encode(api, tone(641));
  }
});

test('repeated adaptive use reuses the heap and preserves complete output', () => {
  const pcm = tone(1921);
  for (const api of apis) {
    const expected = encode(api, pcm);
    for (let i = 0; i < 3; i++) encode(api, tone(i & 1 ? 641 : 1921));
    const warmedBytes = api.memory.buffer.byteLength;
    for (let i = 0; i < 8; i++) {
      encode(api, tone(641), 6);
      assert.deepEqual(encode(api, pcm), expected);
    }
    assert.equal(api.memory.buffer.byteLength, warmedBytes, 'no continuing heap growth after warmup');
  }
});

test('whole-input adaptive refinement emits one continuous V9 Long stream', () => {
  for (const profile of [4, 6]) {
    const n = profile === 4 ? 131073 : 65537;
    const bytes = same(tone(n), profile, 12000);
    assert.ok(parseHeader(bytes).long);
    assert.equal(parseHeader(bytes).samples, n);
  }
});

test('expanded pitch/gain search and explicit allowances match across APIs and backends', async () => {
  const wrappers = await Promise.all(names.map(name => createEncoder(readFileSync(new URL(`web-player/lpx/${name}.wasm`, root)))));
  for (const profile of [4, 6]) {
    const pcm = tone(961), rate = profile === 4 ? 8000 : 16000;
    const original = same(pcm, profile, rate);
    for (const allowance of [0, 10, 25]) {
      const expanded = same(pcm, profile, rate, { extended: true, allowance });
      for (const wrapper of wrappers) {
        assert.deepEqual(wrapper(pcm, rate, profile, () => {}, { sizeAllowancePercent: allowance }), expanded);
        assert.deepEqual(wrapper(pcm, rate, profile, () => {}, { extendedSearch: false }), original);
      }
    }
    for (const api of apis) {
      for (const allowance of [-1, 101]) assert.equal(api.enc_adaptive_extended(pcm.length, profile, rate, 0, 0, 4, allowance), -1);
      assert.deepEqual(encode(api, pcm, profile, rate), original, 'ordinary adaptive calls remain valid after extended calls');
    }
  }
  for (const wrapper of wrappers) for (const allowance of [-1, 101, .5, NaN]) {
    assert.throws(() => wrapper(tone(321), 8000, 4, () => {}, { sizeAllowancePercent: allowance }), /ограничение размера/);
  }
});
