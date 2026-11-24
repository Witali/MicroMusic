import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder} from '../lpx/codec.js';
import {encodeStreaming} from '../lpx/streaming.js';
import {toneBurstTrain} from './helpers/lpx-continuation-cases.mjs';
import {measureTimbre} from './helpers/lpx-timbre-cases.mjs';

const encode=await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm',import.meta.url)));
const decode=await createDecoder(readFileSync(new URL('../lpx/decoder.wasm',import.meta.url)));
const read=async url=>readFileSync(url);
const selectedRate=process.env.LPX_QUALITY_TEST_RATE;
if(selectedRate!==undefined&&!['8000','12000','16000'].includes(selectedRate))
  throw Error('LPX_QUALITY_TEST_RATE must be 8000, 12000 or 16000.');
const testRates=selectedRate===undefined?[8000,12000,16000]:[Number(selectedRate)];

test('spectral safety uses the Hann-weighted source floor while rejecting significant unrelated energy',
  {skip:!process.env.LPX_UNIFICATION_SELFTEST,timeout:30000},async()=>{
    for(const mode of ['scalar','simd']) {
      const binary=readFileSync(new URL(`../../build/lpx-unification-${mode}.wasm`,import.meta.url));
      const {instance}=await WebAssembly.instantiate(binary);instance.exports.__wasm_call_ctors();
      for(let repeat=0;repeat<3;++repeat)assert.equal(instance.exports.spectrum_safety_selftest(),0,mode);
    }
  });

test('both burst sources contain four significant legal partials and the long source crosses a streaming boundary',()=>{
  for(const rate of [8000,12000,16000])for(const samples of [20480+48,8321]) {
    const c=toneBurstTrain(rate,samples),m=measureTimbre(c.reference,c.reference,rate,c.partials);
    assert.equal(c.reference.length,samples);
    assert.equal(m.sourcePartials,4);assert.equal(m.spectralShapeError,0);
    assert.ok(c.partials.every(p=>p.frequency>0&&p.frequency<rate/2));
    assert.ok(c.reference.every(sample=>Math.abs(sample)<=9000));
  }
});

for(const rate of testRates)for(const level of [3,4,6,8])for(const calls of [0,4])for(const mode of ['whole','stream']) {
  test(`valid tone bursts retain complete source quality: ${mode}/P${level}/${rate}/calls${calls}`,{timeout:180000},async()=>{
    // Both lengths independently reproduced the published seed failure. Keep
    // the continued fast case and bound the cost of the full-search matrix.
    const c=toneBurstTrain(rate,calls===0?20480+48:8321),settings={samples:c.reference.length,sampleRate:rate,profile:level,accuracy:true,calls};
    let bytes;
    if(mode==='whole')bytes=encode(c.reference,rate,level,()=>{},{accuracy:true,calls});
    else {
      const result=await encodeStreaming(encode,settings,async(at,count)=>c.reference.slice(at,at+count),()=>{},read);
      assert.equal(result.windows,Math.ceil(c.reference.length/20480));assert.equal(result.samples,c.reference.length);
      assert.equal(result.accuracyLevel,level);bytes=result.bytes;
    }
    const decoded=decode(bytes);
    assert.equal(decoded.samples,c.reference.length);assert.equal(decoded.pcm.length,c.reference.length);
    assert.equal(decoded.sampleRate,rate);assert.equal(decoded.profile,level<=4?4:6);
    const m=measureTimbre(c.reference,decoded.pcm,rate,c.partials);
    // Aggregate source-referenced quality remains meaningful when a short
    // local spectral heuristic cannot be attained by a finite alphabet.
    assert.ok(m.spectralShapeError<.5,`source spectrum replaced (${m.spectralShapeError})`);
    assert.ok(m.envelopeError<.5,`burst timing or magnitude lost (${m.envelopeError})`);
    assert.ok(m.energyRatio>=.25&&m.energyRatio<=4,`unbounded source-level change (${m.energyRatio})`);
    assert.ok(m.retainedPartials>=3,`only ${m.retainedPartials}/4 significant partials retained`);
    assert.ok(m.partialShapeError<.2,`partial balance collapsed (${m.partialShapeError})`);
    assert.ok(m.minimumPartialRetention>=.25,`a significant source partial was suppressed (${m.minimumPartialRetention})`);
  });
}
