import {Renderer as AudioRenderer} from './renderer-js.js';
import {ATtiny13A} from './attiny13a.js';
export class Renderer extends AudioRenderer {
  constructor(entry,sampleRate,controls={}){super(entry,sampleRate,controls,ATtiny13A);}
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw Error('Invalid audio block size');
    return this.processRaw(this.core.capturePhysical(count,this.sampleRate,this.channels),count);
  }
}
