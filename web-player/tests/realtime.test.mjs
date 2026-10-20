import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Renderer } from '../lib/renderer.js';
import { RealtimeMonitor } from '../lib/realtime.js';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));

for (const entry of catalog.entries) {
  test(`${entry.id}: 60 seconds of output retain the 9.6 MHz firmware tempo`,()=>{
    const rate=48000,renderer=new Renderer(entry,rate),frames=60*rate;
    for (let i=0;i<frames;i+=4096) renderer.render(Math.min(4096,frames-i));
    const expectedCycles=frames/rate*entry.cpuHz;
    assert.ok(Math.abs(renderer.core.cyc-expectedCycles)<4096,`${renderer.core.cyc-expectedCycles} cycle drift`);
    assert.equal(renderer.core.lost,0);
    assert.equal(renderer.core.workLost,0);
    assert.equal(renderer.frames,frames);
  });
}
test('monitor reports missing sound as lag instead of hiding it in the clock',()=>{
  const monitor=new RealtimeMonitor(48000);
  monitor.observe({frames:4800,clockFrames:4800,underruns:0},0);
  const good=monitor.observe({frames:484800,clockFrames:484800,underruns:0},10000);
  assert.equal(good.tempoPercent,100); assert.equal(good.lagMs,0); assert.equal(good.wallDriftMs,0);
  const gap=monitor.observe({frames:528000,clockFrames:532800,underruns:1},11000);
  assert.equal(gap.lagMs,100); assert.ok(gap.tempoPercent<100);
  monitor.resetAnchor();
  const resumed=monitor.observe({frames:528000,clockFrames:532800,underruns:1},60000);
  assert.equal(resumed.wallMs,0); assert.equal(resumed.lagMs,100);
});
