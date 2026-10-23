// Stateful reconstruction shared by live playback and WAV export.
export class SignalFilter {
  constructor(rate, cutoff = 4500, poles = 4, normalize = true) {
    this.rate = rate; this.cutoff = cutoff; this.normalize = normalize;
    this.states = new Float64Array(poles); this.alpha = 1 - Math.exp(-2 * Math.PI * cutoff / rate);
    this.highpass = Math.exp(-2 * Math.PI * 20 / rate);
    this.previous = null; this.dc = 0; this.envelope = 0; this.gain = 1;
    this.decay = Math.exp(-1 / rate); this.gainRise = 1 - Math.exp(-1 / (0.02 * rate));
  }
  step(raw) {
    const input = raw * 2 - 1;
    if (this.previous === null) this.previous = input;
    this.dc = this.highpass * (this.dc + input - this.previous); this.previous = input;
    let value = this.dc;
    if (this.cutoff) for (let i = 0; i < this.states.length; i++) { this.states[i] += this.alpha * (value - this.states[i]); value = this.states[i]; }
    if (this.normalize) {
      this.envelope = Math.max(Math.abs(value), this.envelope * this.decay);
      const desired = Math.min(1024, 0.85 / Math.max(this.envelope, 1e-7));
      // Reduce gain immediately on a new peak; recover gently during quiet passages.
      this.gain = desired < this.gain ? desired : this.gain + this.gainRise * (desired - this.gain);
      value *= this.gain;
    }
    return Math.max(-1, Math.min(1, value));
  }
}
