import {validateNativeAudio,nativeAudioMetadata,previewAsset} from './native-audio.js';

// Speex framing/alignment is separate from LPX's version/profile contract.
export function speexPreviewEntries(data,baseURL) {
  validateNativeAudio(data);
  if(data.codec!=='Speex NB'||data.decoderTarget!=='atmega328p'||data.flashMeasurement!==undefined
    ||!Array.isArray(data.variants)||data.variants.length!==2)throw Error('Неверное описание Speex-примеров.');
  const reference=previewAsset(data.reference?.audio,'.wav',baseURL,'audio/lpx-bread/');
  if(reference!==new URL('audio/lpx-bread/original.wav',new URL('./',baseURL)).href)
    throw Error('Неверная исходная запись Speex-примеров.');
  const variants=new Map();
  for(const variant of data.variants){
    if(!variant||!['compact','quality'].includes(variant.id)||variants.has(variant.id))throw Error('Неизвестный или повторный Speex-пример.');
    variants.set(variant.id,variant);
  }
  return [['compact',1,2150,6],['quality',3,8000,20]].map(([id,mode,nominalBitrateBps,packetBytes],index)=>{
    const variant=variants.get(id);
    if(!variant||variant.mode!==mode||variant.nominalBitrateBps!==nominalBitrateBps||variant.packetBytes!==packetBytes
      ||(variant.codec!==undefined&&variant.codec!=='speex-nb')||variant.flashMeasurement!==undefined
      ||typeof variant.label!=='string'||!Number.isSafeInteger(variant.packets)||variant.packets<=0
      ||!Number.isSafeInteger(variant.decodedSamples)||variant.decodedSamples!==variant.packets*160
      ||!['trimStartSamples','trimEndSamples'].every(key=>Number.isSafeInteger(variant[key])&&variant[key]>=0)
      ||variant.decodedSamples-variant.trimStartSamples-variant.trimEndSamples!==data.samples
      ||!Number.isSafeInteger(variant.bytes)||variant.bytes!==packetBytes*variant.packets
      ||!Number.isFinite(variant.bitrateBps)||Math.abs(variant.bitrateBps-variant.bytes*8*data.sampleRate/data.samples)>1e-6)
      throw Error('Неверные пакеты, выравнивание или стоимость Speex-потока.');
    return {...nativeAudioMetadata(data),id:'speex-bread-'+id,order:String(index+1).padStart(2,'0'),
      title:'Speex NB · '+variant.label,codec:'speex-nb',codecLabel:'Speex NB',dataLabel:'Speex',streamExtension:'.spxraw',
      device:'attiny88',decoderTarget:'atmega328p',mode,nominalBitrateBps,
      packetBytes,packets:variant.packets,decodedSamples:variant.decodedSamples,
      trimStartSamples:variant.trimStartSamples,trimEndSamples:variant.trimEndSamples,
      streamBytes:variant.bytes,bitrateBps:variant.bitrateBps,formatNotice:'',
      nativeNotice:'Сравнение звука: нативные PWM8-отсчёты. Наш декодер Speex для ATmega328P; прошивки для ATtiny88 нет.',
      targetNotice:'Декодер: ATmega328P · Speex NB.',
      boardNotice:'Сравнение Speex NB · декодер ATmega328P.',
      firmwareNotice:'Flash HEX недоступен: прошивки Speex для ATtiny88 нет.',
      research:'../Codecs/Speex/AVR/README.md',researchLabel:'Исследование Speex ↗',
      nativeAudioUrl:previewAsset(variant.audio,'.wav',baseURL,'audio/speex-bread/'),
      streamUrl:previewAsset(variant.stream,'.spxraw',baseURL,'audio/speex-bread/'),originalAudioUrl:reference};
  });
}
