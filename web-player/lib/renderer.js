import { AVRCore } from './avr-core.js?v=20261025-board-um88';
import { resolveAVRProfile } from './avr-profiles.js?v=20261025-board-um88';
import { parseHex } from './hex.js';

export class Renderer {
  constructor(entry, sampleRate, controls = {}) {
    if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new Error('Invalid audio sample rate');
    const profile = resolveAVRProfile(entry.device,{cpuHz:entry.cpuHz});
    this.core = new AVRCore(parseHex(entry.flashHex, profile.flashBytes),
      entry.eepromHex ? parseHex(entry.eepromHex, profile.eepromBytes) : null, {target:profile.id,cpuHz:profile.cpuHz});
    this.ratio = entry.pwmHz / sampleRate;
    this.sampleRate = sampleRate;
    this.frames = 0;
    this.channels=entry.audioChannels||1;
    this.core.configureAudio(sampleRate,entry.pwmHz,{...controls,channels:this.channels});
  }
  render(count) {
    if (!Number.isInteger(count) || count < 1 || count > 16384) throw new Error('Invalid audio block size');
    const output = this.core.render(count);
    this.frames += count;
    return output;
  }
  setAudioControls(controls) { this.core.setAudioControls(controls); }
}
