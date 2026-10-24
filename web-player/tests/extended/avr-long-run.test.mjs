// Explicit extended suite: full five-minute runs include the end and restart
// of all current arrangements. No audio samples or MIDI fixtures are stored.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Renderer} from '../../lib/renderer.js';
import {ReferenceRenderer} from '../helpers/reference-audio.mjs';
import {sameCPU} from '../helpers/avr-test-state.mjs';
const catalog=JSON.parse(readFileSync(new URL('../../firmware.json',import.meta.url)));
for(const entry of catalog.entries)test(entry.id+': five minutes retain every PCM sample, CPU state, IRQ and fixed memory',()=>{
  const rate=48000,seconds=300,controls={cutoff:9000,volume:.65};
  const a=new Renderer(entry,rate,controls),b=new ReferenceRenderer(entry,rate,controls);
  const memory=a.core._exports.memory.buffer;let max=0,blocks=0,renderedFrames=0,startupOffset;
  for(let offset=0;offset<rate*seconds;offset+=4096){
    const count=Math.min(4096,rate*seconds-offset),actual=a.render(count),expected=b.render(count);
    assert.deepEqual(a.core.rawSamples,b.rawSamples);
    assert.equal(actual.length,expected.length);
    for(let n=0;n<actual.length;n++)max=Math.max(max,Math.abs(actual[n]-expected[n]));
    sameCPU(a.core,b.core,entry.id+' block '+blocks++);
    assert.equal(a.core.lost,0);assert.equal(a.core.workLost,0);
    assert.equal(a.core._exports.memory.buffer,memory);assert.equal(memory.byteLength,131072);
    renderedFrames+=count;
    const clockOffset=a.core.cyc-renderedFrames/rate*entry.cpuHz;
    if(startupOffset===undefined){
      // Reset/firmware initialization and the resampler's two lookahead PWM
      // values are fixed latency, distinct from accumulated clock drift.
      startupOffset=clockOffset;assert.ok(Math.abs(startupOffset)<4096,'Bounded startup latency');
    }
    assert.ok(Math.abs(clockOffset-startupOffset)<=entry.cpuHz/entry.pwmHz,'No accumulated clock drift');
  }
  assert.ok(max<2e-7,'Full filtered PCM error '+max);
  assert.equal(a.core.irqCount,seconds*entry.pwmHz+2,'Nominal IRQ count plus two resampler lookahead samples');
  assert.equal(a.core.irqCount,a.core.writes,'Each actual overflow interrupt must produce exactly one PWM write');
  if(entry.audioChannels===2)assert.equal(a.core.leftWrites,a.core.writes,'Both PWM channels advance synchronously');
  assert.equal(a.frames,rate*seconds);
});
