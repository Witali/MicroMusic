import {Renderer as AudioRenderer} from './renderer-js.js?v=20261026-emulation-config';
import {ATtiny13A} from './attiny13a.js';
export class Renderer extends AudioRenderer {
  constructor(entry,sampleRate,controls={},core=ATtiny13A,coreOptions={}){super(entry,sampleRate,controls,core,coreOptions);}
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw Error('Invalid audio block size');
    return this.processRaw(this.core.capturePhysical(count,this.sampleRate,this.channels),count);
  }
}
