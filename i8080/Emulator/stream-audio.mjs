import { SignalFilter } from './signal.mjs';

export class StreamingAudio {
  constructor(deviceRate, options = {}) {
    this.deviceRate = deviceRate; this.rate = options.rate || 96000;
    this.chunks = []; this.offset = 0; this.phase = 0; this.previous = null; this.next = null;
    this.sourceFrames = 0; this.finished = false; this.ended = false; this.volume = 0.65;
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
      output[i] = (this.previous + ((this.next ?? this.previous) - this.previous) * this.phase) * this.volume;
      this.phase += this.rate / this.deviceRate;
    }
  }
  get seconds() { return this.ended ? this.sourceFrames / this.rate : Math.max(0, (this.sourceFrames - 2 + Math.min(this.phase, 1)) / this.rate); }
}
