// Native previews are catalog audio entries, never AVR firmware images.
export function lpxPreviewEntries(data,baseURL) {
  if(data.schemaVersion!==1||data.previewKind!=='native-pwm8'||data.sampleRate!==8000
    ||!Number.isInteger(data.samples)||data.samples<=0||!Number.isFinite(data.durationSeconds)||data.durationSeconds<=0
    ||Math.abs(data.durationSeconds-data.samples/data.sampleRate)>1/data.sampleRate
    ||typeof data.title!=='string'||!Array.isArray(data.variants)||data.variants.length!==2)
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
  return [['compact',4],['quality',6]].map(([id,profile],index)=>{
    const variant=data.variants.find(item=>item.id===id);
    if(!variant||variant.profile!==profile||typeof variant.label!=='string'
      ||!Number.isInteger(variant.bytes)||variant.bytes<=0||!Number.isFinite(variant.bitrateBps)
      ||Math.abs(variant.bitrateBps-variant.bytes*8*data.sampleRate/data.samples)>1e-6)
      throw Error('Неверная стоимость LPX-потока.');
    return {id:'lpx-bread-'+id,order:String(index+1).padStart(2,'0'),title:'LPX · '+variant.label,
      description:data.title,kind:'speech',codec:'lpx-v5',playback:'native-pwm8',device:'attiny88',
      intendedBoard:'mh-et-live-16mhz',profile,sampleHz:data.sampleRate,phraseSamples:data.samples,
      playOnce:true,audioChannels:1,streamBytes:variant.bytes,bitrateBps:variant.bitrateBps,
      nativeAudioUrl:asset(variant.audio,'.wav'),streamUrl:asset(variant.stream,'.lpx'),originalAudioUrl:reference};
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
