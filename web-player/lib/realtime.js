// Content time versus the output device's requested audio frames. Missing
// samples are counted as lag; advancing a label never hides an underrun.
export class RealtimeMonitor {
  constructor(sampleRate) { this.sampleRate=sampleRate; this.resetAnchor(); }
  resetAnchor() { this.anchor=null; }
  observe(position, now) {
    const {frames,clockFrames}=position;
    if (!this.anchor) this.anchor={now,clockFrames};
    const wallMs=now-this.anchor.now;
    const audioMs=(clockFrames-this.anchor.clockFrames)*1000/this.sampleRate;
    return {seconds:frames/this.sampleRate,
      lagMs:Math.max(0,clockFrames-frames)*1000/this.sampleRate,
      tempoPercent:clockFrames ? frames/clockFrames*100 : 100,
      wallMs,audioMs,wallDriftMs:wallMs-audioMs,underruns:position.underruns};
  }
}
