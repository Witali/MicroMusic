import { qualityTargetCode } from './quality-target.js?v=20261126-quality-target';
import { createEncoderBackend } from './encoder-backend.js?v=20261126-quality-target';
import { encodeStreaming } from './streaming.js?v=20261126-quality-target';
import { prepareAudio, validTemporaryName } from './audio-source.js?v=20261126-quality-target';
import { MAX_SAMPLES, MAX_STREAM_SAMPLES } from './codec.js?v=20261126-quality-target';
const readBinary=async url=>{const response=await fetch(url);if(!response.ok)throw Error('Не удалось загрузить модуль обработки звука.');return response.arrayBuffer();};
async function encodeSource(data){
  if(!validTemporaryName(data.temporaryName)||!navigator.locks?.request)throw Error('Браузер не поддерживает безопасную временную обработку аудио.');
  return navigator.locks.request('lpx-input-'+data.temporaryName,async()=>{
    let source;
    try{
      self.postMessage({phase:'source',progress:0});
      const extendedFast=data.accuracy===true&&['auto','stream'].includes(data.processingSelection);
      const inputLimit=extendedFast?MAX_STREAM_SAMPLES:MAX_SAMPLES;
      source=await prepareAudio(data.source,data.sampleRate,data.temporaryName,p=>self.postMessage({phase:'source',progress:p*.2}),readBinary,globalThis,inputLimit);
      self.postMessage({sourceInfo:{samples:source.samples,channels:source.channels,duration:source.duration,sourceRate:source.sourceRate,kind:source.kind}});
      const{encode,backend}=await createEncoderBackend(data.backend??'auto'),started=performance.now();
      const stream=['stream','stream-refine'].includes(data.processingSelection)||data.processingSelection==='auto'&&source.samples>128000;
      let result;
      if(stream)result=await encodeStreaming(encode,{...data,samples:source.samples,calls:data.processingSelection==='stream-refine'?4:0},
        (offset,count)=>source.read(offset,count),(phase,p)=>self.postMessage({phase,progress:.2+.8*p}),readBinary,source.verification);
      else{
        if(source.samples>MAX_SAMPLES)throw Error('Полный поиск поддерживает до 32 000 000 отсчётов. Выберите быструю потоковую обработку.');
        const pcm=new Int16Array(source.samples);
        for(let at=0;at<pcm.length;at+=20480)pcm.set(await source.read(at,Math.min(20480,pcm.length-at)),at);
        const bytes=encode(pcm,data.sampleRate,data.profile,p=>self.postMessage({progress:p}),data);
        result={bytes,samples:source.samples,long:!!(bytes[2]&64),loudness:encode.loudness};
      }
      result.backend=backend;result.elapsedMs=performance.now()-started;result.sourceStreaming=true;
      result.inputMemoryBytes=source.modelMemoryBytes;result.inputMaxRead=source.maxCompressedRead;
      return result;
    }finally{await source?.dispose();}
  });
}
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
    qualityTargetCode(data.qualityTarget);
    if(data.source){const result=await encodeSource(data);self.postMessage({result},[result.bytes.buffer]);return;}
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
        qualityTarget:data.qualityTarget,calls:data.calls??4,targetLufs: data.targetLufs ?? -18, maxGainDb: data.maxGainDb ?? 12,accuracy:data.accuracy===true });
    const elapsedMs = performance.now() - started;
    self.postMessage({ result: { bytes, samples: pcm.length, long: !!(bytes[2] & 64), backend, elapsedMs, loudness: encode.loudness } }, [bytes.buffer]);
  } catch (error) {
    const message=error instanceof WebAssembly.RuntimeError
      ?'Кодировщик аварийно остановился. Для длинной записи выберите потоковую обработку; полный поиск может исчерпать память.'
      :error.message||'Ошибка кодирования LPX.';
    self.postMessage({error:message});
  }
};
