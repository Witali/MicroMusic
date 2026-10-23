import { AudioQueue } from './lib/audio-queue.js';
class FirmwareOutput extends AudioWorkletProcessor {
  constructor() {
    super(); this.queue = new AudioQueue(); this.playing = false;
    this.frames = this.clockFrames = this.underruns = this.reportAt = 0; this.started = false; this.primed = this.requested = false;
    this.port.onmessage = ({data}) => {
      if (data.type === 'playing') this.playing = data.value;
      if (data.type === 'connect' || data.type === 'disconnect') {
        this.session = data.session;
        this.source?.close(); this.source = null; this.queue = new AudioQueue(32768, data.channels || 1);
        this.playing = this.primed = this.requested = false;
        this.frames = this.clockFrames = this.underruns = this.reportAt = 0; this.started = false;
        if (data.port) {
          this.source = data.port;
          const source = this.source;
          this.source.onmessage = ({data}) => {
            if (this.source !== source) return;
            if (data.type === 'samples') { this.queue.push(data.samples); this.requested = false; }
            if (data.type === 'error') { this.playing = false; this.queue.clear(); }
          };
          this.source.start();
        }
      }
    };
  }
  process(inputs, outputs) {
    const channels = outputs[0], out = channels[0];
    for (const channel of channels) channel.fill(0);
    if (!this.playing || !this.source) return true;
    if (!this.requested && this.queue.size <= 8192) {
      this.requested = true; this.source.postMessage({type:'need',frames:4096});
    }
    if (!this.primed && this.queue.size >= 8192) { this.primed = true; this.started = true; }
    if (this.started) this.clockFrames += out.length;
    if (this.primed) {
      const count = this.queue.take(channels); this.frames += count;
      if (count < out.length) { this.underruns++; this.primed = false; }
    }
    if (this.clockFrames - this.reportAt >= 2048) {
      this.reportAt = this.clockFrames;
      this.port.postMessage({type:'position',session:this.session,frames:this.frames,clockFrames:this.clockFrames,underruns:this.underruns,buffered:this.queue.size});
    }
    return true;
  }
}
registerProcessor('firmware-output', FirmwareOutput);
