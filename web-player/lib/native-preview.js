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
  const clipId=data.clipId??'bread';
  if(!['bread','chego','otvechaesh','vinni'].includes(clipId))throw Error('Неизвестная речевая фраза LPX.');
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
    const folder=clipId==='bread'?'audio/lpx-bread/':`audio/lpx-speech/${clipId}/`;
    const original=extension==='.wav'&&[base.pathname+`audio/originals/${clipId}.wav`,base.pathname+`audio/originals/playback/${clipId}.wav`].includes(url.pathname);
    if(url.origin!==base.origin||(!url.pathname.startsWith(base.pathname+folder)&&!original)||!url.pathname.endsWith(extension))
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
    return {id:'lpx-'+clipId+'-'+id,audioReferenceId:clipId,profileLabel:variant.label,order:String(index+1).padStart(2,'0'),title:(experimental?'LPX-S15':'LPX')+' · '+variant.label,
      description:data.title,kind:'speech',codec,formatVersion,playback:'native-pwm8',device:'attiny88',
      formatNotice:experimental?'LPX-S15 · экспериментальный формат; нужен отдельный декодер.':'',
      intendedBoard:'mh-et-live-16mhz',profile:definition.profile,sampleHz:data.sampleRate,phraseSamples:data.samples,
      playOnce:true,audioChannels:1,streamBytes:variant.bytes,bitrateBps:variant.bitrateBps,
      flashMeasurement:readFlashMeasurement(variant.flashMeasurement,variant.bytes),outputLevel:variant.outputLevel,
      nativeAudioUrl:asset(variant.audio,'.wav'),streamUrl:asset(variant.stream,'.lpx'),originalAudioUrl:reference,
      originalPlaybackUrl:data.reference.playback?asset(data.reference.playback,'.wav'):undefined};
  });
}

export function lpxFirmwareEntries(data,baseURL) {
  const previews=data.clips??[data.preview];
  if(!['micromusic-lpx-avr-firmware-v1','micromusic-lpx-avr-firmware-v2'].includes(data.schema)||data.device!=='atmega328p'||data.cpuHz!==16000000||data.sampleHz!==8000
    ||!Array.isArray(data.variants)||!Array.isArray(previews)||!previews.length||data.variants.length!==previews.length*2
    ||new Set(data.variants.map(variant=>(variant?.clipId??'bread')+'/'+variant?.id)).size!==data.variants.length)
    throw Error('Неверный каталог речевых прошивок Arduino Nano.');
  const base=new URL('./',baseURL);
  return previews.flatMap(preview=>lpxPreviewEntries(preview,baseURL)).filter(entry=>entry.codec==='lpx-v5').map(entry=>{
    const variant=data.variants.find(item=>(item.clipId??'bread')===entry.audioReferenceId&&item.id===entry.id.replace('lpx-'+entry.audioReferenceId+'-',''));
    if(!variant||!['flashBytes','programFlashBytes','staticSramBytes'].every(key=>Number.isSafeInteger(variant[key])&&variant[key]>0)
      ||variant.flashBytes>30720||variant.staticSramBytes>=2048||variant.programFlashBytes+entry.streamBytes!==variant.flashBytes
      ||!/^[a-f0-9]{64}$/.test(variant.hexSha256)||variant.timing?.underruns!==0||variant.timing?.playedSamples!==entry.phraseSamples)
      throw Error('Неверные параметры прошивки Arduino Nano.');
    const source=new URL(variant.source,base);
    if(source.origin!==base.origin||!source.pathname.startsWith(base.pathname+'firmware/arduino-nano/')||!source.pathname.endsWith('.hex'))
      throw Error('Неверный адрес прошивки Arduino Nano.');
    return {...entry,id:entry.id.replace('lpx-','lpx-nano-'),device:'atmega328p',intendedBoard:'arduino-nano-16mhz',
      flashMeasurement:undefined,firmware:{...variant,source:source.href}};
  });
}

// A reset chain has one verified HEX/WAV, but no single compressed LPX file.
export function lpxDialogueEntry(data,baseURL) {
  const positive=value=>Number.isSafeInteger(value)&&value>0;
  const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
  const timing=data.timing;
  if(data.schema!=='micromusic-nano-dialogue-v1'||data.device!=='atmega328p'||data.cpuHz!==16000000
    ||data.sampleHz!==8000||data.pwmOutput!=='D3 / PD3 / OC2B'||data.playback!=='once-after-reset'
    ||typeof data.title!=='string'||!positive(data.samples)||!Number.isFinite(data.durationSeconds)
    ||Math.abs(data.durationSeconds-data.samples/8000)>1/8000
    ||!['flashBytes','programFlashBytes','streamBytes','staticSramBytes'].every(key=>positive(data[key]))
    ||data.flashBytes>30720||data.staticSramBytes>=2048||data.programFlashBytes+data.streamBytes!==data.flashBytes
    ||!digest(data.hexSha256)||!digest(data.wavSha256)
    ||timing?.played!==data.samples||timing.timer_ticks!==data.samples||timing.timer_events!==data.samples
    ||timing.underruns!==0||timing.queued_at_stop!==0||timing.irq_entry_cycles!==4||timing.irq_reti_complete!==true
    ||!positive(timing.stack_margin_all_bytes)||!positive(timing.irq_cycles_max)
    ||!positive(timing.tick_interval_min_cycles)||!positive(timing.tick_interval_max_cycles)
    ||timing.tick_interval_min_cycles>timing.tick_interval_max_cycles
    ||timing.tick_interval_min_cycles<1992||timing.tick_interval_max_cycles>2008)
    throw Error('Неверные параметры LPX-диалога Arduino Nano.');
  const base=new URL('./',baseURL);
  const asset=(path,expected)=>{
    if(typeof path!=='string')throw Error('Неверный адрес LPX-диалога.');
    const url=new URL(path,base);
    if(url.origin!==base.origin||url.pathname!==base.pathname+expected||url.search||url.hash)
      throw Error('Неверный адрес LPX-диалога.');
    return url.href;
  };
  const source=asset(data.firmware,'firmware/arduino-nano/lpx-nano-dialogue-quality.hex');
  return {id:'lpx-nano-dialogue-quality',audioReferenceId:'dialogue',order:'05',title:data.title,
    description:'Четыре реплики · громкость выровнена · паузы 0,5 / 1,5 / 0,5 с',
    profile:6,profileLabel:'Повышенное качество',kind:'speech',codec:'lpx-v5',formatVersion:5,
    playback:'native-pwm8',device:'atmega328p',intendedBoard:'arduino-nano-16mhz',
    sampleHz:8000,phraseSamples:data.samples,audioChannels:1,playOnce:true,streamBytes:data.streamBytes,
    bitrateBps:data.streamBytes*8*8000/data.samples,outputLevel:data.outputLevel,
    nativeAudioUrl:asset(data.audio,'audio/lpx-dialogue/dialogue.wav'),
    research:'../ATmega328/Sound/lpx-dialogue/README.md',
    firmware:{source,flashBytes:data.flashBytes,programFlashBytes:data.programFlashBytes,
      staticSramBytes:data.staticSramBytes,hexSha256:data.hexSha256,pwmPin:3,pwmOutput:data.pwmOutput}};
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
    ||!payload||payload.bytes!==phraseSamples*2)throw Error('WAV не соответствует звуковому примеру.');
  return Float32Array.from({length:phraseSamples},(_,index)=>view.getInt16(payload.start+index*2,true)/32768);
}
