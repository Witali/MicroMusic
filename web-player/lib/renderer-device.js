import {Renderer as AudioRenderer,validateRendererInput} from './renderer-js.js?v=20261026-persistent-cache';
import {ATtiny13A,getRuntimeBytes} from './attiny13a.js?v=20261026-persistent-cache';
import {parseHex} from './hex.js';
import {createCachedDeviceCore} from './avr-persistent-cache.js';
export async function createDeviceRenderer(entry,sampleRate,controls,options){
  const profile=validateRendererInput(entry,sampleRate,controls);
  const flash=parseHex(entry.flashHex,profile.flashBytes),eeprom=entry.eepromHex?parseHex(entry.eepromHex,profile.eepromBytes):null;
  const core=await createCachedDeviceCore({Core:ATtiny13A,flash,eeprom,
    options:{target:'attiny13a',cpuHz:entry.cpuHz,...options},runtimeBytes:getRuntimeBytes()});
  const renderer=new Renderer(entry,sampleRate,controls,core);
  renderer.translationCache=core.persistentTranslationCache;return renderer;
}
export class Renderer extends AudioRenderer {
  constructor(entry,sampleRate,controls={},core=ATtiny13A,coreOptions={}){super(entry,sampleRate,controls,core,coreOptions);}
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw Error('Invalid audio block size');
    return this.processRaw(this.core.capturePhysical(count,this.sampleRate,this.channels),count);
  }
}
