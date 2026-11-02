// Only retained, IRQ-verified ATmega328P images enter the public speech catalog.
const profiles={nb215:{sampleHz:8000,packetBytes:6,nominal:2150,band:'NB'},
  wb395:{sampleHz:16000,packetBytes:10,nominal:3950,band:'WB'},wb98:{sampleHz:16000,packetBytes:25,nominal:9800,band:'WB'}};
const phrases=['chego','otvechaesh','vinni','bread'];
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const positive=value=>Number.isSafeInteger(value)&&value>0;
const outputs={3:'D3 / PD3 / OC2B',9:'D9 / PB1 / OC1A'};
function readVariant(v,clip,data,base){
  const asset=(path,expected)=>{
    if(typeof path!=='string')throw Error('Неверный адрес Speex-примера.');
    const url=new URL(path,base);
    if(url.origin!==base.origin||url.pathname!==base.pathname+expected||url.search||url.hash)throw Error('Неверный адрес Speex-примера.');
    return url.href;
  };
    const p=profiles[v.profile],id=`speex-nano-${clip?.id}-${v.profile}`;
    if(!p||!clip||v.id!==id||typeof v.label!=='string'||v.band!==p.band||v.sampleHz!==p.sampleHz||v.packetBytes!==p.packetBytes
      ||v.nominalBitrateBps!==p.nominal||!positive(v.frames)||!positive(v.samples)||!positive(v.streamBytes)||v.samples!==v.frames*p.sampleHz/50||v.streamBytes!==v.frames*p.packetBytes
      ||!['streamSha256','audioSha256','pwmSha256','hexSha256'].every(k=>digest(v[k]))
      ||!['flashBytes','programFlashBytes','staticSramBytes','peakStackBytes','freeSramAtPeak'].every(k=>positive(v[k]))
      ||v.flashBytes>30720||v.programFlashBytes+v.streamBytes!==v.flashBytes
      ||v.staticSramBytes+v.peakStackBytes+v.freeSramAtPeak!==2048
      ||v.timing?.samples!==v.samples||v.timing?.underruns!==0||v.timing?.includesInterrupts!==true
      ||!positive(v.timing?.minQueuedSamplesBeforeOutput)
      ||!positive(v.timing?.timerIntervalMinCycles)||!positive(v.timing?.timerIntervalMaxCycles)||v.timing.timerIntervalMinCycles>v.timing.timerIntervalMaxCycles
      ||v.timing.timerIntervalMinCycles<(p.sampleHz===8000?1992:990)||v.timing.timerIntervalMaxCycles>(p.sampleHz===8000?2008:1010))
      throw Error('Неверные параметры Speex-прошивки.');
    const source=asset(v.source,`firmware/arduino-nano/${id}.hex`);
    return {id,audioReferenceId:clip.id,profile:v.profile,profileLabel:v.label,title:clip.id==='dialogue'?clip.title:v.label,description:clip.title,
      order:clip.id==='dialogue'?'05':undefined,profileMenuOrder:Object.keys(profiles).indexOf(v.profile)+1,
      kind:'speech',codec:'speex',band:p.band,playback:'native-pwm8',device:'atmega328p',intendedBoard:'arduino-nano-16mhz',
      sampleHz:p.sampleHz,phraseSamples:v.samples,audioChannels:1,playOnce:true,streamBytes:v.streamBytes,
      bitrateBps:v.streamBytes*8*p.sampleHz/v.samples,nominalBitrateBps:p.nominal,streamExtension:'.spxraw',
      nativeAudioUrl:asset(v.audio,`audio/speex-speech/${clip.id}/${v.profile}.wav`),
      streamUrl:asset(v.stream,`audio/speex-speech/${clip.id}/${v.profile}.spxraw`),
      originalAudioUrl:clip.id==='dialogue'?undefined:asset(clip.originalAudioUrl,clip.id==='bread'?'audio/lpx-bread/original.wav':`audio/originals/${clip.id}.wav`),
      originalPlaybackUrl:clip.id==='dialogue'?undefined:asset(clip.originalPlaybackUrl,clip.id==='bread'?'audio/lpx-bread/original.wav':`audio/originals/playback/${clip.id}.wav`),
      research:clip.id==='dialogue'?'../ATmega328/Sound/lpx-dialogue/README.md':'../Codecs/Speex/AVR/README.md',
      firmware:{...v,source,pwmPin:data.pwmPin,pwmOutput:data.pwmOutput}};
}

function validTarget(data){
  return data.device==='atmega328p'&&data.cpuHz===16000000&&data.pwmHz===62500
    &&outputs[data.pwmPin]&&data.pwmOutput===outputs[data.pwmPin]&&data.assemblyEnabled===true
    &&data.physicalBoardMeasured===false&&digest(data.decoderAdmissionSha256);
}

export function speexFirmwareEntries(data,baseURL){
  if(data.schema!=='micromusic-speex-avr-firmware-v1'||!validTarget(data)
    ||!Array.isArray(data.clips)||![3,4].includes(data.clips.length)
    ||new Set(data.clips.map(c=>c?.id)).size!==data.clips.length||data.clips.some(c=>!phrases.includes(c.id)||typeof c.title!=='string'||!digest(c.originalSha256))
    ||phrases.slice(0,3).some(id=>!data.clips.some(clip=>clip.id===id))
    ||!Array.isArray(data.variants)||data.variants.length!==data.clips.length*3||new Set(data.variants.map(v=>v?.clipId+'/'+v?.profile)).size!==data.variants.length)
    throw Error('Неверный каталог Speex для ATmega328P.');
  const base=new URL('./',baseURL);
  return data.variants.map(v=>readVariant(v,data.clips.find(c=>c.id===v.clipId),data,base));
}

export function speexDialogueProfiles(data,baseURL){
  if(data.schema!=='micromusic-speex-dialogue-v1'||!validTarget(data)||data.flashLimitBytes!==30720||typeof data.title!=='string'
    ||!Array.isArray(data.variants)||data.variants.length!==3||new Set(data.variants.map(v=>v?.profile)).size!==3)
    throw Error('Неверный каталог Speex-диалога.');
  const entries=[],unavailableProfiles=[],base=new URL('./',baseURL);
  for(const v of data.variants){
    if(!Object.hasOwn(profiles,v.profile)||typeof v.available!=='boolean')throw Error('Неверный профиль Speex-диалога.');
    if(v.available){entries.push(readVariant(v,{id:'dialogue',title:data.title},data,base));continue;}
    if(v.id!=='speex-nano-dialogue-'+v.profile||typeof v.label!=='string'||!positive(v.flashBytes)||v.flashBytes<=30720
      ||!positive(v.programFlashBytes)||!positive(v.streamBytes)||v.programFlashBytes+v.streamBytes!==v.flashBytes
      ||v.source!==undefined||v.audio!==undefined||v.stream!==undefined)
      throw Error('Неверная причина недоступности Speex-диалога.');
    unavailableProfiles.push({id:v.id,codec:'speex',profile:v.profile,profileLabel:v.label,available:false,
      profileMenuOrder:Object.keys(profiles).indexOf(v.profile)+1,unavailableReason:'Не помещается во Flash Arduino Nano'});
  }
  return {entries,unavailableProfiles};
}
