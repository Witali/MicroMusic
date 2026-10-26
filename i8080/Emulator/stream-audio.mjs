import { SignalFilter } from './signal.mjs';

export class StreamingAudio {
  constructor(deviceRate, options = {}) {
    this.deviceRate = deviceRate; this.rate = options.rate ?? 96000;
    for (const value of [this.rate, deviceRate])
      if (!Number.isInteger(value) || value < 8000 || value > 192000) throw Error('Invalid audio sample rate');
    this.chunks = []; this.offset = 0; this.phase = 0; this.previous = null; this.next = null;
    this.sourceFrames = 0; this.finished = false; this.ended = false; this.volume = 0.65;
    if (this.rate > deviceRate) {
      // A real output device cannot reproduce frequencies above its Nyquist
      // limit. Reject them BEFORE decimation, independently of the user's RC.
      this.radius = Math.ceil(48 * this.rate / 96000);
      this.history = new Float64Array(2 ** Math.ceil(Math.log2(2 * this.radius + 4)));
      this.outputFrames = 0; this.kernels = new Map();
      const gcd = (a, b) => b ? gcd(b, a % b) : a;
      this.phases = Math.min(1024, deviceRate / gcd(this.rate, deviceRate));
      // Build coefficient tables before the real-time callbacks, not per block.
      for (let phase = 0; phase < this.phases; phase++) this.kernel(phase);
    }
    this.configure(options);
  }
  configure(options = {}) {
    this.filter = new SignalFilter(this.rate, options.cutoff ?? 4500, options.poles ?? 4, options.normalize ?? true);
    if (options.volume !== undefined) this.volume = options.volume;
  }
  push(samples) { if (samples.length) this.chunks.push(samples); }
  take() {
    if (!this.chunks.length) return null;
    const value = this.chunks[0][this.offset++]; this.sourceFrames++;
    if (this.offset === this.chunks[0].length) { this.chunks.shift(); this.offset = 0; }
    return this.filter.step(value);
  }
  render(output) {
    output.fill(0);
    if (this.ended) return;
    if (this.history) { this.renderDownsampled(output); return; }
    for (let i = 0; i < output.length; i++) {
      if (this.previous === null) this.previous = this.take();
      if (this.previous === null) { if (this.finished) this.ended = true; break; }
      if (this.next === null) this.next = this.take();
      if (this.next === null && !this.finished) break;
      while (this.phase >= 1) {
        this.previous = this.next; this.next = this.take(); this.phase--;
        if (this.previous === null) { this.ended = this.finished; break; }
        if (this.next === null) break;
      }
      if (this.previous === null || (this.next === null && !this.finished)) break;
      if (this.next === null && this.finished && this.phase >= 1) { this.ended = true; break; }
      const value = (this.previous + ((this.next ?? this.previous) - this.previous) * this.phase) * this.volume;
      output[i] = Math.max(-1, Math.min(1, value));
      this.phase += this.rate / this.deviceRate;
    }
  }
  kernel(phase) {
    let weights = this.kernels.get(phase);
    if (weights) return weights;
    weights = new Float64Array(2 * this.radius + 1);
    const cutoff = .45 * this.deviceRate / this.rate, fraction = phase / this.phases;
    let sum = 0;
    for (let k = -this.radius; k <= this.radius; k++) {
      const x = k - fraction, a = Math.PI * x / this.radius;
      const window = Math.abs(x) > this.radius ? 0 : .42 + .5 * Math.cos(a) + .08 * Math.cos(2 * a);
      const value = (x === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * x) / (Math.PI * x)) * window;
      weights[k + this.radius] = value; sum += value;
    }
    for (let k = 0; k < weights.length; k++) weights[k] /= sum;
    this.kernels.set(phase, weights); return weights;
  }
  renderDownsampled(output) {
    for (let i = 0; i < output.length; i++) {
      const position = this.outputFrames * this.rate / this.deviceRate;
      let center = Math.floor(position), phase = Math.round((position - center) * this.phases);
      if (phase === this.phases) { center++; phase = 0; }
      const right = center + this.radius, mask = this.history.length - 1;
      while (this.sourceFrames <= right) {
        const value = this.take();
        if (value === null) break;
        this.history[(this.sourceFrames - 1) & mask] = value;
      }
      // Save partial lookahead on underrun; do not advance the output clock.
      if (!this.finished && this.sourceFrames <= right) break;
      if (this.finished && position >= this.sourceFrames) { this.ended = true; break; }
      const weights = this.kernel(phase); let value = 0;
      for (let k = -this.radius; k <= this.radius; k++) {
        const at = center + k;
        if (at >= 0 && at < this.sourceFrames) value += weights[k + this.radius] * this.history[at & mask];
      }
      output[i] = Math.max(-1, Math.min(1, value * this.volume)); this.outputFrames++;
    }
  }
  get seconds() {
    if (this.ended) return this.sourceFrames / this.rate;
    if (this.history) return this.outputFrames / this.deviceRate;
    return Math.max(0, (this.sourceFrames - 2 + Math.min(this.phase, 1)) / this.rate);
  }
}
