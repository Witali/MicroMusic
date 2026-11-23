import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createEncoder} from '../lpx/encoder.js';
import {createDecoder,parseHeader} from '../lpx/codec.js';
import {readRecordedBuildFile} from './helpers/recorded-build-source.mjs';

const binaries=['encoder-adaptive','encoder-adaptive-simd'].map(n=>readFileSync(new URL(`../lpx/${n}.wasm`,import.meta.url)));
const encoders=await Promise.all(binaries.map(createEncoder));
const decode=await createDecoder(readFileSync(new URL('../lpx/decoder.wasm',import.meta.url)));
const tone=(n,amp=3000)=>Int16Array.from({length:n},(_,i)=>Math.round(amp*Math.sin(i*.14)+amp*.17*Math.sin(i*.31)));
function attach(bytes,gain) {
  const header=bytes[2]&64?17:13,result=new Uint8Array(bytes.length+2);
  result.set(bytes.subarray(0,header));result[2]|=32;result[header]=gain;result[header+1]=gain>>8;result.set(bytes.subarray(header),header+2);return result;
}
function scaled(pcm,gain) {return Int16Array.from(pcm,x=>Math.max(-32768,Math.min(32767,2*Math.max(-16384,Math.min(16384,Math.floor(((x===32767?16384:x/2)*gain+2048)/4096))))));}
test('portable signed and short-unsigned gain products are equivalent across 720904 cases', {skip:!process.env.LPX_FILE_GAIN_SELFTEST},async()=>{
  const {instance}=await WebAssembly.instantiate(readFileSync(process.env.LPX_FILE_GAIN_SELFTEST));
  assert.equal(instance.exports.lpx_file_gain_selftest(),720904);
});

test('optional Q4.12 file gain changes only final output, including sparse and Long',async()=>{
  const raw=await createEncoder(readFileSync(new URL('../lpx/encoder.wasm',import.meta.url)));
  const clips=[raw(tone(641),8000,4),raw(tone(961),16000,6),raw(tone(65537),12000,6),
    readFileSync(new URL('../audio/lpx-speech/chego/quality.v9.lpx',import.meta.url)),
    readFileSync(new URL('../audio/lpx-bread/low15.v9.lpx',import.meta.url))];
  const native=[];
  for(const bytes of clips)for(const gain of [1,256,2048,4096,8192,64916,65535]) {
    const modified=attach(bytes,gain),actual=decode(modified),expected=scaled(decode(bytes).pcm,gain);
    assert.equal(parseHeader(modified).gainQ12,gain);assert.deepEqual(actual.pcm,expected);
    assert.equal(actual.samples,decode(bytes).samples);assert.equal(actual.hasGain,true);native.push(modified);
  }
  if(process.env.LPX_FILE_GAIN_NATIVE) {
    const input=Buffer.concat(native.flatMap(bytes=>{const n=Buffer.alloc(4);n.writeUInt32LE(bytes.length);return [n,bytes];}));
    const result=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_FILE_GAIN_NATIVE],{input,maxBuffer:16*1024*1024});
    assert.equal(result.status,0,result.stderr?.toString());let offset=0;
    for(const bytes of native) {const size=result.stdout.readUInt32LE(offset);offset+=4;assert.deepEqual(result.stdout.subarray(offset,offset+size),Buffer.from(decode(bytes).pcm.buffer));offset+=size;}
    assert.equal(offset,result.stdout.length);
  }
  const previous=await createDecoder(readRecordedBuildFile('f282950c44f01793f55e2fad6c4fe5cf66cdfd2f','web-player/lpx/decoder.wasm'));
  assert.throws(()=>previous(attach(clips[0],8192)),'older readers reject the marked extension');
  const bad=attach(clips[0],0);assert.throws(()=>decode(bad));assert.throws(()=>decode(attach(clips[0],4096).subarray(0,14)));
  assert.deepEqual(decode(clips[0]).pcm,decode(clips[0]).pcm,'ordinary decode remains usable after errors');
});

test('file normalization stores a bounded whole-recording coefficient and preserves the ordinary payload',()=>{
  const pcm=tone(8001,300),options={normalization:'file',targetLufs:-18,maxGainDb:12};
  for(const profile of [4,6]) {
    const control=encoders[0](pcm,8000,profile),results=[];
    for(const encode of encoders) {
      const bytes=encode(pcm,8000,profile,()=>{},options),meta=parseHeader(bytes),report=encode.loudness;
      assert.equal(bytes.length,control.length+2);assert.deepEqual(bytes.subarray(15),control.subarray(13),'coded payload is unchanged');
      assert.ok(meta.gainQ12<=Math.floor(4096*10**(12/20)));assert.ok(report.gainDb<=12);
      assert.deepEqual(decode(bytes).pcm,scaled(decode(control).pcm,meta.gainQ12));
      assert.ok(decode(bytes).pcm.every(x=>Math.abs(x)<=29204));assert.equal(report.fileGain,true);assert.ok(report.gainLimited);
      results.push(bytes);
      const limited=encode(tone(8001,20000),8000,profile,()=>{},{...options,targetLufs:-9,maxGainDb:24});
      assert.ok(decode(limited).pcm.every(x=>Math.abs(x)<=29204),'decoded-peak ceiling');
    }
    assert.deepEqual(results[0],results[1]);
  }
});

test('level switch and target/max-gain settings preserve all four profiles and strict caps',()=>{
  const pcm=tone(6401,3000);
  for(const profile of [3,4,6,8]) {
    const control=encoders[0](pcm,8000,profile),results=[];
    for(const encode of encoders) {
      const low=encode(pcm,8000,profile,()=>{},{normalization:'file',targetLufs:-27,maxGainDb:24});
      const lowReport=encode.loudness;
      const high=encode(pcm,8000,profile,()=>{},{normalization:'file',targetLufs:-18,maxGainDb:24});
      assert.ok(encode.loudness.decoded>lowReport.decoded+2,'target slider changes whole-file level');
      assert.equal(parseHeader(high).hasGain,true);
      if(profile===3||profile===8)assert.ok(high.length<=Math.floor(pcm.length*profile/64));
      assert.deepEqual(encode(pcm,8000,profile,()=>{},{normalization:'preserve'}),control,'disabled means original level and bytes');
      assert.equal(encode.loudness,null);results.push(high);
    }
    assert.deepEqual(results[0],results[1]);
  }
  for(const encode of encoders)for(const options of [{targetLufs:-31},{targetLufs:-8},{targetLufs:NaN},{maxGainDb:-1},{maxGainDb:25},{maxGainDb:.5}]) {
    assert.throws(()=>encode(pcm,8000,6,()=>{},{normalization:'file',...options}),/настройки/);
  }
});
