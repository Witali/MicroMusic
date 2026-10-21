import { AVRCore } from './avr-reference.js';
import { parseHex } from './hex.js';

// Same resampling, Q=0.5 biquads and 15-ms control smoothing as the C engine.
// The test oracle keeps a separate Direct Form I implementation.
function coefficients(filter, rate, hz, highpass = false) {
  const w = 2 * Math.PI * hz / rate, c = Math.cos(w), a = Math.sin(w), a0 = 1 + a;
  filter.b0 = (1 + (highpass ? c : -c)) / (2 * a0);
  filter.b1 = (highpass ? -(1 + c) : 1 - c) / a0;
  filter.b2 = filter.b0; filter.a1 = -2 * c / a0; filter.a2 = (1 - a) / a0;
}
function filtered(filter, x) {
  const y = filter.b0 * x + filter.z1;
  filter.z1 = filter.b1 * x - filter.a1 * y + filter.z2;
  filter.z2 = filter.b2 * x - filter.a2 * y;
  return y;
}
function validateControls(cutoff, volume) {
  if (!Number.isFinite(cutoff) || cutoff <= 0 || !Number.isFinite(volume) || volume < 0 || volume > 1)
    throw new Error('Invalid audio configuration');
}

export class Renderer {
  constructor(entry, sampleRate, {cutoff = 4000, volume = 1, filtered = true} = {}) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid audio sample rate');
    validateControls(cutoff, volume);
    if (!Number.isFinite(entry.pwmHz) || entry.pwmHz <= 0) throw new Error('Invalid audio configuration');
    this.core = new AVRCore(parseHex(entry.flashHex), entry.eepromHex ? parseHex(entry.eepromHex, 64) : null);
    this.sampleRate = sampleRate; this.ratio = entry.pwmHz / sampleRate;
    this.frames = 0; this.phase = 0; this.first = true; this.filtered = filtered;
    this.cutoff = this.targetCutoff = Math.min(cutoff, sampleRate * .45);
    this.volume = this.targetVolume = volume; this.smoothing = Math.exp(-1 / (sampleRate * .015));
    this.hp = {z1:0, z2:0}; this.lp = {z1:0, z2:0};
    coefficients(this.hp, sampleRate, 35, true); coefficients(this.lp, sampleRate, this.cutoff);
  }
  setAudioControls({cutoff = 4000, volume = 1}) {
    validateControls(cutoff, volume);
    this.targetCutoff = Math.min(cutoff, this.sampleRate * .45); this.targetVolume = volume;
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw new Error('Invalid audio block size');
    const output = new Float32Array(count), raw = new Float32Array(count);
    if (this.first) { this.v0 = this.core.nextDuty(); this.v1 = this.core.nextDuty(); this.first = false; }
    let sum = 0;
    for (let n = 0; n < count; n++) {
      raw[n] = (this.v0 + (this.v1 - this.v0) * this.phase - 128) / 128; sum += raw[n];
      if (this.filtered) {
        if (this.cutoff !== this.targetCutoff) {
          this.cutoff = this.targetCutoff + (this.cutoff - this.targetCutoff) * this.smoothing;
          if (Math.abs(this.cutoff - this.targetCutoff) < 1e-9) this.cutoff = this.targetCutoff;
          coefficients(this.lp, this.sampleRate, this.cutoff);
        }
        this.volume = this.targetVolume + (this.volume - this.targetVolume) * this.smoothing;
        output[n] = filtered(this.lp, filtered(this.hp, raw[n])) * this.volume;
      } else output[n] = raw[n];
      this.phase += this.ratio;
      while (this.phase >= 1) { this.phase--; this.v0 = this.v1; this.v1 = this.core.nextDuty(); }
    }
    this.frames += count; this.core.rawSamples = raw; this.core.averagePWM = 128 + 128 * sum / count;
    return output;
  }
}
