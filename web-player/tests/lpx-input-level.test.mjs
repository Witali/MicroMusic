import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder,parseHeader} from '../lpx/codec.js';
import {readRecordedBuildFile} from './helpers/recorded-build-source.mjs';
import {loudnessCases} from './helpers/lpx-loudness-cases.mjs';

const binaries=['encoder-adaptive','encoder-adaptive-simd'].map(n=>readFileSync(new URL(`../lpx/${n}.wasm`,import.meta.url)));
const apis=await Promise.all(binaries.map(async b=>{const {instance}=await WebAssembly.instantiate(b);instance.exports.__wasm_call_ctors();return instance.exports;}));
const encoders=await Promise.all(binaries.map(createEncoder));
const revision='f282950c44f01793f55e2fad6c4fe5cf66cdfd2f';
const old=await createEncoder(readRecordedBuildFile(revision,'web-player/lpx/encoder-adaptive.wasm'));
const oldDecode=await createDecoder(readRecordedBuildFile(revision,'web-player/lpx/decoder.wasm'));
function prepare(api,pcm,rate,target,max) {
  assert.ok(api.enc_reserve(pcm.length));new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(pcm);
  const status=api.enc_normalize_level(pcm.length,rate,target,max);assert.ok(status>0);
  return {pcm:new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).slice(),status,
    input:api.enc_loudness_input(),prepared:api.enc_loudness_prepared(),gainDb:api.enc_loudness_gain_db(),
    peakLimited:!!api.enc_loudness_limited(),gainLimited:!!api.enc_loudness_gain_limited()};
}
test('configurable input normalization matches independent constant scaling and both WASM backends',()=>{
  for(const c of loudnessCases())for(const [target,max] of [[-30,0],[-18,12],[-9,24]]) {
    const a=prepare(apis[0],c.pcm,c.rate,target,max),b=prepare(apis[1],c.pcm,c.rate,target,max);
    assert.deepEqual(a,b);assert.equal(a.pcm.length,c.pcm.length);
    if(a.status!==1){assert.deepEqual(a.pcm,c.pcm);continue;}
    let peak=0;for(const x of c.pcm)peak=Math.max(peak,Math.abs(x));
    const factor=Math.min(10**((target-a.input)/20),10**(max/20),29204/peak);
    const expected=Int16Array.from(c.pcm,x=>Math.max(-29204,Math.min(29204,Math.sign(x)*Math.floor(Math.abs(x*factor)+.5))));
    assert.deepEqual(a.pcm,expected);assert.ok(a.gainDb<=max+1e-10);
    if(!a.peakLimited&&!a.gainLimited)assert.ok(Math.abs(a.prepared-target)<.05);
    if(process.env.LPX_LOUDNESS_NATIVE && ['quiet','peak-limited','noise'].includes(c.name)) {
      const r=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_LOUDNESS_NATIVE,String(c.rate),String(target),String(max)],{input:Buffer.from(c.pcm.buffer),maxBuffer:1024*1024});
      assert.equal(r.status,0,r.stderr?.toString());assert.deepEqual(r.stdout,Buffer.from(a.pcm.buffer));
    }
  }
});
test('configured normalization encodes prepared PCM into ordinary files accepted by the prior decoder',()=>{
  for(const profile of [3,4,6,8])for(const rate of profile===3||profile===8?[8000]:[8000,12000,16000]) {
    const pcm=Int16Array.from({length:rate/2+1},(_,i)=>Math.round(800*Math.sin(i*.14))),source=pcm.slice();
    const options={normalization:'loudness',targetLufs:-24,maxGainDb:9};
    // Normalization must feed the current quality search exactly the prepared
    // PCM. The frozen encoder is a wire-reader reference, not a quality oracle
    // after independently validated search improvements.
    const preserved=encoders[0](pcm,rate,profile);
    const normalized=prepare(apis[0],pcm,rate,-24,9).pcm,expected=encoders[0](normalized,rate,profile);
    for(const encode of encoders){
      const actual=encode(pcm,rate,profile,()=>{},options);
      assert.deepEqual(actual,expected,'same quality search and original complete budget');
      assert.equal(actual[2]&32,0);assert.equal(oldDecode(actual).samples,pcm.length);
      assert.equal(actual.length,13+new DataView(actual.buffer,actual.byteOffset).getUint16(11,true));
      if(profile===3||profile===8)assert.ok(actual.length<=Math.floor(pcm.length*profile/64));
      assert.deepEqual(encode(pcm,rate,profile),preserved);assert.equal(encode.loudness,null);
    }
    assert.deepEqual(pcm,source);
  }
});
test('configured normalization retains one Long stream and rejects invalid settings and removed gain syntax',()=>{
  const pcm=Int16Array.from({length:65537},(_,i)=>Math.round((i<32000?300:900)*Math.sin(i*.14)));
  const normalized=prepare(apis[0],pcm,12000,-21,12).pcm;
  for(const api of apis){
    assert.ok(api.enc_reserve(pcm.length));new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(pcm);
    const size=api.enc_adaptive_level(pcm.length,6,12000,0,0,0,1,-21,12);assert.ok(size>17);
    const actual=new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),size).slice();
    assert.ok(parseHeader(actual).long);assert.equal(actual[2]&32,0);assert.equal(oldDecode(actual).samples,pcm.length);
    assert.ok(api.enc_reserve(normalized.length));new Int16Array(api.memory.buffer,api.enc_input(),normalized.length).set(normalized);
    const plainSize=api.enc_adaptive_extended(normalized.length,6,12000,0,0,0,0);
    assert.deepEqual(actual,new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),plainSize).slice());
    for(const [target,max] of [[-31,12],[-8,12],[-18,-1],[-18,25]])assert.equal(api.enc_normalize_level(pcm.length,12000,target,max),-1);
  }
  const short=new Int16Array(641);
  for(const options of [{targetLufs:NaN},{targetLufs:-31},{maxGainDb:.5},{maxGainDb:25}])assert.throws(()=>encoders[0](short,8000,6,()=>{},{normalization:'loudness',...options}),/настройки/);
  assert.throws(()=>encoders[0](short,8000,6,()=>{},{normalization:'file'}),/режим громкости/);
  const marked=old(short,8000,4);marked[2]|=32;assert.throws(()=>parseHeader(marked));
});
