// Keep the input gain warm while output is selected, just like the filters.
export class SignalPoint {
  constructor(sampleRate, volume = 1) {
    this.gain = volume;
    this.smoothing = Math.exp(-1 / (sampleRate * .015));
  }
  select(output, input, channels, {signal = 'output', volume = 1} = {}) {
    if (signal === 'input' && (!input || input.length !== output.length)) throw Error('OCR input is unavailable');
    const selected = signal === 'input' ? new Float32Array(output.length) : output;
    for (let i = 0; i < output.length; i += channels) {
      this.gain = volume + (this.gain - volume) * this.smoothing;
      if (signal === 'input') for (let ch = 0; ch < channels; ch++) selected[i + ch] = input[i + ch] * this.gain;
    }
    return selected;
  }
}
