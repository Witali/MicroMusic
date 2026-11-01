// Native previews are catalog audio entries, never AVR firmware images.
import {validateNativeAudio,nativeAudioMetadata,previewAsset} from './native-audio.js';
export {previewWaveform} from './native-audio.js';
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
  validateNativeAudio(data);
  if(!['LPX v5','LPX'].includes(data.codec)
    ||!Array.isArray(data.variants)||![2,3].includes(data.variants.length))
    throw Error('Неверное описание LPX-примеров.');
  const asset=(path,extension)=>previewAsset(path,extension,baseURL,'audio/lpx-bread/');
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
    return {...nativeAudioMetadata(data),id:'lpx-bread-'+id,order:String(index+1).padStart(2,'0'),title:(experimental?'LPX-S15':'LPX')+' · '+variant.label,
      codec,formatVersion,device:'attiny88',codecLabel:experimental?'LPX-S15':'LPX',dataLabel:'LPX',streamExtension:'.lpx',
      nativeNotice:'ПРЕВЬЮ · Точные PWM8-отсчёты нативного декодера LPX. Целевая плата — MH-ET LIVE Tiny88, 16 МГц. Работа LPX-прошивки на этой плате ещё не подтверждена.',
      targetNotice:'Целевой профиль: MH-ET LIVE Tiny88 · 16 МГц.',
      formatNotice:experimental?'LPX-S15 · экспериментальный формат; нужен отдельный декодер.':'',
      intendedBoard:'mh-et-live-16mhz',profile:definition.profile,streamBytes:variant.bytes,bitrateBps:variant.bitrateBps,
      flashMeasurement:readFlashMeasurement(variant.flashMeasurement,variant.bytes),
      nativeAudioUrl:asset(variant.audio,'.wav'),streamUrl:asset(variant.stream,'.lpx'),originalAudioUrl:reference};
  });
}
