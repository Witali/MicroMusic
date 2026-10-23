import {Renderer as AudioRenderer} from './renderer-js.js';
import {AVRCore} from './avr-transpiled.js';

// Reuse resampling/DSP while feeding it only the generated AVR instruction code.
export class Renderer extends AudioRenderer {
  constructor(entry,sampleRate,controls={},Core=AVRCore){super(entry,sampleRate,controls,Core);}
  render(count){
    if(!Number.isInteger(count)||count<1||count>16384)throw new Error('Invalid audio block size');
    // Forecast using the same additions/subtractions as the resampler. Capture
    // exactly what this block consumes: no CPU look-ahead at its public exit.
    let phase=this.phase,needed=this.first?2:0;
    for(let n=0;n<count;n++){phase+=this.ratio;while(phase>=1){phase--;needed++;}}
    const pwm=this.core.capturePWM(needed,this.channels);let position=0;
    this.nextValue=()=>pwm[position++];
    return super.render(count);
  }
}
