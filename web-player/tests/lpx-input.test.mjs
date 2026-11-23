import test from'node:test';
import assert from'node:assert/strict';
import{readFileSync}from'node:fs';
import{spawnSync}from'node:child_process';
import{createHash}from'node:crypto';
import{createInputResampler,decodePackets,validTemporaryName,prepareAudio,recoverTemporaryInputs}from'../lpx/audio-source.js';
import{encodeWav}from'../lpx/codec.js';
import{openAudio}from'../lpx/audio-demux.js';
const wasm=readFileSync(new URL('../lpx/input-resampler.wasm',import.meta.url));
test('input WASM has complete current source/build provenance and no imports',()=>{
 const manifest=JSON.parse(readFileSync(new URL('../lpx/input-resampler-build.json',import.meta.url))),hash=b=>createHash('sha256').update(b).digest('hex');
 assert.equal(hash(wasm),manifest.sha256);for(const key of['source','builder'])assert.equal(hash(readFileSync(new URL('../../'+manifest[key],import.meta.url),'utf8').replaceAll('\r\n','\n')),manifest[key+'Sha256']);
 assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(wasm)),[]);
});
async function resample(rate,target,n,block,frequency=1000){
  const r=await createInputResampler(wasm);r.init(rate,target,2);const output=[];
  for(let at=0;at<n;at+=block){const count=Math.min(block,n-at);for(let i=0;i<count;i++){const x=.2*Math.sin((at+i)*2*Math.PI*frequency/rate);r.input[i]=x;r.input[r.capacity+i]=x;}output.push(r.push(count).slice());}
  output.push(r.push(0,true).slice());return Int16Array.from(output.flatMap(x=>Array.from(x)));
}
test('C++ input FIR retains exact phase/history across arbitrary packet sizes and rates',async()=>{
  for(const rate of[8000,11025,22050,44100,48000,96000])for(const target of[8000,12000,16000]){
    const n=8197,a=await resample(rate,target,n,4096),b=await resample(rate,target,n,37);
    assert.equal(a.length,Math.round(n*target/rate));assert.deepEqual(a,b,`${rate}/${target}`);
  }
});
test('native and WASM input preparation agree on the same PCM frames',{skip:!process.env.LPX_INPUT_NATIVE},async()=>{
  for(const rate of[7500,44100,48000])for(const target of[8000,12000,16000]){
    const count=8197,raw=new Float32Array(count*2);for(let i=0;i<count;i++)raw[i*2]=raw[i*2+1]=.2*Math.sin(i*2*Math.PI*1000/rate);
    const done=spawnSync('wsl',['-d','Ubuntu','--',process.env.LPX_INPUT_NATIVE,String(rate),String(target),'2','37'],{input:Buffer.from(raw.buffer),maxBuffer:1024*1024});
    assert.equal(done.status,0,done.stderr?.toString());const expected=await resample(rate,target,count,37);assert.deepEqual(done.stdout,Buffer.from(expected.buffer));
  }
});

function localStorageMock(failWrite=false){
  const files=new Map();let closes=0,removals=0;
  const folder={async getFileHandle(name){if(!files.has(name))files.set(name,new Uint8Array());return{async createSyncAccessHandle(){return{
    truncate(n){files.set(name,new Uint8Array(n));},getSize(){return files.get(name).length;},flush(){},close(){closes++;},
    write(bytes,{at}){if(failWrite)throw new DOMException('quota','QuotaExceededError');const old=files.get(name),next=new Uint8Array(Math.max(old.length,at+bytes.length));next.set(old);next.set(bytes,at);files.set(name,next);return bytes.length;},
    read(out,{at}){const bytes=new Uint8Array(out.buffer,out.byteOffset,out.byteLength),part=files.get(name).subarray(at,at+bytes.length);bytes.set(part);return part.length;}
  };}};},async removeEntry(name){files.delete(name);removals++;},async*entries(){for(const name of files.keys())yield[name,{}];}};
  return{files,folder,get closes(){return closes;},get removals(){return removals;},storage:{async getDirectory(){return{async getDirectoryHandle(){return folder;}};}}};
}
test('temporary source and verification PCM stay separate and are removed on success/error',async()=>{
  const name='pcm-00000000-0000-0000-0000-000000000000.tmp',blob=new Blob([encodeWav(new Int16Array(641).fill(1000),8000)]);
  for(const fail of[false,true]){
    const disk=localStorageMock(fail),runtime={navigator:{storage:disk.storage}};
    if(fail){await assert.rejects(()=>prepareAudio(blob,8000,name,()=>{},async()=>wasm,runtime),/Недостаточно места/);}
    else{const source=await prepareAudio(blob,8000,name,()=>{},async()=>wasm,runtime),before=await source.read(0,641);
      source.verification.append(0,new Int16Array(641).fill(42));assert.deepEqual(await source.verification.read(0,0,641),new Int16Array(641).fill(42));assert.deepEqual(await source.read(0,641),before);
      source.verification.reset();assert.equal(source.verification.size(0),0);await source.dispose();await assert.rejects(()=>source.read(0,1));
    }
    assert.equal(disk.files.size,0);assert.equal(disk.closes,1);assert.equal(disk.removals,1);
  }
});
test('crash recovery removes only unlocked application-owned temporary files',async()=>{
  const disk=localStorageMock(),a='pcm-00000000-0000-0000-0000-000000000000.tmp',b='pcm-11111111-1111-1111-1111-111111111111.tmp';
  disk.files.set(a,new Uint8Array());disk.files.set(b,new Uint8Array());disk.files.set('unrelated',new Uint8Array());
  await recoverTemporaryInputs(disk.storage,{async request(name,options,callback){return callback(name.endsWith(b)?null:{});}});
  assert.equal(disk.files.has(a),false);assert.equal(disk.files.has(b),true);assert.equal(disk.files.has('unrelated'),true);
});
test('C++ input FIR rejects out-of-band aliases without attenuating ordinary speech bands',async()=>{
  const level=x=>Math.sqrt(x.subarray(100,x.length-100).reduce((s,v)=>s+v*v,0)/(x.length-200));
  const pass=await resample(48000,8000,48000,1024,1000),stop=await resample(48000,8000,48000,1024,7000);
  assert.ok(Math.abs(level(pass)-.2*32768/Math.sqrt(2))<10);assert.ok(level(stop)<level(pass)*.001);
  const upper=await resample(48000,8000,48000,1024,2900);assert.ok(Math.abs(level(upper)-.2*32768/Math.sqrt(2))<10);
});
test('input FIR validates configuration, finite samples, EOF and bounded fixed memory',async()=>{
  const r=await createInputResampler(wasm);assert.equal(r.memoryBytes,1048576);assert.throws(()=>r.init(12345,8000,2));r.init(44100,8000,1);r.input[0]=NaN;assert.throws(()=>r.push(1));r.init(44100,8000,1);assert.equal(r.push(0,true).length,0);assert.throws(()=>r.push(1));
  assert.equal(validTemporaryName('pcm-00000000-0000-0000-0000-000000000000.tmp'),true);assert.equal(validTemporaryName('../input.pcm'),false);
});
test('retained public M4A is range-read with edit trimming and bounded reads',async()=>{
  const path=new URL('../../Codecs/LPX/05_BENCHMARKS/OPUS_AAC_LPX_RUSSIAN_AND_MUSIC/synthetic_music_codecs/synthetic_polyphony_24s_aac_32.m4a',import.meta.url);
  const b=new Blob([readFileSync(path)]);b.arrayBuffer=()=>{throw Error('Whole input read forbidden');};
  const t=await openAudio(b);assert.equal(t.kind,'m4a');assert.equal(t.duration,24);assert.equal(t.trimStart,.128);assert.ok(t.reader.maxRead<=65536);
  const packets=[];for await(const p of t.packets())packets.push(p);assert.equal(packets.length,t.packetCount);assert.ok(packets.every(p=>p.size>0));
  await assert.rejects(()=>openAudio(new Blob([readFileSync(path).subarray(0,40)])),/M4A/);
});
test('actual bounded AudioDecoder protocol trims once, closes every frame and drains before reuse',async()=>{
  const r=await createInputResampler(wasm);let closed=0,decoderClosed=false,peak=0,flushes=0;const output=[];
  class Chunk{constructor(data){Object.assign(this,data);}}
  class Decoder extends EventTarget{static async isConfigSupported(){return{supported:true};}state='unconfigured';queue=[];get decodeQueueSize(){return this.queue.length;}
    constructor(callbacks){super();this.callbacks=callbacks;}configure(){this.state='configured';}
    decode(c){this.queue.push(c);peak=Math.max(peak,this.queue.length);queueMicrotask(()=>{const data=new Float32Array(1024).fill(.1);this.callbacks.output({sampleRate:8000,numberOfChannels:1,numberOfFrames:1024,timestamp:c.timestamp,close(){closed++;},copyTo(out,{frameCount}){out.set(data.subarray(0,frameCount));}});this.queue.shift();this.dispatchEvent(new Event('dequeue'));});}
    async flush(){flushes++;await new Promise(resolve=>queueMicrotask(resolve));}
    close(){this.state='closed';decoderClosed=true;}
  }
  const count=19,track={config:{codec:'mp4a.40.2'},packetCount:count,trimStart:.128,trimDuration:2,leading:0,reader:{async read(){return new Uint8Array([0]);}},*packets(){for(let i=0;i<count;i++)yield{offset:i,size:1,timestamp:i*128000,duration:128000};}};
  const stats=await decodePackets(track,r,8000,pcm=>output.push(pcm.slice()),()=>{},{AudioDecoder:Decoder,EncodedAudioChunk:Chunk});
  assert.equal(stats.samples,16000);assert.equal(closed,count);assert.equal(decoderClosed,true);assert.equal(flushes,1);assert.ok(peak<=8);assert.equal(output.reduce((n,p)=>n+p.length,0),16000);
});
