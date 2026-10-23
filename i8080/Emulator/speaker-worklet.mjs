import { StreamingAudio } from './stream-audio.mjs';
class SpeakerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(); this.stream = new StreamingAudio(sampleRate, options.processorOptions);
    this.blocks = 0; this.reportedEnd = false;
    this.port.onmessage = ({ data }) => {
      if (data.kind === 'audio') this.stream.push(new Float32Array(data.audio));
      else if (data.kind === 'finish') this.stream.finished = true;
      else if (data.kind === 'config') this.stream.configure(data);
      else if (data.kind === 'volume') this.stream.volume = data.volume;
    };
  }
  process(inputs, outputs) {
    const output = outputs[0][0]; if (!output) return true;
    this.stream.render(output);
    if (++this.blocks % 32 === 0 || (this.stream.ended && !this.reportedEnd)) {
      this.port.postMessage({ seconds: this.stream.seconds, ended: this.stream.ended });
      if (this.stream.ended) this.reportedEnd = true;
    }
    return true;
  }
}
registerProcessor('intel8080-speaker', SpeakerProcessor);
