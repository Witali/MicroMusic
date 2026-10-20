// Fixed memory and demand-driven production: neither paused nor hidden tabs
// accumulate an unlimited backlog of samples.
export class AudioQueue {
  constructor(capacity = 32768) { this.data = new Float32Array(capacity); this.clear(); }
  clear() { this.read = this.write = this.size = 0; }
  push(samples) {
    if (samples.length > this.data.length - this.size) throw new Error('Audio queue overflow');
    for (let i = 0; i < samples.length; i++) {
      this.data[this.write] = samples[i]; this.write = (this.write + 1) % this.data.length;
    }
    this.size += samples.length;
  }
  take(output) {
    const count = Math.min(output.length, this.size);
    for (let i = 0; i < count; i++) { output[i] = this.data[this.read]; this.read = (this.read + 1) % this.data.length; }
    output.fill(0, count); this.size -= count;
    return count;
  }
}
