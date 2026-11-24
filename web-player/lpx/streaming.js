import { createIncrementalDecoder, MAX_SAMPLES } from './codec.js?v=20261123-precision-input-v2';
import { encodingPolicy, bitrateBudget } from './encoding-policy.js?v=20261124-unification';

export function createStreamSession(api, settings) {
  const {samples,profile,sampleRate,sizeAllowancePercent=0,normalization='preserve',targetLufs=-18,maxGainDb=12,calls=4}=settings;
  if(!api.enc_stream_create)throw Error('Обновите страницу: потоковое кодирование недоступно.');
  if(!Number.isInteger(samples)||samples<1||samples>MAX_SAMPLES||![3,4,6,8].includes(profile)||![8000,12000,16000].includes(sampleRate)
    ||!Number.isInteger(sizeAllowancePercent)||sizeAllowancePercent<0||sizeAllowancePercent>100
    ||!['preserve','loudness'].includes(normalization)||!Number.isInteger(targetLufs)||targetLufs<-30||targetLufs>-9
    ||!Number.isInteger(maxGainDb)||maxGainDb<0||maxGainDb>24||!Number.isInteger(calls)||calls<0||calls>4)
    throw Error('Некорректные настройки потокового кодирования.');
  const policy=encodingPolicy(profile,!!settings.accuracy);
  if(settings.accuracy&&sizeAllowancePercent!==0)throw Error('Уровни точности не используют допуск размера.');
  if(policy.targetBitrate&&(sampleRate!==8000||sizeAllowancePercent!==0))throw Error('Профили 3/8 используют 8 кГц без допуска размера.');
  const checked=(value,stage)=>{if(value<0)throw Error(`Потоковый энкодер: ${stage} (${value}).`);return value;};
  const create=settings.accuracy?api.enc_stream_create_accuracy:api.enc_stream_create;
  if(!create)throw Error('Обновите страницу: выбранный энкодер недоступен.');
  checked(create(samples,profile,sampleRate,sizeAllowancePercent,calls,normalization==='loudness'?1:0,targetLufs,maxGainDb),'подготовка');
  const window=api.enc_stream_window();
  const put=pcm=>{
    if(!(pcm instanceof Int16Array)||!pcm.length||pcm.length>window+48)throw Error('Некорректная порция PCM.');
    new Int16Array(api.memory.buffer,api.enc_stream_input(),pcm.length).set(pcm);
  };
  const take=()=>[0,1].map(kind=>{
    const size=api.enc_stream_size(kind),count=api.enc_stream_pcm_size(kind);
    return {bytes:new Uint8Array(api.memory.buffer,api.enc_stream_bytes(kind),size).slice(),
      pcm:new Int16Array(api.memory.buffer,api.enc_stream_pcm(kind),count).slice()};
  });
  return {
    window, measure(pcm){put(pcm);return checked(api.enc_stream_measure(pcm.length),'измерение громкости');},
    plan(){return checked(api.enc_stream_plan(targetLufs,maxGainDb),'план нормализации');},
    process(pcm,count){put(pcm);checked(api.enc_stream_process(count,pcm.length-count),'обработка порции');return take();},
    finish(){checked(api.enc_stream_finish(),'окончание потока');return take();},
    header(kind){const size=api.enc_stream_header_size(kind);return new Uint8Array(api.memory.buffer,api.enc_stream_header(kind),size).slice();},
    get hasCandidate(){return !!api.enc_stream_candidate();},
    verify(kind,offset,pcm){put(pcm);return checked(api.enc_stream_verify_put(kind,offset,pcm.length),'проверка отсчётов');},
    admit(){return checked(api.enc_stream_admit(),'проверка качества');},
    get allocationFailed(){return !!api.enc_allocation_failed?.();},
    get memoryBytes(){return api.memory.buffer.byteLength;},
    get loudness(){return normalization==='preserve'?null:{status:api.enc_stream_loudness(0),limited:!!api.enc_stream_loudness(1),
      gainLimited:!!api.enc_stream_loudness(2),input:api.enc_stream_loudness(3),prepared:api.enc_stream_loudness(4),decoded:api.enc_stream_loudness(5),gainDb:api.enc_stream_loudness(6)};}
  };
}

const yieldTurn=()=>new Promise(resolve=>setTimeout(resolve,0));
// JS transports PCM/bytes and compares independently decoded output; all gain,
// analysis, synthesis, search, packing and quality decisions stay in shared C++.
export async function encodeStreaming(encode,settings,readPcm,progress=()=>{},readBinary,verification) {
  const session=encode.createStream(settings),n=settings.samples,window=session.window;
  const parts=[[],[]],expected=[[],[]];let windows=0,peakWorking=session.memoryBytes;
  const append=rows=>rows.forEach((row,kind)=>{if(row.bytes.length)parts[kind].push(row.bytes);if(row.pcm.length){if(verification)verification.append(kind,row.pcm);else expected[kind].push(row.pcm);}});
  if(settings.normalization==='loudness') {
    for(let offset=0;offset<n;offset+=window) {
      const count=Math.min(window,n-offset);session.measure(await readPcm(offset,count));progress('measure',(offset+count)/n*.1);await yieldTurn();
    }
    session.plan();
  }
  const start=settings.normalization==='loudness'?.1:0;
  for(let offset=0;offset<n;offset+=window) {
    const count=Math.min(window,n-offset),ahead=Math.min(48,n-offset-count);
    append(session.process(await readPcm(offset,count+ahead),count));++windows;
    peakWorking=Math.max(peakWorking,session.memoryBytes);progress('encode',start+(offset+count)/n*(.8-start));await yieldTurn();
    if(!session.hasCandidate){parts[1]=[];expected[1]=[];}
  }
  append(session.finish());
  const candidate=session.hasCandidate;
  const decoder=await createIncrementalDecoder(await readBinary(new URL('./decoder.wasm?v=20261123-precision-input-v2',import.meta.url)));
  const output=[];let memoryFallback=false;
  for(const kind of candidate?[0,1]:[0]) {
    if(kind && memoryFallback)break;
    const header=session.header(kind),blob=new Blob([header,...parts[kind]]),pcmBlob=verification?null:new Blob(expected[kind]);
    parts[kind]=[];expected[kind]=[];
    const bytes=new Uint8Array(await blob.arrayBuffer()),decoded=decoder(bytes);
    if(decoded.samples!==n||(verification?verification.size(kind)!==n:pcmBlob.size!==n*2))throw Error('Проверка непрерывного потока: неверная длина.');
    const policy=encodingPolicy(settings.profile,!!settings.accuracy);
    if(policy.targetBitrate&&bytes.length>bitrateBudget(n,policy,settings.sampleRate))throw Error('Превышен предел размера полного LPX.');
    for(let offset=0;offset<n;offset+=window) {
      const count=Math.min(window,n-offset),actual=decoded.read(count);
      const wanted=verification?await verification.read(kind,offset,count):new Int16Array(await pcmBlob.slice(offset*2,(offset+count)*2).arrayBuffer());
      for(let i=0;i<count;++i)if(actual[i]!==wanted[i])throw Error('Проверка непрерывного потока: звук не совпал с ожидаемым.');
      if(!memoryFallback)try{session.verify(kind+1,offset,actual);}catch(error){if(!session.allocationFailed)throw error;memoryFallback=true;}
      progress('verify',.8+kind*.07+(offset+count)/n*.07);await yieldTurn();
    }
    output[kind]=bytes;
  }
  let choice=0;
  if(candidate&&!memoryFallback) {
    for(let offset=0;offset<n;offset+=window) {
      const count=Math.min(window,n-offset);
      try{session.verify(0,offset,await readPcm(offset,count));}catch(error){if(!session.allocationFailed)throw error;memoryFallback=true;break;}
      progress('quality',.94+(offset+count)/n*.03);await yieldTurn();
    }
    if(!memoryFallback)try{progress('quality',.97);await yieldTurn();choice=session.admit();}catch(error){if(!session.allocationFailed)throw error;memoryFallback=true;}
  } else if(!memoryFallback)choice=session.admit();
  if(memoryFallback)choice=0; // The original, completely verified control remains admissible.
  progress('done',1);
  return {bytes:output[choice],samples:n,long:n>64000,processing:'stream',refinementRequested:settings.calls!==0,windows,workingMemoryBytes:peakWorking,
    accuracyLevel:settings.accuracy?settings.profile:undefined,usedControl:choice===0,memoryFallback,loudness:session.loudness};
}
