import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {MAX_SAMPLES,MAX_STREAM_SAMPLES,MAX_DECODE_SAMPLES,MAX_FILE_BYTES,parseHeader,createIncrementalDecoder,streamingSampleLimit} from '../lpx/codec.js';
import {createStreamSession} from '../lpx/streaming.js';
import {qualityTargetCode} from '../lpx/quality-target.js';
import {decodePackets,prepareAudio} from '../lpx/audio-source.js';

const root=new URL('../lpx/',import.meta.url),binary=name=>readFileSync(new URL(name,root));
const header=samples=>{
  const bytes=Buffer.alloc(17);bytes.write('L9');bytes[2]=64|6;
  bytes.writeUInt16LE(16000,3);bytes.writeUInt32LE(samples,5);bytes.writeUInt16LE(13926,9);
  return bytes;
};

// A real all-zero P6 stream, constructed without allocating its decoded PCM.
function silentV9(samples) {
  const bytes=Buffer.alloc(17+Math.ceil(samples/320)*20+16);let bits=0;
  const put=(value,width)=>{for(let i=0;i<width;++i,++bits)bytes[17+(bits>>3)]|=((value>>i)&1)<<(bits&7);};
  for(let frame=0;frame*320<samples;++frame) {
    put(frame===0?1:0,1);
    if(!frame) {put(0,1);for(let j=0;j<10;++j){const value=j?5:3;put(0,value>>2);put(1,1);put(value&3,2);}}
    for(let half=0;half<2&&frame*320+half*160<samples;++half) {
      put(0,8);
      for(let packet=0;packet<4&&frame*320+half*160+packet*40<samples;++packet) {put(0,9);put(8,4);put(8,4);}
    }
  }
  const payload=Math.ceil(bits/8),result=bytes.subarray(0,17+payload);header(samples).copy(result);
  result.writeUInt32LE(payload,13);return result;
}

test('whole search stays at 32M while only fast accuracy streaming admits 64M',()=>{
  assert.equal(MAX_SAMPLES,32000000);assert.equal(MAX_STREAM_SAMPLES,64000000);assert.equal(MAX_DECODE_SAMPLES,64000000);
  const calls=[];const api={enc_stream_window:()=>20480,enc_stream_create:()=>1,
    enc_stream_create_accuracy:(...args)=>{calls.push(args);return 1;}};
  const settings={samples:MAX_SAMPLES+1,profile:4,sampleRate:16000,accuracy:true,calls:0};
  createStreamSession(api,settings);assert.equal(calls.length,1);
  createStreamSession(api,{...settings,samples:MAX_STREAM_SAMPLES});assert.equal(calls.length,2);
  for(const changed of [{calls:4},{accuracy:false},{samples:MAX_STREAM_SAMPLES+1}])assert.throws(()=>createStreamSession(api,{...settings,...changed}),/настройки/);
  assert.equal(calls.length,2,'rejected sessions do not reach an allocating ABI');
  assert.equal(streamingSampleLimit(true,0),MAX_STREAM_SAMPLES);
  assert.equal(streamingSampleLimit(true,4),MAX_SAMPLES);assert.equal(streamingSampleLimit(false,0),MAX_SAMPLES);
});

test('actual encoder constructors extend fast accuracy only and retain the seed allocation guard',async()=>{
  for(const name of ['encoder-adaptive.wasm','encoder-adaptive-simd.wasm']) {
    const {instance}=await WebAssembly.instantiate(binary(name)),api=instance.exports;api.__wasm_call_ctors();
    assert.equal(api.enc_stream_create_accuracy(641,4,16000,0,0,0,-18,12),1);
    const small=api.memory.buffer.byteLength;
    assert.equal(api.enc_stream_create_accuracy(MAX_STREAM_SAMPLES,4,16000,0,0,0,-18,12),1);
    assert.ok(api.memory.buffer.byteLength<=small+65536,'the total count does not allocate whole-recording PCM');
    assert.equal(api.enc_stream_create_accuracy(MAX_STREAM_SAMPLES+1,4,16000,0,0,0,-18,12),-1);
    assert.equal(api.enc_stream_create_accuracy(MAX_SAMPLES+1,4,16000,0,4,0,-18,12),-1);
    assert.equal(api.enc_stream_create(MAX_SAMPLES+1,4,16000,0,0,0,-18,12),-1,'legacy streaming limit is retained');
    assert.equal(api.enc_reserve(MAX_SAMPLES+1),0,'whole-input seed limit is retained before allocation');
    assert.equal(api.enc_stream_create_accuracy(641,4,16000,0,0,0,-18,12),1,'a rejected request does not poison reuse');
  }
});

test('64M metadata and incremental decode fit while impossible headers remain rejected',async()=>{
  for(const count of [MAX_SAMPLES+1,MAX_STREAM_SAMPLES])assert.equal(parseHeader(header(count)).samples,count);
  assert.throws(()=>parseHeader(header(MAX_STREAM_SAMPLES+1)),/64 000 000/);
  const decoderBinary=binary('decoder.wasm'),{instance}=await WebAssembly.instantiate(decoderBinary),api=instance.exports;
  api.__wasm_call_ctors?.();assert.equal(api.lpx_reserve(13,1),1);
  const base=api.lpx_input(),worst=base+Math.ceil(MAX_FILE_BYTES/8)*8+MAX_DECODE_SAMPLES*2;
  assert.ok(worst<256*1024*1024,'100MiB input plus64M PCM fits the existing256MiB WASM arena');
  const before=api.memory.buffer.byteLength;
  assert.equal(api.lpx_reserve(13,MAX_DECODE_SAMPLES+1),0);
  assert.equal(api.lpx_reserve(0xffffffff,0xffffffff),0);
  assert.equal(api.memory.buffer.byteLength,before,'invalid allocation arithmetic is rejected first');
  const open=await createIncrementalDecoder(decoderBinary),bytes=silentV9(MAX_SAMPLES+1),stream=open(bytes);
  assert.equal(stream.samples,MAX_SAMPLES+1);assert.deepEqual(stream.read(20480),new Int16Array(20480));
  const short=open(silentV9(641));assert.deepEqual(short.read(641),new Int16Array(641));
});

function virtualWav(samples,rate=16000) {
  const bytes=Buffer.alloc(44);bytes.write('RIFF');bytes.writeUInt32LE(samples*2+36,4);bytes.write('WAVEfmt ',8);
  bytes.writeUInt32LE(16,16);bytes.writeUInt16LE(1,20);bytes.writeUInt16LE(1,22);bytes.writeUInt32LE(rate,24);
  bytes.writeUInt32LE(rate*2,28);bytes.writeUInt16LE(2,32);bytes.writeUInt16LE(16,34);bytes.write('data',36);bytes.writeUInt32LE(samples*2,40);
  return{size:samples*2+44,slice(at,end){const out=new Uint8Array(end-at);if(at<44)out.set(bytes.subarray(at,Math.min(end,44)));return{async arrayBuffer(){return out.buffer;}};}};
}

test('bounded input preflight receives the per-job cap before PCM/storage allocation',async()=>{
  let modules=0,storage=0;
  const runtime={navigator:{storage:{async getDirectory(){storage++;throw Error('Storage must not be opened');}}}};
  const read=async()=>{modules++;throw Error('admitted resampler');};
  const name='pcm-00000000-0000-0000-0000-000000000000.tmp',source=virtualWav(MAX_SAMPLES+1);
  await assert.rejects(()=>prepareAudio(source,16000,name,()=>{},read,runtime),/отсчётов/);
  assert.equal(modules,0);assert.equal(storage,0);
  await assert.rejects(()=>prepareAudio(source,16000,name,()=>{},read,runtime,MAX_STREAM_SAMPLES),/admitted resampler/);
  assert.equal(modules,1);assert.equal(storage,0);
  await assert.rejects(()=>prepareAudio(source,16000,name,()=>{},read,runtime,MAX_STREAM_SAMPLES+1),/предел/);
});

test('runtime packet output also enforces its cap when metadata was insufficient',async()=>{
  let framesClosed=0,closed=false,writes=0;
  class Decoder {
    static async isConfigSupported(){return{supported:true};}state='unconfigured';decodeQueueSize=0;
    constructor(callbacks){this.callbacks=callbacks;}configure(){this.state='configured';}
    decode(){this.callbacks.output({sampleRate:8000,numberOfChannels:1,numberOfFrames:8,timestamp:0,
      copyTo(out){out.fill(0);},close(){framesClosed++;}});}
    async flush(){}close(){this.state='closed';closed=true;}
  }
  const track={config:{codec:'test'},trimStart:0,trimDuration:.001,leading:0,packetCount:1,
    reader:{async read(){return new Uint8Array([0]);}},*packets(){yield{offset:0,size:1,timestamp:0,duration:1000};}};
  const resampler={capacity:8,input:new Float32Array(8),init(){},push(n){return new Int16Array(n);}};
  await assert.rejects(()=>decodePackets(track,resampler,8000,()=>writes++,()=>{},
    {AudioDecoder:Decoder,EncodedAudioChunk:class{constructor(value){Object.assign(this,value);}}},4),/отсчётов/);
  assert.equal(writes,0);assert.equal(framesClosed,1);assert.equal(closed,true);
});

test('source worker chooses 64M only for fast accuracy Auto/stream jobs',async()=>{
  const workerSource=binary('encode-worker.js').toString().replace(/^import .*;\r?\n/gm,'').replaceAll('import.meta.url',JSON.stringify(new URL('encode-worker.js',root).href));
  for(const processingSelection of ['auto','stream','full','stream-refine'])for(const accuracy of [false,true]) {
    let limit;
    const messages=[],self={postMessage:message=>messages.push(message)};
    const context={self,MAX_SAMPLES,MAX_STREAM_SAMPLES,qualityTargetCode,validTemporaryName:()=>true,
      navigator:{locks:{async request(name,callback){return callback();}}},
      prepareAudio:async(...args)=>{limit=args[6];throw Error('limit probe');}};
    runInNewContext(workerSource,context);
    await self.onmessage({data:{source:{},temporaryName:'probe',processingSelection,accuracy}});
    assert.equal(limit,accuracy&&['auto','stream'].includes(processingSelection)?MAX_STREAM_SAMPLES:MAX_SAMPLES);
    assert.equal(messages.at(-1).error,'limit probe');
  }
});

test('full source worker rejects an oversized prepared result before allocating whole PCM',async()=>{
  const workerSource=binary('encode-worker.js').toString().replace(/^import .*;\r?\n/gm,'').replaceAll('import.meta.url',JSON.stringify(new URL('encode-worker.js',root).href));
  let allocations=0,reads=0,encodes=0,disposed=false;
  const messages=[],self={postMessage:message=>messages.push(message)};
  const context={self,MAX_SAMPLES,MAX_STREAM_SAMPLES,qualityTargetCode,validTemporaryName:()=>true,performance:{now:()=>0},
    Int16Array:function(){allocations++;throw Error('Unexpected whole PCM allocation');},
    navigator:{locks:{async request(name,callback){return callback();}}},
    createEncoderBackend:async()=>({backend:'scalar',encode(){encodes++;}}),
    prepareAudio:async()=>({samples:MAX_SAMPLES+1,read(){reads++;},async dispose(){disposed=true;}})};
  runInNewContext(workerSource,context);
  await self.onmessage({data:{source:{},temporaryName:'probe',processingSelection:'full',accuracy:true}});
  assert.match(messages.at(-1).error,/32 000 000/);
  assert.equal(allocations,0);assert.equal(reads,0);assert.equal(encodes,0);assert.equal(disposed,true);
});

test('Web UI defaults to 16 kHz and explains the upper-partial bandwidth tradeoff',()=>{
  const html=binary('index.html').toString(),select=html.match(/<select id="encode-rate">([\s\S]*?)<\/select>/)[1];
  assert.match(select,/^<option value="16000" selected>/);
  assert.match(select,/8 кГц · речь/);assert.match(select,/16 кГц · обертоны/);
  assert.match(html,/выше 4 кГц удаляются ещё до сжатия/);
});
