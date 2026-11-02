import {Renderer as AudioRenderer} from './renderer-js.js';
import {ATmega328P,resolveATmega328PProfile} from './atmega328p.js';
import {parseHex} from './hex.js';

// Shared filtering and controls; actual ATmega328P CPU/timers/GPIO supply audio.
export class Renderer extends AudioRenderer{
  constructor(entry,sampleRate,controls={}){
    const profile=resolveATmega328PProfile(entry.device,{cpuHz:entry.cpuHz});
    if(entry.pwmHz!==62500||(entry.audioChannels??1)!==1)throw Error('ATmega328P speech requires mono 62.5 kHz PWM');
    const core=new ATmega328P(parseHex(entry.flashHex,profile.flashBytes),
      entry.eepromHex?parseHex(entry.eepromHex,profile.eepromBytes):null,
      {target:profile.id,cpuHz:profile.cpuHz,pwmOutput:entry.pwmOutput});
    super(entry,sampleRate,controls,core,resolveATmega328PProfile);
    this.physicalAudio=true;
  }
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw Error('Invalid audio block size');
    const {physical,registers}=this.core.captureAudio(count,this.sampleRate);
    this.registerSamples=registers;return this.processRaw(physical,count);
  }
}
