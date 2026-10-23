import {Renderer as AudioRenderer} from './renderer-js.js';
import {AVRCore} from './avr-transpiled.js';

// Reuse resampling/DSP while feeding it only the generated AVR instruction code.
export class Renderer extends AudioRenderer {
  constructor(entry,sampleRate,controls={}){super(entry,sampleRate,controls,AVRCore);}
}
