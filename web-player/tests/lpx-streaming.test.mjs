import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createEncoder} from '../lpx/encoder.js';
import {encodeStreaming,createStreamSession} from '../lpx/streaming.js';
import {createDecoder,parseHeader} from '../lpx/codec.js';

const paths=['encoder-adaptive','encoder-adaptive-simd'];
const load=async name=>createEncoder(readFileSync(new URL(`../lpx/${name}.wasm`,import.meta.url)));
const decoder=await createDecoder(readFileSync(new URL('../lpx/decoder.wasm',import.meta.url)));
const tone=n=>Int16Array.from({length:n},(_,i)=>Math.round((i<21000?900:3000)*Math.sin(i*.14)+200*Math.sin(i*.073)));
const binary=async url=>readFileSync(url);
async function run(name,pcm,settings={}){
  const progress=[],reads=[];
  const result=await encodeStreaming(await load(name),{samples:pcm.length,profile:6,sampleRate:8000,...settings},
    async(offset,count)=>{assert.ok(count<=20528);reads.push([offset,count]);return pcm.slice(offset,offset+count);},
    (phase,value)=>progress.push([phase,value]),binary);
  assert.equal(result.samples,pcm.length);assert.equal(decoder(result.bytes).pcm.length,pcm.length);
  assert.equal(result.bytes[2]&32,0);assert.equal(progress.at(-1)[1],1);
  for(let i=1;i<progress.length;i++)assert.ok(progress[i][1]>=progress[i-1][1],'monotonic progress');
  return {result,reads,progress};
}
test('streaming scalar/SIMD produces one verified file with all four profiles and original final caps',async()=>{
  const pcm=tone(4001);
  for(const profile of [3,4,6,8]){
    const a=await run(paths[0],pcm,{profile}),b=await run(paths[1],pcm,{profile});
    assert.deepEqual(a.result.bytes,b.result.bytes);
    assert.equal(a.result.memoryFallback,false);assert.equal(a.result.windows,1);
    if(profile===3||profile===8)assert.ok(a.result.bytes.length<=Math.floor(pcm.length*profile/64));
    if(process.env.LPX_STREAM_NATIVE){
      const native=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_STREAM_NATIVE,String(profile),'8000','0','-18','12','4'],{input:Buffer.from(pcm.buffer),maxBuffer:1024*1024});
      assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(a.result.bytes));
    }
  }
});
test('streaming input normalization keeps one whole-recording gain at actual 8/12/16 kHz',async()=>{
  const pcm=tone(8001);
  for(const sampleRate of [8000,12000,16000]){
    const settings={sampleRate,normalization:'loudness',targetLufs:-24,maxGainDb:9};
    const a=await run(paths[0],pcm,settings),b=await run(paths[1],pcm,settings);
    assert.deepEqual(a.result.bytes,b.result.bytes);assert.deepEqual(a.result.loudness,b.result.loudness);
    assert.equal(a.result.loudness.status,1);assert.ok(a.result.loudness.gainDb<=9);assert.ok(a.progress.some(p=>p[0]==='measure'));
    if(process.env.LPX_STREAM_NATIVE){
      const native=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_STREAM_NATIVE,'6',String(sampleRate),'1','-24','9','4'],{input:Buffer.from(pcm.buffer),maxBuffer:1024*1024});
      assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(a.result.bytes));
    }
  }
});
test('continued Long output retains bounded model memory across many input windows',async()=>{
  let first=0;
  for(const length of [65537,1048577]){
    const {result,reads}=await run(paths[0],new Int16Array(length),{calls:0});
    assert.equal(parseHeader(result.bytes).long,true);assert.ok(decoder(result.bytes).pcm.every(x=>x===0));
    assert.equal(result.windows,Math.ceil(length/20480));assert.ok(reads.length>=result.windows);
    assert.ok(result.workingMemoryBytes<32*1024*1024);
    if(first)assert.ok(result.workingMemoryBytes<=first+1024*1024);first=result.workingMemoryBytes;
  }
});
test('continued adaptive refinement verifies boundary history and can be repeated without a poisoned instance',async()=>{
  const pcm=tone(40961),a=await run(paths[0],pcm),b=await run(paths[1],pcm);
  assert.deepEqual(a.result.bytes,b.result.bytes);assert.equal(a.result.windows,3);assert.equal(a.result.memoryFallback,false);
  if(process.env.LPX_STREAM_NATIVE){
    const native=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_STREAM_NATIVE,'6','8000','0','-18','12','4'],{input:Buffer.from(pcm.buffer),maxBuffer:1024*1024});
    assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(a.result.bytes));
  }
  const encode=await load(paths[0]);
  assert.throws(()=>encode.createStream({samples:641,profile:3,sampleRate:12000}),/8 кГц/);
  assert.throws(()=>encode.createStream({samples:641,profile:6,sampleRate:8000,maxGainDb:25}),/настройки/);
  const session=encode.createStream({samples:641,profile:6,sampleRate:8000,calls:0});
  assert.throws(()=>session.finish(),/окончание/);
  const ordinary=encode(new Int16Array(641),8000,6);assert.equal(decoder(ordinary).samples,641);
});

test('a single normalized gain spans all windows and equals whole-input loudness planning',async()=>{
  const pcm=tone(40961),settings={normalization:'loudness',targetLufs:-24,maxGainDb:9,calls:0};
  const {result}=await run(paths[0],pcm,settings);
  const {instance}=await WebAssembly.instantiate(readFileSync(new URL('../lpx/encoder-adaptive.wasm',import.meta.url)));
  const api=instance.exports;api.__wasm_call_ctors();assert.ok(api.enc_reserve(pcm.length));
  new Int16Array(api.memory.buffer,api.enc_input(),pcm.length).set(pcm);
  assert.equal(api.enc_normalize_level(pcm.length,8000,-24,9),1);
  assert.equal(result.loudness.input,api.enc_loudness_input());assert.equal(result.loudness.prepared,api.enc_loudness_prepared());
  assert.equal(result.loudness.gainDb,api.enc_loudness_gain_db());assert.equal(result.windows,3);
});

test('final admission allocation failure retains the completely decoded control',async()=>{
  const {instance}=await WebAssembly.instantiate(readFileSync(new URL('../lpx/encoder-adaptive.wasm',import.meta.url)));
  instance.exports.__wasm_call_ctors();let failed=false;
  const api={...instance.exports,enc_stream_verify_put(){failed=true;throw new WebAssembly.RuntimeError('allocation probe');},enc_allocation_failed:()=>failed?1:0};
  const pcm=tone(4001),fake={createStream:settings=>createStreamSession(api,settings)};
  const result=await encodeStreaming(fake,{samples:pcm.length,profile:6,sampleRate:8000},async(o,n)=>pcm.slice(o,o+n),()=>{},binary);
  const control=await run(paths[0],pcm,{calls:0});
  assert.equal(result.memoryFallback,true);assert.equal(result.usedControl,true);
  assert.deepEqual(result.bytes,control.result.bytes);assert.equal(decoder(result.bytes).samples,pcm.length);
});
