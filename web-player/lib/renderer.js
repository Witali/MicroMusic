import { AVRCore } from './avr-core.js';
import { parseHex } from './hex.js';

export class Renderer {
  constructor(entry, sampleRate) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid audio sample rate');
    this.core = new AVRCore(parseHex(entry.flashHex), entry.eepromHex ? parseHex(entry.eepromHex, 64) : null);
    this.ratio = entry.pwmHz / sampleRate;
    this.sampleRate = sampleRate;
    this.phase = 0; this.first = true; this.frames = 0;
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw new Error('Invalid audio block size');
    const output = new Float32Array(count);
    if (this.first) { this.v0 = this.core.nextDuty(); this.v1 = this.core.nextDuty(); this.first = false; }
    for (let i = 0; i < count; i++) {
      output[i] = (this.v0 + (this.v1 - this.v0) * this.phase - 128) / 128;
      this.phase += this.ratio;
      while (this.phase >= 1) { this.phase--; this.v0 = this.v1; this.v1 = this.core.nextDuty(); }
    }
    this.frames += count;
    return output;
  }
}
