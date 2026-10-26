import {Renderer as AudioRenderer} from './renderer-js.js';
import {AT13_IO as IO} from './attiny13a-registers.js';

export class PhysicalAudioRenderer extends AudioRenderer {
  constructor(entry, sampleRate, controls, Core) {
    super(entry, sampleRate, controls, Core);
    this.physicalAudio = true;
    this.registerInput = controls?.signal === 'input';
  }
  setAudioControls(controls) {
    super.setAudioControls(controls);
    this.registerInput = controls.signal === 'input';
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw Error('Invalid audio block size');
    this.registerSamples = null;
    let raw;
    if (this.registerInput) {
      // Physical capture is the pin waveform, not the value written to OCR.
      // Read the official device registers at each host audio frame instead.
      raw = new Float32Array(count * this.channels);
      this.registerSamples = new Float32Array(raw.length);
      for (let n = 0; n < count; n++) {
        raw.set(this.core.capturePhysical(1, this.sampleRate, this.channels), n * this.channels);
        for (let ch = 0; ch < this.channels; ch++) {
          const address = this.channels === 2 && ch === 0 ? IO.OCR0A : IO.OCR0B;
          this.registerSamples[n * this.channels + ch] = (this.core.readIO(address) - 128) / 128;
        }
      }
    } else raw = this.core.capturePhysical(count, this.sampleRate, this.channels);
    // Keep the physical output filters running when listening to OCR.
    return this.processRaw(raw, count);
  }
}
