// Execute the assembled feasibility probe, checking all phases and the PWM queue.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';
const folder='build/eight-guitar-voices';
const meta=JSON.parse(fs.readFileSync(folder+'/build-report.json'));
const rom=fs.readFileSync(folder+'/synth.bin'),ep=fs.readFileSync(folder+'/eeprom.bin');
const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
let renders=0,start=null,interrupts=0,maxElapsed=0,maxActive=0,minQueued=16,underruns=0,minSP=159;
let phaseChecks=0,mixChecks=0,previous=null,minMix=127,maxMix=-128;
const step=core.step.bind(core);
const states=()=>meta.voiceAddresses.map(a=>({phase:core.data[a]|core.data[a+1]<<8,step:core.data[a+2]|core.data[a+3]<<8}));
core.step=()=>{
  if(!core.inIRQ&&core.pc===pc.render_sample){
    const now=states();
    if(previous)for(let i=0;i<8;i++){
      assert.equal(now[i].phase,(previous[i].phase+meta.steps[i])&65535,'Each independent oscillator advances once per output');
      assert.equal(now[i].step,meta.steps[i]);phaseChecks++;
    }
    previous=now;start=core.cyc;interrupts=core.irqCount;renders++;
  }
  if(core.inIRQ&&core.pc===pc.ring_read){
    const queued=(core.r[22]-core.r[28]+16)%16;
    minQueued=Math.min(minQueued,queued);if(!queued)underruns++;
  }
  if(!core.inIRQ&&core.pc===pc.write_pwm){
    const mix=core.r[17]&128?core.r[17]-256:core.r[17];
    const values=states().map(({phase,step})=>{
      const index=phase>>12,packed=ep[(step>=1024?8:0)+(index>>1)];
      return ((index&1?packed>>4:packed)&15)-8;
    });
    const expected=Math.floor(values.slice(0,2).reduce((a,b)=>a+b,0)*core.r[4]/8)
      +Math.floor(values.slice(2).reduce((a,b)=>a+b,0)*core.r[5]/8);
    assert.equal(mix,expected,'All eight individual waveforms contribute to the output');mixChecks++;
    minMix=Math.min(minMix,mix);maxMix=Math.max(maxMix,mix);
    assert.ok(mix>=-120&&mix<=120,'Eight-voice sum has safe headroom');
  }
  step();
  minSP=Math.min(minSP,core.minSP);
  if(!core.inIRQ&&core.pc===pc.idle&&start!==null){
    const elapsed=core.cyc-start;
    maxElapsed=Math.max(maxElapsed,elapsed);
    maxActive=Math.max(maxActive,elapsed-core.maxIRQ*(core.irqCount-interrupts));start=null;
  }
};
while(core.cyc<9600000)core.step();
assert.equal(core.lost,0);assert.equal(underruns,0);
assert.ok(minSP>=143,'Stack stays above the oscillator state and PWM ring');
assert.ok(renders>18700&&renders<18800);
assert.ok(phaseChecks>149000);
let gainChecks=0;
const gainCore=new AVRCore(rom,ep,{fastIdle:false});
for(let sum=-48;sum<=42;sum++)for(let level=0;level<16;level++){
  gainCore.pc=pc.chord_gain;gainCore.r[21]=sum&255;gainCore.r[25]=level;
  while(gainCore.pc!==pc.gain_return)gainCore.step();
  const actual=gainCore.r[17]&128?gainCore.r[17]-256:gainCore.r[17];
  assert.equal(actual,Math.floor(sum*level/8)||0,'Signed chord gain retains headroom at every envelope level');gainChecks++;
}
const report={...meta,flashSha256:createHash('sha256').update(rom).digest('hex'),
  emulatedSeconds:core.cyc/9600000,renders,independentPhaseChecks:phaseChecks,eightVoiceMixChecks:mixChecks,
  chordGainChecks:gainChecks,maxRenderElapsedCycles:maxElapsed,
  maxRenderActiveCycles:maxActive,cyclesAvailablePerRender:512,minQueuedPwmBytes:minQueued,
  ringUnderruns:underruns,lostTimerEvents:core.lost,isrCycles:core.maxIRQ,
  maxStackBytes:159-minSP,sramUsedWorstCase:48+159-minSP,mixRange:[minMix,maxMix],
  limitation:'Eight continuous notes verified in emulation; score decoding, note scheduling and envelope updates are not implemented in this probe.'};
delete report.labels;
fs.writeFileSync(folder+'/verification.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
