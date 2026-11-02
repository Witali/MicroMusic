// Only retained, IRQ-verified ATmega328P images enter the public speech catalog.
const profiles={nb215:{sampleHz:8000,packetBytes:6,nominal:2150,band:'NB'},
  wb395:{sampleHz:16000,packetBytes:10,nominal:3950,band:'WB'},wb98:{sampleHz:16000,packetBytes:25,nominal:9800,band:'WB'}};
const phrases=['chego','otvechaesh','vinni'];
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const positive=value=>Number.isSafeInteger(value)&&value>0;
const outputs={3:'D3 / PD3 / OC2B',9:'D9 / PB1 / OC1A'};
export function speexFirmwareEntries(data,baseURL){
  if(data.schema!=='micromusic-speex-avr-firmware-v1'||data.device!=='atmega328p'||data.cpuHz!==16000000
    ||data.pwmHz!==62500||!outputs[data.pwmPin]||data.pwmOutput!==outputs[data.pwmPin]||data.assemblyEnabled!==true||data.physicalBoardMeasured!==false
    ||!digest(data.decoderAdmissionSha256)||!Array.isArray(data.clips)||data.clips.length!==3
    ||new Set(data.clips.map(c=>c?.id)).size!==3||data.clips.some(c=>!phrases.includes(c.id)||typeof c.title!=='string'||!digest(c.originalSha256))
    ||!Array.isArray(data.variants)||data.variants.length!==9||new Set(data.variants.map(v=>v?.clipId+'/'+v?.profile)).size!==9)
    throw Error('Неверный каталог Speex для ATmega328P.');
  const base=new URL('./',baseURL);
  const asset=(path,expected)=>{
    if(typeof path!=='string')throw Error('Неверный адрес Speex-примера.');
    const url=new URL(path,base);
    if(url.origin!==base.origin||url.pathname!==base.pathname+expected||url.search||url.hash)throw Error('Неверный адрес Speex-примера.');
    return url.href;
  };
  return data.variants.map(v=>{
    const p=profiles[v.profile],clip=data.clips.find(c=>c.id===v.clipId),id=`speex-nano-${v.clipId}-${v.profile}`;
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
    return {id,audioReferenceId:clip.id,profile:v.profile,profileLabel:v.label,title:v.label,description:clip.title,
      kind:'speech',codec:'speex',band:p.band,playback:'native-pwm8',device:'atmega328p',intendedBoard:'arduino-nano-16mhz',
      sampleHz:p.sampleHz,phraseSamples:v.samples,audioChannels:1,playOnce:true,streamBytes:v.streamBytes,
      bitrateBps:v.streamBytes*8*p.sampleHz/v.samples,nominalBitrateBps:p.nominal,streamExtension:'.spxraw',
      nativeAudioUrl:asset(v.audio,`audio/speex-speech/${clip.id}/${v.profile}.wav`),
      streamUrl:asset(v.stream,`audio/speex-speech/${clip.id}/${v.profile}.spxraw`),
      originalAudioUrl:asset(clip.originalAudioUrl,`audio/originals/${clip.id}.wav`),
      originalPlaybackUrl:asset(clip.originalPlaybackUrl,`audio/originals/playback/${clip.id}.wav`),
      research:'../Codecs/Speex/AVR/README.md',firmware:{...v,source,pwmPin:data.pwmPin,pwmOutput:data.pwmOutput}};
  });
}
