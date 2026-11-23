import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder,parseHeader} from '../lpx/codec.js';
import {readRecordedBuildFile} from './helpers/recorded-build-source.mjs';
import {loudnessCases} from './helpers/lpx-loudness-cases.mjs';

const binaries=['encoder-adaptive','encoder-adaptive-simd'].map(name=>readFileSync(new URL(`../lpx/${name}.wasm`,import.meta.url)));
const apis=await Promise.all(binaries.map(async binary=>{const {instance}=await WebAssembly.instantiate(binary);instance.exports.__wasm_call_ctors();return instance.exports;}));
const wrappers=await Promise.all(binaries.map(createEncoder));
const cases=loudnessCases();
const reference=JSON.parse(readFileSync(new URL('./fixtures/lpx-loudness-reference.json',import.meta.url)));
const decode=await createDecoder(readFileSync(new URL('../lpx/decoder.wasm',import.meta.url)));
function normalize(api,pcm,rate,settings) {
  assert.ok(api.enc_reserve(pcm.length));new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(pcm);
  const status=settings?api.enc_normalize_level(pcm.length,rate,settings.targetLufs,settings.maxGainDb):api.enc_normalize_loudness(pcm.length,rate);assert.ok(status>0);
  return {pcm:new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).slice(),report:{status,limited:api.enc_loudness_limited(),input:api.enc_loudness_input(),prepared:api.enc_loudness_prepared(),gainDb:api.enc_loudness_gain_db()}};
}

test('shared mono LUFS agrees with 42 independent libebur128 measurements at all rates',()=>{
  assert.equal(reference.cases.length,cases.length);
  for(let i=0;i<cases.length;i++) {
    const c=cases[i],expected=reference.cases[i];assert.equal(c.name,expected.name);assert.equal(c.rate,expected.rate);
    const results=apis.map(api=>normalize(api,c.pcm,c.rate));assert.deepEqual(results[1],results[0]);
    const {pcm,report}=results[0];
    if(expected.lufs===null)assert.equal(report.input,-Infinity);
    else assert.ok(Math.abs(report.input-expected.lufs)<1e-6,`${c.name}/${c.rate}: ${report.input} vs ${expected.lufs}`);
    if(report.status===1) {
      assert.ok(pcm.every(x=>Math.abs(x)<=29204),'normalized sample-peak ceiling');
      if(!report.limited)assert.ok(Math.abs(report.prepared+18)<.05,`${c.name}: target loudness`);
      if(c.name==='peak-limited')assert.equal(report.limited,1);
    } else { assert.deepEqual(pcm,c.pcm);assert.equal(report.gainDb,0); }
  }
});

test('normalization preserves pauses, polarity and the full continuous recording',()=>{
  for(const rate of [8000,12000,16000]) {
    const c=cases.find(c=>c.rate===rate&&c.name==='pauses'),result=normalize(apis[0],c.pcm,rate);
    for(let i=0;i<c.pcm.length;i++)if(!c.pcm[i])assert.equal(result.pcm[i],0);
    assert.equal(result.pcm.length,c.pcm.length);
    assert.ok(result.report.gainDb>0);
    const inverse=normalize(apis[0],Int16Array.from(c.pcm,x=>-x),rate);
    assert.deepEqual(inverse.pcm,Int16Array.from(result.pcm,x=>-x));
    const amplified=normalize(apis[0],Int16Array.from(c.pcm,x=>x*2),rate);
    assert.ok(Math.abs(amplified.report.prepared-result.report.prepared)<.005,'different source levels converge');
  }
});

test('opt-in normalization uses the shared controller, reports decoded LUFS and keeps default bytes',async()=>{
  const old=await createEncoder(readRecordedBuildFile('18be72f12e202906f33cb7abd8fd001d3c806b4a','web-player/lpx/encoder-adaptive.wasm'));
  const c=cases.find(c=>c.rate===8000&&c.name==='quiet'),source=c.pcm.slice(),results=[];
  for(const profile of [4,6]) {
    const expected=old(c.pcm,c.rate,profile);
    for(const encode of wrappers) {
      assert.deepEqual(encode(c.pcm,c.rate,profile),expected,'preserve remains the exact default');assert.equal(encode.loudness,null);
      const bytes=encode(c.pcm,c.rate,profile,()=>{},{normalization:'loudness'});
      assert.equal(decode(bytes).samples,c.pcm.length);assert.equal(encode.loudness.status,1);
      assert.ok(Math.abs(encode.loudness.prepared-encode.loudness.input-12)<.05);
      assert.equal(encode.loudness.gainLimited,true);
      assert.ok(Number.isFinite(encode.loudness.decoded));assert.notDeepEqual(bytes,expected);
      const normalized=normalize(apis[0],c.pcm,c.rate,{targetLufs:-18,maxGainDb:12}).pcm;
      assert.deepEqual(bytes,old(normalized,c.rate,profile),'quality gates use the normalized reference');
      results.push(bytes);
      assert.throws(()=>encode(c.pcm,c.rate,profile,()=>{},{normalization:'unknown'}),/режим громкости/);
    }
  }
  assert.deepEqual(results[0],results[1]);assert.deepEqual(results[2],results[3]);assert.deepEqual(c.pcm,source,'caller input remains unchanged');
});

test('native and WASM normalization retain exactly the same PCM', {skip:!process.env.LPX_LOUDNESS_NATIVE},()=>{
  for(const c of cases) {
    const actual=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_LOUDNESS_NATIVE,String(c.rate)],{input:Buffer.from(c.pcm.buffer),maxBuffer:1024*1024});
    assert.equal(actual.status,0,actual.stderr?.toString());
    assert.deepEqual(actual.stdout,Buffer.from(normalize(apis[0],c.pcm,c.rate).pcm.buffer),`${c.name}/${c.rate}`);
  }
});

test('normalization precedes one continuous V9 Long encode without resetting gain',()=>{
  const pcm=Int16Array.from({length:65537},(_,i)=>Math.round((i<32000?500:2000)*Math.sin(i*.14)));
  const results=[];
  for(const api of apis) {
    assert.ok(api.enc_reserve(pcm.length));new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(pcm);
    const size=api.enc_adaptive_loudness(pcm.length,6,12000,0,0,0,1);assert.ok(size>13);
    const bytes=new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),size).slice();
    assert.ok(parseHeader(bytes).long);assert.equal(decode(bytes).pcm.length,pcm.length);
    const gain=api.enc_loudness_gain_db(),prepared=normalize(api,pcm,12000);assert.equal(prepared.report.gainDb,gain);
    assert.ok(api.enc_reserve(pcm.length));new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(prepared.pcm);
    const expectedSize=api.enc_adaptive_extended(pcm.length,6,12000,0,0,0,0);
    assert.deepEqual(bytes,new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),expectedSize).slice());results.push(bytes);
  }
  assert.deepEqual(results[0],results[1]);
});

test('3/8 bitrate presets normalize their reference before selection and retain exact file caps',async()=>{
  const previous=await createEncoder(readRecordedBuildFile('6ef6899b698dd7cf0449ce2b2d3775bd4d3684da','web-player/lpx/encoder-adaptive.wasm'));
  const c=cases.find(c=>c.rate===8000&&c.name==='quiet'),prepared=normalize(apis[0],c.pcm,c.rate,{targetLufs:-18,maxGainDb:12}).pcm;
  for(const kbps of [3,8]) {
    const expected=previous(prepared,c.rate,kbps),preserved=previous(c.pcm,c.rate,kbps),results=[];
    for(const encode of wrappers) {
      assert.deepEqual(encode(c.pcm,c.rate,kbps),preserved,'existing preset output remains unchanged');
      const bytes=encode(c.pcm,c.rate,kbps,()=>{},{normalization:'loudness'});
      assert.deepEqual(bytes,expected,'preset quality gates use normalized PCM');
      assert.ok(bytes.length<=Math.floor(c.pcm.length*kbps*1000/(8*c.rate)));
      assert.equal(decode(bytes).samples,c.pcm.length);assert.equal(encode.loudness.status,1);
      assert.ok(Math.abs(encode.loudness.prepared-encode.loudness.input-12)<.05);assert.ok(Number.isFinite(encode.loudness.decoded));
      results.push(bytes);
    }
    assert.deepEqual(results[0],results[1]);
  }
});
