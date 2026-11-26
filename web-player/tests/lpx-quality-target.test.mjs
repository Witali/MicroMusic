import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { qualityTargetCode, callQualityEncoder } from '../lpx/quality-target.js';
import { createEncoder } from '../lpx/encoder.js';
import { createStreamSession, encodeStreaming } from '../lpx/streaming.js';
import { createDecoder } from '../lpx/codec.js';

const bytes = name => readFileSync(new URL(`../lpx/${name}.wasm`, import.meta.url));
const tone = n => Int16Array.from({length:n}, (_,i) => Math.round(1800*Math.sin(i*.143)+350*Math.sin(i*.057)));

test('quality target validation and legacy compatibility never ignore an explicit PCM request', async () => {
  assert.equal(qualityTargetCode(),1);
  assert.equal(qualityTargetCode('pwm'),1); assert.equal(qualityTargetCode('pcm'),0);
  for (const invalid of [null,'PCM','',0,1,false,{},[]]) assert.throws(() => qualityTargetCode(invalid), /PCM/);
  const calls = [];
  const api = { enc_accuracy:(...args)=>{calls.push(['legacy',...args]);return 13;},
    enc_accuracy_target:(...args)=>{calls.push(['explicit',...args]);return 14;} };
  assert.equal(callQualityEncoder(api,'enc_accuracy',[4,6],0),14);
  assert.deepEqual(calls.pop(),['explicit',4,6,0]);
  delete api.enc_accuracy_target;
  assert.equal(callQualityEncoder(api,'enc_accuracy',[4,6],1),13);
  assert.throws(()=>callQualityEncoder(api,'enc_accuracy',[4,6],0), /WASM.*PCM/);
  const legacy = await createEncoder(bytes('encoder'));
  assert.throws(()=>legacy(tone(321),8000,6,undefined,{qualityTarget:'pcm'}), /WASM.*PCM/);
  assert.throws(()=>legacy(tone(321),8000,6,undefined,{qualityTarget:null}), /PCM/);
});

test('stream creation captures the selected target and rejects stale or invalid settings before dispatch', () => {
  const calls=[];
  const api={enc_stream_create:()=>1,enc_stream_create_accuracy:()=>1,enc_stream_window:()=>20480,
    enc_stream_create_target:(...args)=>{calls.push(args);return 1;},
    enc_stream_create_accuracy_target:(...args)=>{calls.push(args);return 1;}};
  const settings={samples:641,profile:6,sampleRate:16000,calls:0};
  for(const accuracy of [false,true]) for(const qualityTarget of [undefined,'pwm','pcm']) {
    const session=createStreamSession(api,{...settings,accuracy,qualityTarget});
    assert.equal(calls.at(-1).at(-1),qualityTarget==='pcm'?0:1);
    assert.equal(session.qualityTarget,qualityTarget??'pwm');
  }
  const count=calls.length;
  assert.throws(()=>createStreamSession(api,{...settings,qualityTarget:'unknown'}),/PCM/);
  assert.equal(calls.length,count);
  delete api.enc_stream_create_target;
  assert.throws(()=>createStreamSession(api,{...settings,qualityTarget:'pcm'}),/WASM.*PCM/);
});

test('shipped scalar/SIMD APIs preserve PWM defaults and accept PCM in short accuracy and normalization paths', async () => {
  const pcm=tone(1281), decode=await createDecoder(bytes('decoder'));
  const outputs=[];
  for(const name of ['encoder-adaptive','encoder-adaptive-simd']) {
    const encode=await createEncoder(bytes(name));
    const settings={accuracy:true,calls:0};
    const original=encode(pcm,16000,6,undefined,settings);
    assert.deepEqual(encode(pcm,16000,6,undefined,{...settings,qualityTarget:'pwm'}),original);
    const native=encode(pcm,16000,6,undefined,{...settings,qualityTarget:'pcm'});
    assert.equal(decode(native).pcm.length,pcm.length);
    const normalized=encode(pcm,16000,6,undefined,{...settings,qualityTarget:'pcm',normalization:'loudness',targetLufs:-24,maxGainDb:9});
    assert.equal(decode(normalized).pcm.length,pcm.length);
    assert.ok(encode.loudness);
    assert.deepEqual(encode(pcm,16000,6,undefined,settings),original,'PCM policy does not leak into the next default encode');
    assert.throws(()=>encode(pcm,16000,6,undefined,{qualityTarget:'bad'}),/PCM/);
    outputs.push({native,normalized});
  }
  assert.deepEqual(outputs[0],outputs[1]);
});

test('PCM quality sessions survive window continuation and complete refinement admission on both backends', async () => {
  const results=[];
  for(const name of ['encoder-adaptive','encoder-adaptive-simd']) {
    const encode=await createEncoder(bytes(name));
    const run=async(pcm,calls)=>encodeStreaming(encode,
      {samples:pcm.length,profile:6,sampleRate:16000,accuracy:true,calls,qualityTarget:'pcm'},
      async(offset,count)=>pcm.slice(offset,offset+count),()=>{},async url=>readFileSync(url));
    const continued=await run(tone(20481),0);
    assert.equal(continued.windows,2);assert.equal(continued.qualityTarget,'pcm');
    const refined=await run(tone(1281),1);
    assert.equal(refined.qualityTarget,'pcm');assert.equal(refined.memoryFallback,false);
    results.push({continued:continued.bytes,refined:refined.bytes});
  }
  assert.deepEqual(results[0],results[1]);
});
