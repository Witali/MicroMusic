import { AVRCore } from './avr-core.js';
import { parseHex } from './hex.js';

export class Renderer {
  constructor(entry, sampleRate) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid audio sample rate');
    this.core = new AVRCore(parseHex(entry.flashHex), entry.eepromHex ? parseHex(entry.eepromHex, 64) : null);
    this.channels = entry.audioChannels || 1;
    if (![1, 2].includes(this.channels)) throw new Error('Unsupported audio channel count');
    this.nextValue = this.channels === 2 ? () => this.core.nextStereoDuty() : () => this.core.nextDuty();
    this.ratio = entry.pwmHz / sampleRate;
    this.sampleRate = sampleRate;
    this.phase = 0; this.first = true; this.frames = 0;
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw new Error('Invalid audio block size');
    // Interleaved frames: L,R,L,R for stereo; one scalar per frame for mono.
    const output = new Float32Array(count * this.channels);
    if (this.first) { this.v0 = this.nextValue(); this.v1 = this.nextValue(); this.first = false; }
    for (let i = 0; i < count; i++) {
      if (this.channels === 2) {
        const l0 = this.v0 & 255, l1 = this.v1 & 255, r0 = this.v0 >> 8, r1 = this.v1 >> 8;
        output[i * 2] = (l0 + (l1 - l0) * this.phase - 128) / 128;
        output[i * 2 + 1] = (r0 + (r1 - r0) * this.phase - 128) / 128;
      } else output[i] = (this.v0 + (this.v1 - this.v0) * this.phase - 128) / 128;
      this.phase += this.ratio;
      while (this.phase >= 1) { this.phase--; this.v0 = this.v1; this.v1 = this.nextValue(); }
    }
    this.frames += count;
    return output;
  }
}
