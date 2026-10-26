import {PhysicalAudioRenderer} from './renderer-physical.js';
import {ATtiny13A} from './attiny13a.js';
export class Renderer extends PhysicalAudioRenderer {
  constructor(entry,sampleRate,controls={},core=ATtiny13A){super(entry,sampleRate,controls,core);}
}
