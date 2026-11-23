import { createEncoderBackend } from './encoder-backend.js?v=20261123-stream-v1';
import { encodeStreaming } from './streaming.js?v=20261123-stream-v1';
let nextRead=0;
const reads=new Map();
function readPcm(offset,samples) {
  const id=++nextRead;
  return new Promise((resolve,reject)=>{reads.set(id,{resolve,reject,samples});self.postMessage({read:{id,offset,samples}});});
}
self.onmessage = async ({ data }) => {
  if(data.readReply!==undefined) {
    const pending=reads.get(data.readReply);if(!pending)return;reads.delete(data.readReply);
    const pcm=data.pcm?new Int16Array(data.pcm):null;
    if(data.error||!pcm||pcm.length!==pending.samples)pending.reject(Error(data.error||'Не удалось прочитать порцию исходника.'));
    else pending.resolve(pcm);
    return;
  }
  try {
    const { encode, backend } = await createEncoderBackend(data.backend ?? 'auto');
    if(data.processing==='stream') {
      const started=performance.now();
      const result=await encodeStreaming(encode,data,readPcm,(phase,progress)=>self.postMessage({phase,progress}),async url=>{
        const response=await fetch(url);if(!response.ok)throw Error('Не удалось загрузить декодер для проверки результата.');return response.arrayBuffer();
      });
      result.backend=backend;result.elapsedMs=performance.now()-started;
      self.postMessage({result},[result.bytes.buffer]);return;
    }
    const pcm = new Int16Array(data.pcm);
    const started = performance.now();
    const bytes = encode(pcm, data.sampleRate, data.profile, progress => self.postMessage({ progress }),
      { sizeAllowancePercent: data.sizeAllowancePercent ?? 0, normalization: data.normalization ?? 'preserve',
        targetLufs: data.targetLufs ?? -18, maxGainDb: data.maxGainDb ?? 12 });
    const elapsedMs = performance.now() - started;
    self.postMessage({ result: { bytes, samples: pcm.length, long: !!(bytes[2] & 64), backend, elapsedMs, loudness: encode.loudness } }, [bytes.buffer]);
  } catch (error) {
    const message=error instanceof WebAssembly.RuntimeError
      ?'Кодировщик аварийно остановился. Для длинной записи выберите потоковую обработку; полный поиск может исчерпать память.'
      :error.message||'Ошибка кодирования LPX.';
    self.postMessage({error:message});
  }
};
