// Fixed memory and demand-driven production: neither paused nor hidden tabs
// accumulate an unlimited backlog of samples.
export class AudioQueue {
  constructor(capacity = 32768, channels = 1) {
    if (![1, 2].includes(channels)) throw new Error('Unsupported audio channel count');
    this.channels = channels; this.capacity = capacity;
    this.data = new Float32Array(capacity * channels); this.clear();
  }
  clear() { this.read = this.write = this.size = 0; }
  push(samples) {
    const frames = samples.length / this.channels;
    if (!Number.isInteger(frames)) throw new Error('Incomplete interleaved audio frame');
    if (frames > this.capacity - this.size) throw new Error('Audio queue overflow');
    for (let i = 0; i < samples.length; i++) {
      this.data[this.write] = samples[i]; this.write = (this.write + 1) % this.data.length;
    }
    this.size += frames;
  }
  take(output) {
    const outputs = Array.isArray(output) ? output : [output];
    if (outputs.length < this.channels) throw new Error('Missing output channel');
    const count = Math.min(outputs[0].length, this.size);
    for (let i = 0; i < count; i++) {
      for (let ch = 0; ch < this.channels; ch++) {
        outputs[ch][i] = this.data[this.read]; this.read = (this.read + 1) % this.data.length;
      }
    }
    if (this.channels === 1) for (let ch = 1; ch < outputs.length; ch++) outputs[ch].set(outputs[0].subarray(0, count));
    for (const channel of outputs) channel.fill(0, count);
    this.size -= count;
    return count;
  }
}
