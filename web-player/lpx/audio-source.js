import{openAudio}from'./audio-demux.js?v=20261124-stream-quality';
import{MAX_SAMPLES,MAX_STREAM_SAMPLES}from'./codec.js?v=20261124-stream-quality';
const folderName='micromusic-lpx-input-v1';
const validSampleLimit=limit=>Number.isInteger(limit)&&limit>0&&limit<=MAX_STREAM_SAMPLES;
const sampleLimitError=limit=>Error(`Запись превышает ${limit.toLocaleString('ru-RU')} отсчётов в выбранной частоте.`);
export const validTemporaryName=name=>/^pcm-[a-f0-9-]{36}\.tmp$/.test(name);
export async function removeTemporaryInput(name,storage=navigator.storage){
  if(!validTemporaryName(name)||!storage?.getDirectory)return;
  try{const root=await storage.getDirectory(),folder=await root.getDirectoryHandle(folderName);await folder.removeEntry(name);}
  catch(error){if(error.name!=='NotFoundError')throw error;}
}
export async function recoverTemporaryInputs(storage=navigator.storage,locks=navigator.locks){
  if(!storage?.getDirectory||!locks?.request)return;
  let folder;try{folder=await(await storage.getDirectory()).getDirectoryHandle(folderName);}catch(error){if(error.name==='NotFoundError')return;throw error;}
  for await(const[name]of folder.entries())if(validTemporaryName(name))
    await locks.request('lpx-input-'+name,{ifAvailable:true},async lock=>{if(lock)await folder.removeEntry(name).catch(e=>{if(e.name!=='NotFoundError')throw e;});});
}
export async function createInputResampler(binary){
  const{instance}=await WebAssembly.instantiate(binary),api=instance.exports,capacity=api.source_capacity();
  return{
    init(rate,target,channels){if(api.source_init(rate,target,channels)!==1)throw Error('Не поддерживается частота декодированного AAC.');},
    input:new Float32Array(api.memory.buffer,api.source_input(),capacity*2),capacity,
    pcm16(bytes,frames){new Uint8Array(api.memory.buffer,api.source_raw_input(),bytes.length).set(bytes);if(api.source_copy_s16(frames)<0)throw Error('Неверная порция PCM16.');return this.push(frames);},
    push(frames,final=false){const n=api.source_push(frames,final?1:0);if(n<0)throw Error('Ошибка потокового пересчёта частоты.');return new Int16Array(api.memory.buffer,api.source_output(),n);},
    memoryBytes:api.memory.buffer.byteLength
  };
}
// Runtime injection makes the actual queue/lifetime/storage protocol testable
// without a JavaScript implementation of AAC or the C++ FIR.
export async function decodePackets(track,resampler,target,sink,onProgress=()=>{},runtime=globalThis,maxSamples=MAX_SAMPLES){
  if(!validSampleLimit(maxSamples))throw Error('Некорректный предел подготовленного PCM.');
  const Decoder=runtime.AudioDecoder,Chunk=runtime.EncodedAudioChunk;
  if(!Decoder||!Chunk||(await Decoder.isConfigSupported(track.config)).supported!==true)
    throw Error('Браузер не поддерживает потоковое декодирование этого формата. Используйте актуальный браузер с AudioDecoder и поддержкой MP3/AAC.');
  let decoder,error,wake,sourceRate=0,channels=0,expected=0,end=0,written=0,outputs=0,peakQueue=0;
  const save=pcm=>{if(!pcm.length)return;if(written+pcm.length>maxSamples)throw sampleLimitError(maxSamples);sink(pcm,written);written+=pcm.length;};
  const silence=frames=>{while(frames>0){const count=Math.min(frames,resampler.capacity);resampler.input.fill(0);save(resampler.push(count));frames-=count;}};
  decoder=new Decoder({error:e=>{error=e;wake?.();},output:frame=>{
    try{
      if(error)return;
      if(!sourceRate){sourceRate=frame.sampleRate;channels=frame.numberOfChannels;resampler.init(sourceRate,target,channels);
        expected=Math.round(track.trimStart*sourceRate);end=Math.round((track.trimStart+track.trimDuration)*sourceRate);silence(Math.round(track.leading*sourceRate));}
      if(frame.sampleRate!==sourceRate||frame.numberOfChannels!==channels)throw Error('Звук меняет частоту или число каналов посреди файла.');
      const at=Math.round(frame.timestamp*sourceRate/1e6),first=Math.max(0,expected-at),stop=Math.min(frame.numberOfFrames,end-at);
      if(first<stop){if(at+first!==expected)throw Error('Разрыв временной шкалы звука.');
        for(let p=first;p<stop;p+=resampler.capacity){const count=Math.min(stop-p,resampler.capacity);
          for(let c=0;c<channels;c++)frame.copyTo(resampler.input.subarray(c*resampler.capacity,c*resampler.capacity+count),{planeIndex:c,frameOffset:p,frameCount:count,format:'f32-planar'});
          save(resampler.push(count));expected+=count;
        }
      }
      outputs++;
    }catch(e){error=e;wake?.();}finally{frame.close();}
  }});
  try{
    decoder.configure(track.config);let packets=0;
    // Backpressure, not intermediate flushes: AAC overlap and MP3 reservoir/
    // synthesis history must survive the entire track. Flush only at true EOF.
    for await(const packet of track.packets()){
      if(error)throw error;
      if(decoder.decodeQueueSize>=8)await new Promise(resolve=>{
        const ready=()=>{if(error||decoder.decodeQueueSize<8){decoder.removeEventListener('dequeue',ready);wake=null;resolve();}};
        wake=ready;decoder.addEventListener('dequeue',ready);ready();
      });
      if(error)throw error;
      const data=await track.reader.read(packet.offset,packet.size);
      decoder.decode(new Chunk({type:'key',timestamp:packet.timestamp,duration:packet.duration,data}));
      peakQueue=Math.max(peakQueue,decoder.decodeQueueSize);
      if(++packets%8===0){onProgress(packets/track.packetCount);await new Promise(resolve=>setTimeout(resolve,0));if(error)throw error;}
    }
    await decoder.flush();if(error)throw error;
    if(!sourceRate||expected!==end)throw Error('Звуковой поток закончился раньше заявленной длительности.');
    save(resampler.push(0,true));
    const exact=Math.round((Math.round(track.leading*sourceRate)+end-Math.round(track.trimStart*sourceRate))*target/sourceRate);
    if(!written||written!==exact)throw Error('Длина подготовленного PCM не совпала с временной шкалой.');
    onProgress(1);return {samples:written,sampleRate:target,sourceRate,channels,outputs,peakDecodeQueue:peakQueue,modelMemoryBytes:resampler.memoryBytes};
  }finally{if(decoder.state!=='closed')decoder.close();}
}
async function decodeWav(track,resampler,target,sink,onProgress,runtime,maxSamples){
  resampler.init(track.rate,target,track.channels);let written=0;
  const save=pcm=>{if(written+pcm.length>maxSamples)throw sampleLimitError(maxSamples);sink(pcm,written);written+=pcm.length;};
  for(let at=0;at<track.frames;at+=resampler.capacity){const frames=Math.min(resampler.capacity,track.frames-at);const bytes=await track.reader.read(track.at+at*track.align,frames*track.align);save(resampler.pcm16(bytes,frames));onProgress((at+frames)/track.frames);}
  save(resampler.push(0,true));if(written!==Math.round(track.frames*target/track.rate))throw Error('Неверная длина подготовленного WAV.');
  return{samples:written,sampleRate:target,sourceRate:track.rate,channels:track.channels,modelMemoryBytes:resampler.memoryBytes};
}
export async function prepareAudio(file,rate,name,onProgress,readBinary,runtime=globalThis,maxSamples=MAX_SAMPLES){
  if(!validSampleLimit(maxSamples))throw Error('Некорректный предел подготовленного PCM.');
  if(!validTemporaryName(name)||!runtime.navigator?.storage?.getDirectory)throw Error('Для потоковой обработки требуется локальное хранилище OPFS (HTTPS и современный браузер).');
  const track=await openAudio(file);
  if(![8000,12000,16000].includes(rate)||Math.ceil(track.duration*rate)>maxSamples)throw sampleLimitError(maxSamples);
  const resampler=await createInputResampler(await readBinary(new URL('./input-resampler.wasm?v=20261124-stream-quality',import.meta.url)));
  let handle,folder,disposed=false;
  const dispose=async()=>{if(disposed)return;disposed=true;try{handle?.close();}finally{if(folder)await folder.removeEntry(name).catch(e=>{if(e.name!=='NotFoundError')throw e;});}};
  try{
    const root=await runtime.navigator.storage.getDirectory();folder=await root.getDirectoryHandle(folderName,{create:true});
    handle=await(await folder.getFileHandle(name,{create:true})).createSyncAccessHandle();handle.truncate(0);
    const decode=track.kind==='wav'?decodeWav:decodePackets;
    const stats=await decode(track,resampler,rate,(pcm,offset)=>{const bytes=new Uint8Array(pcm.buffer,pcm.byteOffset,pcm.byteLength);if(handle.write(bytes,{at:offset*2})!==bytes.length)throw Error('Не удалось записать временный PCM.');},onProgress,runtime,maxSamples);
    handle.flush();if(handle.getSize()!==stats.samples*2)throw Error('Неверная длина временного PCM.');
    const expectedPosition=[0,0];
    return{...stats,kind:track.kind,duration:stats.samples/rate,metadataBytes:track.metadataBytes,maxCompressedRead:track.reader.maxRead,dispose,
      verification:{
        reset(){expectedPosition[0]=expectedPosition[1]=0;},
        append(kind,pcm){const bytes=new Uint8Array(pcm.buffer,pcm.byteOffset,pcm.byteLength),at=(stats.samples*(kind+1)+expectedPosition[kind])*2;if(handle.write(bytes,{at})!==bytes.length)throw Error('Не удалось сохранить проверочный PCM.');expectedPosition[kind]+=pcm.length;},
        async read(kind,offset,count){const pcm=new Int16Array(count);if(offset+count>expectedPosition[kind]||handle.read(pcm,{at:(stats.samples*(kind+1)+offset)*2})!==pcm.byteLength)throw Error('Не удалось прочитать проверочный PCM.');return pcm;},
        size(kind){return expectedPosition[kind];}
      },
      async read(offset,count){if(disposed||!Number.isInteger(offset)||!Number.isInteger(count)||offset<0||count<1||count>20528||offset+count>stats.samples)throw Error('Неверный диапазон временного PCM.');const pcm=new Int16Array(count);if(handle.read(pcm,{at:offset*2})!==pcm.byteLength)throw Error('Временный PCM прочитан не полностью.');return pcm;}}
  }catch(error){await dispose();if(error.name==='QuotaExceededError')throw Error('Недостаточно места в локальном хранилище браузера для временного PCM.');throw error;}
}
