import {lpxPreviewEntries} from './native-preview.js?v=20261102-nano';

const phrases=['chego','otvechaesh','vinni','bread'];
const positive=value=>Number.isSafeInteger(value)&&value>0;
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);

// Admit complete, interrupt-verified images independently of the USB loader's
// smaller application area. Images above that area remain downloadable for ISP.
export function lpxTiny88FirmwareEntries(data,baseURL){
  if(data.schema!=='micromusic-lpx-attiny88-firmware-v1'||data.device!=='attiny88'
    ||data.cpuHz!==16000000||data.sampleHz!==8000||data.pwmHz!==62500||data.pwmOutput!=='D9 / PB1 / OC1A'
    ||data.flashLimitBytes!==8192||data.bootloaderLimitBytes!==6012||data.physicalBoardMeasured!==false
    ||!Array.isArray(data.clips)||data.clips.length!==4
    ||new Set(data.clips.map(clip=>clip?.clipId??'bread')).size!==4
    ||data.clips.some(clip=>!phrases.includes(clip?.clipId??'bread'))
    ||!Array.isArray(data.variants)||data.variants.length!==9
    ||new Set(data.variants.map(variant=>variant?.clipId+'/'+variant?.id)).size!==9)
    throw Error('Неверный каталог речевых прошивок ATtiny88.');
  const base=new URL('./',baseURL);
  const entries=data.clips.flatMap(clip=>lpxPreviewEntries(clip,baseURL));
  if(entries.length!==9||entries.some(entry=>entry.profile===15&&entry.audioReferenceId!=='bread'))
    throw Error('Неполный набор прошивок ATtiny88.');
  return entries.map(entry=>{
    const profile=entry.id.replace('lpx-'+entry.audioReferenceId+'-','');
    const variant=data.variants.find(item=>item.clipId===entry.audioReferenceId&&item.id===profile);
    if(!variant||!['flashBytes','programFlashBytes','staticSramBytes','peakStackBytes','stackMarginBytes'].every(key=>positive(variant[key]))
      ||variant.flashBytes>data.flashLimitBytes||variant.programFlashBytes+entry.streamBytes!==variant.flashBytes
      ||variant.staticSramBytes+variant.peakStackBytes+variant.stackMarginBytes!==511
      ||!digest(variant.hexSha256)||!digest(variant.streamSha256)
      ||variant.fitsStandardBootloader!==(variant.flashBytes<=data.bootloaderLimitBytes)
      ||variant.requiresIsp!==(variant.flashBytes>data.bootloaderLimitBytes)
      ||variant.timing?.playedSamples!==entry.phraseSamples||variant.timing?.underruns!==0
      ||variant.timing?.irqEntryCycles!==4||variant.timing?.irqRetiComplete!==true
      ||!positive(variant.timing?.minQueuedSamplesBeforeOutput)
      ||!positive(variant.timing?.minTickCycles)||!positive(variant.timing?.maxTickCycles)
      ||variant.timing.minTickCycles>variant.timing.maxTickCycles
      ||variant.timing.minTickCycles<1980||variant.timing.maxTickCycles>2020)
      throw Error('Неверные параметры прошивки ATtiny88.');
    if(typeof variant.source!=='string')throw Error('Неверный адрес прошивки ATtiny88.');
    const source=new URL(variant.source,base);
    if(source.origin!==base.origin||source.pathname!==base.pathname+`firmware/attiny88/lpx-tiny88-${entry.audioReferenceId}-${profile}.hex`
      ||source.search||source.hash)throw Error('Неверный адрес прошивки ATtiny88.');
    return {...entry,cpuHz:data.cpuHz,pwmHz:data.pwmHz,flashMeasurement:undefined,
      firmware:{...variant,source:source.href,pwmPin:9,pwmOutput:data.pwmOutput,
        flashLimitBytes:data.flashLimitBytes,bootloaderLimitBytes:data.bootloaderLimitBytes}};
  });
}
