function createWorkletURL() { return new URL('./speaker-worklet.mjs', import.meta.url); }

export class RealtimeSpeaker {
  constructor(onStatus) { this.onStatus = onStatus; this.context = null; this.node = null; this.analyser = null; this.scopeBuffer = null; this.active = false; this.paused = false; }
  async start(options) {
    this.reset();
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) throw Error('Браузер не поддерживает Web Audio');
    const context = this.context = new Context({ latencyHint: 'interactive' });
    // Called during the user's click, before awaiting module loading.
    const resume = context.resume();
    if (!context.audioWorklet) { this.reset(); throw Error('Для звука нужен AudioWorklet: откройте страницу через localhost, HTTPS или автономный HTML.'); }
    const url = createWorkletURL();
    try { await context.audioWorklet.addModule(url); await resume; }
    finally { if (typeof url === 'string' && url.startsWith('blob:')) URL.revokeObjectURL(url); }
    if (this.context !== context) return false;
    this.node = new AudioWorkletNode(context, 'intel8080-speaker', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [1], processorOptions: options });
    this.node.port.onmessage = ({ data }) => { if (this.context === context) { if (data.ended) { this.active = false; context.suspend().catch(() => {}); } this.onStatus(data); } };
    this.analyser = context.createAnalyser();
    // Match the ATtiny13A player's 4096 device-frame window.
    this.analyser.fftSize = 4096;
    this.scopeBuffer = new Float32Array(this.analyser.fftSize);
    this.node.connect(this.analyser); this.analyser.connect(context.destination);
    this.active = true; this.paused = false; return true;
  }
  readScope() {
    if (!this.analyser) return null;
    this.analyser.getFloatTimeDomainData(this.scopeBuffer);
    return this.scopeBuffer;
  }
  get scopeMilliseconds() { return 4096 / (this.context?.sampleRate || 48000) * 1000; }
  push(samples) { this.node?.port.postMessage({ kind: 'audio', audio: samples }, [samples]); }
  finish() { this.node?.port.postMessage({ kind: 'finish' }); }
  configure(options) { this.node?.port.postMessage({ kind: 'config', ...options }); }
  volume(volume) { this.node?.port.postMessage({ kind: 'volume', volume }); }
  async togglePause() {
    if (!this.active) return;
    this.paused = !this.paused;
    if (this.paused) await this.context.suspend(); else await this.context.resume();
  }
  reset() {
    this.active = this.paused = false;
    if (this.node) { this.node.disconnect(); this.node.port.close(); this.node = null; }
    if (this.analyser) { this.analyser.disconnect(); this.analyser = null; this.scopeBuffer = null; }
    if (this.context) { this.context.close().catch(() => {}); this.context = null; }
  }
}
