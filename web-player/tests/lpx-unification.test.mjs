import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';
import { readRecordedBuildFile } from './helpers/recorded-build-source.mjs';
import { encodingPolicy, bitrateBudget } from '../lpx/encoding-policy.js';

// Pin the pre-refactoring production artifact, independently of current builds.
const baselineRevision = 'b428477f5e4f39797dc7c91b53c01469d7b4944f';
const baseline = await createEncoder(readRecordedBuildFile(baselineRevision, 'web-player/lpx/encoder-adaptive.wasm'));
const scalar = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));
const simd = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive-simd.wasm', import.meta.url)));
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));

test('candidate cache retains continuation state and a bounded packet-key budget',
  {skip:!process.env.LPX_UNIFICATION_SELFTEST},async()=>{
    for(const mode of ['scalar','simd']) {
      const binary=readFileSync(new URL(`../../build/lpx-unification-${mode}.wasm`,import.meta.url));
      const {instance}=await WebAssembly.instantiate(binary);instance.exports.__wasm_call_ctors();
      for(let i=0;i<3;++i)assert.equal(instance.exports.unification_selftest(),0);
    }
  });

test('precision, strict bitrate and legacy control budgets remain distinct', () => {
  for(const level of [3,4,6,8]) {
    const accuracy=encodingPolicy(level,true);
    assert.equal(accuracy.accuracyLevel,level);assert.equal(accuracy.targetBitrate,0);
    assert.equal(accuracy.budgetKind,'accuracy-allocation');
  }
  for(const kbps of [3,8]) {
    const strict=encodingPolicy(kbps);
    assert.equal(strict.accuracyLevel,0);assert.equal(strict.budgetKind,'complete-v9');
    assert.equal(bitrateBudget(65537,strict,8000),Math.floor(65537*kbps/64));
  }
  for(const profile of [4,6])assert.equal(encodingPolicy(profile).budgetKind,'v5-control');
});

test('shared encoder refactoring retains complete accuracy bytes and PCM', () => {
  const signals = [new Int16Array(41),
    Int16Array.from({length:321}, (_,i)=>Math.round(7000*Math.sin(i*.17)+2000*Math.sin(i*.037))),
    Int16Array.from({length:161}, (_,i)=>i&1?32767:-32768)];
  for (const pcm of signals) for (const rate of [8000,12000,16000]) for (const level of [3,4,6,8]) {
    const options={accuracy:true,calls:4};
    let expected, failure;
    try { expected=baseline(pcm,rate,level,()=>{},options); }
    catch(error) { failure=error.message; }
    for (const encode of [scalar,simd]) {
      if(failure) { assert.throws(()=>encode(pcm,rate,level,()=>{},options),{message:failure});continue; }
      const actual=encode(pcm,rate,level,()=>{},options);
      assert.deepEqual(actual,expected,`P${level}/${rate}/${pcm.length}`);
      assert.deepEqual(decode(actual).pcm,decode(expected).pcm);
    }
  }
});
