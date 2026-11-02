import {parseHex} from './hex.js';
import {ATMEGA328P_PROFILE as profile,ARDUINO_BOARD} from './atmega328p-profile.js';

// Catalog data describes linked, timer-driven images. Native WAV entries never
// pass this boundary and cannot acquire a Flash download or an MCU claim.
export function arduinoSpeechEntries(data,baseURL) {
  if(data?.schemaVersion!==1||!Array.isArray(data.entries)||!data.entries.length)
    throw Error('Неверный каталог речевых прошивок Arduino.');
  const base=new URL('./',baseURL),ids=new Set();
  const asset=(path,extension)=>{
    if(typeof path!=='string')throw Error('Нет адреса файла Arduino.');
    const url=new URL(path,base);
    if(url.origin!==base.origin||!url.pathname.startsWith(base.pathname)||!url.pathname.endsWith(extension))
      throw Error('Неверный адрес файла Arduino.');
    return url.href;
  };
  const entries=data.entries.map(entry=>{
    if(!entry||typeof entry.id!=='string'||!entry.id||ids.has(entry.id)
      ||typeof entry.title!=='string'||typeof entry.description!=='string'
      ||entry.device!==profile.id||entry.board!==ARDUINO_BOARD
      ||entry.executionEngine!=='avr8js'||entry.supportedEngines?.length!==1||entry.supportedEngines[0]!=='avr8js'
      ||entry.kind!=='speech'||entry.cpuHz!==profile.cpuHz||entry.sampleHz!==8000||entry.pwmHz!==62500
      ||entry.audioChannels!==1||entry.playOnce!==true||entry.playback==='native-pwm8'
      ||!Number.isSafeInteger(entry.phraseSamples)||entry.phraseSamples<1
      ||!Number.isSafeInteger(entry.playbackCycles)||entry.playbackCycles<entry.phraseSamples*entry.cpuHz/entry.sampleHz
      ||!['programFlashBytes','encodedBytes','flashBytes'].every(key=>Number.isSafeInteger(entry[key])&&entry[key]>0)
      ||entry.programFlashBytes+entry.encodedBytes!==entry.flashBytes||entry.flashBytes>profile.flashBytes
      ||entry.eepromBytes!==0||entry.eepromHex
      ||!Number.isFinite(entry.bitrateBps)||Math.abs(entry.bitrateBps-entry.encodedBytes*8*entry.sampleHz/entry.phraseSamples)>1e-6
      ||!/^\w[\w-]*$/.test(entry.id)||!/^[a-f0-9]{64}$/i.test(entry.flashSha256)
      ||!((entry.pwmOutput==='OC2B'&&entry.outputPin==='D3')||(entry.pwmOutput==='OC1A'&&entry.outputPin==='D9')))
      throw Error('Неверная конфигурация речевой прошивки Arduino.');
    if(parseHex(entry.flashHex,profile.flashBytes).length!==entry.flashBytes)
      throw Error('Размер HEX не соответствует прошивке Arduino.');
    ids.add(entry.id);
    return {...entry,source:asset(entry.source,'.hex'),originalAudioUrl:asset(entry.originalAudioUrl,'.wav')};
  });
  if(!ids.has(data.defaultId))throw Error('Нет основной прошивки Arduino.');
  return {...data,entries};
}
