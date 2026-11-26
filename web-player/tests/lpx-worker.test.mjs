import test from 'node:test';
import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';
import { readFileSync } from 'node:fs';
import { createEncoder } from '../lpx/encoder.js';
import { createDecoder } from '../lpx/codec.js';

// Run the shipped worker and its default backend loader. Only the browser's
// transport primitives are adapted; no encoder or backend logic is mocked.
const workerSource = `
  const { parentPort, workerData } = require('node:worker_threads');
  const { readFile } = require('node:fs/promises');
  globalThis.self = { postMessage: (message, transfer) => parentPort.postMessage(message, transfer) };
  globalThis.fetch = async url => {
    const target = new URL(url); target.search = '';
    if (!/(?:encoder-adaptive(?:-simd)?|decoder)\\.wasm$/.test(target.pathname)) throw Error('Unexpected asset');
    return new Response(await readFile(target));
  };
  import(workerData).then(() => parentPort.on('message', data => self.onmessage({ data })));
`;
const decode = await createDecoder(readFileSync(new URL('../lpx/decoder.wasm', import.meta.url)));
const reference = await createEncoder(readFileSync(new URL('../lpx/encoder-adaptive.wasm', import.meta.url)));

test('shipped streaming worker pulls bounded portions, reports progress and permits cancellation', async () => {
  const pcm=Int16Array.from({length:40961},(_,i)=>Math.round((i<20000?500:2500)*Math.sin(i*.14)));
  const worker=new Worker(workerSource,{eval:true,workerData:new URL('../lpx/encode-worker.js',import.meta.url).href});
  const reads=[],phases=[];
  try {
    const result=await new Promise((resolve,reject)=>{
      worker.on('error',reject);worker.on('message',data=>{
        if(data.error)return reject(Error(data.error));
        if(data.read){
          const {id,offset,samples}=data.read;assert.ok(samples<=20528);reads.push([offset,samples]);
          const part=pcm.slice(offset,offset+samples);worker.postMessage({readReply:id,pcm:part.buffer},[part.buffer]);
        }
        if(data.phase)phases.push(data.phase);
        if(data.result)resolve(data.result);
      });
      worker.postMessage({processing:'stream',samples:pcm.length,profile:6,sampleRate:8000,backend:'auto',normalization:'loudness',targetLufs:-24,maxGainDb:9});
    });
    assert.equal(result.processing,'stream');assert.equal(result.windows,3);assert.equal(result.memoryFallback,false);
    assert.equal(decode(result.bytes).samples,pcm.length);assert.equal(result.loudness.status,1);
    for(const phase of ['measure','encode','verify','done'])assert.ok(phases.includes(phase));
    assert.ok(reads.length>=6);
  } finally {await worker.terminate();}
  const cancelled=new Worker(workerSource,{eval:true,workerData:new URL('../lpx/encode-worker.js',import.meta.url).href});
  let resultAfterCancel=false;
  await new Promise((resolve,reject)=>{
    cancelled.on('error',reject);cancelled.on('message',async data=>{
      if(data.result)resultAfterCancel=true;
      if(data.read){await cancelled.terminate();resolve();}
    });
    cancelled.postMessage({processing:'stream',samples:1048577,profile:6,sampleRate:8000,backend:'scalar',normalization:'loudness'});
  });
  assert.equal(resultAfterCancel,false);
});

test('shipped worker loads adaptive assets, forwards allowances and returns one validated file', async () => {
  for (const backend of ['scalar', 'simd', 'auto']) for (const normalization of ['preserve', 'loudness']) {
    const worker = new Worker(workerSource, { eval: true, workerData: new URL('../lpx/encode-worker.js', import.meta.url).href });
    const pcm = Int16Array.from({ length: 6001 }, (_, i) => Math.round(6000 * Math.sin(i * .14)));
    const settings = { targetLufs: -24, maxGainDb: 9 };
    const expected = reference(pcm, 12000, 6, () => {}, { sizeAllowancePercent: 25, normalization, ...settings });
    const expectedLoudness = reference.loudness;
    const progress = [];
    try {
      const result = await new Promise((resolve, reject) => {
        worker.on('error', reject);
        worker.on('message', data => {
          if (data.error) reject(Error(data.error));
          if (data.progress !== undefined) progress.push(data.progress);
          if (data.result) resolve(data.result);
        });
        worker.postMessage({ pcm: pcm.buffer, sampleRate: 12000, profile: 6, backend, sizeAllowancePercent: 25, normalization, ...settings }, [pcm.buffer]);
      });
      assert.deepEqual(result.bytes, expected);
      assert.deepEqual(progress, [0, 1]);
      assert.equal(result.backend, backend === 'scalar' ? 'scalar' : 'simd');
      assert.equal(result.samples, 6001);
      assert.equal(decode(result.bytes).pcm.length, 6001);
      assert.deepEqual(result.loudness, expectedLoudness);
      if (normalization === 'loudness') assert.equal(result.loudness.status, 1);
      assert.ok(result.elapsedMs >= 0);
    } finally { await worker.terminate(); }
  }
});


test('worker forwards PCM quality selection and reports invalid targets', async () => {
  const worker=new Worker(workerSource,{eval:true,workerData:new URL('../lpx/encode-worker.js',import.meta.url).href});
  try {
    const pcm=Int16Array.from({length:641},(_,i)=>Math.round(2500*Math.sin(i*.143)));
    const settings={accuracy:true,calls:0,qualityTarget:'pcm',normalization:'loudness',targetLufs:-24,maxGainDb:9};
    const expected=reference(pcm,16000,6,()=>{},settings);
    const result=await new Promise((resolve,reject)=>{
      worker.once('error',reject);
      const receive=data=>{if(data.error){worker.off('message',receive);reject(Error(data.error));}if(data.result){worker.off('message',receive);resolve(data.result);}};
      worker.on('message',receive);
      worker.postMessage({pcm:pcm.buffer,sampleRate:16000,profile:6,backend:'scalar',...settings});
    });
    assert.deepEqual(result.bytes,expected);
    const error=await new Promise(resolve=>{worker.once('message',resolve);worker.postMessage({qualityTarget:'wrong'});});
    assert.match(error.error,/PCM/);
  } finally {await worker.terminate();}
});
