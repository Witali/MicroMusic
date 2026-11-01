// Identical playback/asset contracts shared by the explicit codec adapters.
export function validateNativeAudio(data) {
  if(data?.schemaVersion!==1||data.previewKind!=='native-pwm8'||data.sampleRate!==8000
    ||!Number.isInteger(data.samples)||data.samples<=0||!Number.isFinite(data.durationSeconds)||data.durationSeconds<=0
    ||Math.abs(data.durationSeconds-data.samples/data.sampleRate)>1/data.sampleRate||typeof data.title!=='string')
    throw Error('Неверное описание звуковых примеров.');
}
export function nativeAudioMetadata(data) {
  return {description:data.title,kind:'speech',playback:'native-pwm8',sampleHz:data.sampleRate,
    phraseSamples:data.samples,playOnce:true,audioChannels:1};
}
export function previewAsset(path,extension,baseURL,directory) {
  if(typeof path!=='string')throw Error('Неверный адрес звукового примера.');
  const base=new URL('./',baseURL),url=new URL(path,base);
  if(url.origin!==base.origin||!url.pathname.startsWith(base.pathname+directory)||!url.pathname.endsWith(extension))
    throw Error('Неверный адрес звукового примера.');
  return url.href;
}

// Read the actual mono PCM16 WAV for display; playback uses the same URL.
export function previewWaveform(buffer,{sampleHz,phraseSamples}) {
  const view=new DataView(buffer),tag=offset=>String.fromCharCode(...new Uint8Array(buffer,offset,4));
  if(view.byteLength<12||tag(0)!=='RIFF'||tag(8)!=='WAVE'||view.getUint32(4,true)+8!==view.byteLength)
    throw Error('Неверный WAV-пример.');
  let format,payload;
  for(let offset=12;offset+8<=view.byteLength;){
    const name=tag(offset),bytes=view.getUint32(offset+4,true),start=offset+8;
    if(start+bytes>view.byteLength)throw Error('Неполный WAV-пример.');
    if(name==='fmt '){
      if(bytes<16)throw Error('Неверный формат WAV.');
      format={encoding:view.getUint16(start,true),channels:view.getUint16(start+2,true),
        rate:view.getUint32(start+4,true),align:view.getUint16(start+12,true),bits:view.getUint16(start+14,true)};
    }
    if(name==='data')payload={start,bytes};
    offset=start+bytes+(bytes&1);
  }
  if(!format||format.encoding!==1||format.channels!==1||format.rate!==sampleHz||format.bits!==16||format.align!==2
    ||!payload||payload.bytes!==phraseSamples*2)throw Error('WAV не соответствует звуковому примеру.');
  return Float32Array.from({length:phraseSamples},(_,index)=>view.getInt16(payload.start+index*2,true)/32768);
}
