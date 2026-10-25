import { AVRCore } from './avr-reference.js?v=20261025-um88';
import { resolveAVRProfile } from './avr-profiles.js?v=20261025-um88';
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
  constructor(entry, sampleRate, {cutoff = 4000, volume = 1, filtered = true} = {}, Core = AVRCore) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid audio sample rate');
    validateControls(cutoff, volume);
    if (!Number.isFinite(entry.pwmHz) || entry.pwmHz <= 0) throw new Error('Invalid audio configuration');
    const profile = resolveAVRProfile(entry.device);
    this.core = typeof Core==='function'
      ? new Core(parseHex(entry.flashHex, profile.flashBytes), entry.eepromHex ? parseHex(entry.eepromHex, profile.eepromBytes) : null, {target:profile.id}) : Core;
    this.channels=entry.audioChannels||1;
    if(![1,2].includes(this.channels))throw new Error('Unsupported audio channel count');
    this.nextValue=this.channels===2?()=>this.core.nextStereoDuty():()=>this.core.nextDuty();
    this.sampleRate = sampleRate; this.ratio = entry.pwmHz / sampleRate;
    this.frames = 0; this.phase = 0; this.first = true; this.filtered = filtered;
    this.cutoff = this.targetCutoff = Math.min(cutoff, sampleRate * .45);
    this.volume = this.targetVolume = volume; this.smoothing = Math.exp(-1 / (sampleRate * .015));
    this.hp = {z1:0, z2:0}; this.lp = {z1:0, z2:0};
    coefficients(this.hp, sampleRate, 35, true); coefficients(this.lp, sampleRate, this.cutoff);
    this.filters=[{hp:this.hp,lp:this.lp}];
    if(this.channels===2){
      const hp={z1:0,z2:0},lp={z1:0,z2:0};
      coefficients(hp,sampleRate,35,true);coefficients(lp,sampleRate,this.cutoff);this.filters.push({hp,lp});
    }
  }
  setAudioControls({cutoff = 4000, volume = 1}) {
    validateControls(cutoff, volume);
    this.targetCutoff = Math.min(cutoff, this.sampleRate * .45); this.targetVolume = volume;
  }
  processRaw(raw,count) {
    const output=new Float32Array(raw.length);let sum=0;
    for(let n=0;n<count;n++){
      if(this.filtered){
        if(this.cutoff!==this.targetCutoff){
          this.cutoff=this.targetCutoff+(this.cutoff-this.targetCutoff)*this.smoothing;
          if(Math.abs(this.cutoff-this.targetCutoff)<1e-9)this.cutoff=this.targetCutoff;
          for(const {lp} of this.filters)coefficients(lp,this.sampleRate,this.cutoff);
        }
        this.volume=this.targetVolume+(this.volume-this.targetVolume)*this.smoothing;
      }
      for(let ch=0;ch<this.channels;ch++){
        const at=n*this.channels+ch,{hp,lp}=this.filters[ch];sum+=raw[at];
        output[at]=this.filtered?filtered(lp,filtered(hp,raw[at]))*this.volume:raw[at];
      }
    }
    this.frames+=count;this.core.rawSamples=raw;this.core.averagePWM=128+128*sum/raw.length;
    return output;
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw new Error('Invalid audio block size');
    const output = new Float32Array(count*this.channels), raw = new Float32Array(count*this.channels);
    if (this.first) { this.v0 = this.nextValue(); this.v1 = this.nextValue(); this.first = false; }
    let sum = 0;
    for (let n = 0; n < count; n++) {
      if (this.filtered) {
        if (this.cutoff !== this.targetCutoff) {
          this.cutoff = this.targetCutoff + (this.cutoff - this.targetCutoff) * this.smoothing;
          if (Math.abs(this.cutoff - this.targetCutoff) < 1e-9) this.cutoff = this.targetCutoff;
          for(const {lp} of this.filters)coefficients(lp, this.sampleRate, this.cutoff);
        }
        this.volume = this.targetVolume + (this.volume - this.targetVolume) * this.smoothing;
      }
      for(let ch=0;ch<this.channels;ch++){
        const at=n*this.channels+ch,a=this.channels===2?(this.v0>>(ch*8))&255:this.v0,b=this.channels===2?(this.v1>>(ch*8))&255:this.v1;
        raw[at]=(a+(b-a)*this.phase-128)/128;sum+=raw[at];
        const {hp,lp}=this.filters[ch];output[at]=this.filtered?filtered(lp,filtered(hp,raw[at]))*this.volume:raw[at];
      }
      this.phase += this.ratio;
      while (this.phase >= 1) { this.phase--; this.v0 = this.v1; this.v1 = this.nextValue(); }
    }
    this.frames += count; this.core.rawSamples = raw; this.core.averagePWM = 128 + 128 * sum / (count*this.channels);
    return output;
  }
}
