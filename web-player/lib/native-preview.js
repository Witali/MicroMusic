// Native audio and downloadable firmware have separate, explicit metadata.
function readFlashMeasurement(value,encodedBytes) {
  if(value===undefined)return undefined;
  if(!value||value.target!=='attiny88'||value.memoryProfile!=='sram512'||value.flashMeasurementKind!=='unpaced-test-image'
    ||!['programFlashBytes','encodedBytes','totalFlashBytes'].every(key=>Number.isSafeInteger(value[key])&&value[key]>0)
    ||value.encodedBytes!==encodedBytes||value.programFlashBytes+value.encodedBytes!==value.totalFlashBytes)
    throw Error('Неверное измерение Flash для LPX-примера.');
  const {programFlashBytes,totalFlashBytes,flashMeasurementKind,memoryProfile,target}=value;
  return {programFlashBytes,encodedBytes,totalFlashBytes,flashMeasurementKind,memoryProfile,target};
}
export function lpxPreviewEntries(data,baseURL) {
  if(data.schemaVersion!==1||data.previewKind!=='native-pwm8'||data.sampleRate!==8000
    ||!Number.isInteger(data.samples)||data.samples<=0||!Number.isFinite(data.durationSeconds)||data.durationSeconds<=0
    ||Math.abs(data.durationSeconds-data.samples/data.sampleRate)>1/data.sampleRate
    ||typeof data.title!=='string'||!['LPX v5','LPX'].includes(data.codec)
    ||!Array.isArray(data.variants)||![2,3].includes(data.variants.length))
    throw Error('Неверное описание LPX-примеров.');
  const base=new URL('./',baseURL);
  const asset=(path,extension)=>{
    if(typeof path!=='string')throw Error('Неверный адрес LPX-примера.');
    const url=new URL(path,base);
    if(url.origin!==base.origin||!url.pathname.startsWith(base.pathname+'audio/lpx-bread/')||!url.pathname.endsWith(extension))
      throw Error('Неверный адрес LPX-примера.');
    return url.href;
  };
  const reference=asset(data.reference?.audio,'.wav');
  const definitions={low15:{profile:15,codec:'lpx-s15',version:8},compact:{profile:4,codec:'lpx-v5',version:5},quality:{profile:6,codec:'lpx-v5',version:5}};
  const variants=new Map();
  for(const variant of data.variants){
    if(!variant||!Object.hasOwn(definitions,variant.id)||variants.has(variant.id))throw Error('Неизвестный или повторный LPX-пример.');
    variants.set(variant.id,variant);
  }
  if(!variants.has('compact')||!variants.has('quality'))throw Error('Неполный набор LPX-примеров.');
  return ['low15','compact','quality'].filter(id=>variants.has(id)).map((id,index)=>{
    const variant=variants.get(id),definition=definitions[id],experimental=id==='low15';
    const codec=variant.codec===undefined?(experimental?null:'lpx-v5'):variant.codec;
    const formatVersion=variant.formatVersion===undefined?(experimental?null:5):variant.formatVersion;
    if(variant.profile!==definition.profile||codec!==definition.codec||formatVersion!==definition.version||typeof variant.label!=='string'
      ||!Number.isInteger(variant.bytes)||variant.bytes<=0||!Number.isFinite(variant.bitrateBps)
      ||Math.abs(variant.bitrateBps-variant.bytes*8*data.sampleRate/data.samples)>1e-6)
      throw Error('Неверная стоимость LPX-потока.');
    return {id:'lpx-bread-'+id,order:String(index+1).padStart(2,'0'),title:(experimental?'LPX-S15':'LPX')+' · '+variant.label,
      description:data.title,kind:'speech',codec,formatVersion,playback:'native-pwm8',device:'attiny88',
      formatNotice:experimental?'LPX-S15 · экспериментальный формат; нужен отдельный декодер.':'',
      intendedBoard:'mh-et-live-16mhz',profile:definition.profile,sampleHz:data.sampleRate,phraseSamples:data.samples,
      playOnce:true,audioChannels:1,streamBytes:variant.bytes,bitrateBps:variant.bitrateBps,
      flashMeasurement:readFlashMeasurement(variant.flashMeasurement,variant.bytes),
      nativeAudioUrl:asset(variant.audio,'.wav'),streamUrl:asset(variant.stream,'.lpx'),originalAudioUrl:reference};
  });
}

export function lpxFirmwareEntries(data,baseURL) {
  if(data.schema!=='micromusic-lpx-avr-firmware-v1'||data.device!=='atmega328p'||data.cpuHz!==16000000||data.sampleHz!==8000
    ||!Array.isArray(data.variants)||data.variants.length!==2||new Set(data.variants.map(variant=>variant?.id)).size!==2)
    throw Error('Неверный каталог речевых прошивок Arduino Nano.');
  const base=new URL('./',baseURL);
  return lpxPreviewEntries(data.preview,baseURL).filter(entry=>entry.codec==='lpx-v5').map(entry=>{
    const variant=data.variants.find(item=>item.id===entry.id.replace('lpx-bread-',''));
    if(!variant||!['flashBytes','programFlashBytes','staticSramBytes'].every(key=>Number.isSafeInteger(variant[key])&&variant[key]>0)
      ||variant.flashBytes>30720||variant.staticSramBytes>=2048||variant.programFlashBytes+entry.streamBytes!==variant.flashBytes
      ||!/^[a-f0-9]{64}$/.test(variant.hexSha256)||variant.timing?.underruns!==0||variant.timing?.playedSamples!==entry.phraseSamples)
      throw Error('Неверные параметры прошивки Arduino Nano.');
    const source=new URL(variant.source,base);
    if(source.origin!==base.origin||!source.pathname.startsWith(base.pathname+'firmware/arduino-nano/')||!source.pathname.endsWith('.hex'))
      throw Error('Неверный адрес прошивки Arduino Nano.');
    return {...entry,id:entry.id.replace('lpx-bread-','lpx-nano-bread-'),device:'atmega328p',intendedBoard:'arduino-nano-16mhz',
      flashMeasurement:undefined,firmware:{...variant,source:source.href}};
  });
}

// Read the actual mono PCM16 WAV for display; audio playback uses the same URL.
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
    ||!payload||payload.bytes!==phraseSamples*2)throw Error('WAV не соответствует LPX-примеру.');
  return Float32Array.from({length:phraseSamples},(_,index)=>view.getInt16(payload.start+index*2,true)/32768);
}
