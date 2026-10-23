import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRenderer} from '../lib/engines.js';
import {sameCPU} from './helpers/avr-test-state.mjs';

const music=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const speech=JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url)));
for(const entry of [...music.entries,...speech.entries])for(const rate of [22050,48000])
test(`${entry.id}/${rate}: browser-selectable transpiled renderer preserves mono/stereo PCM and timing`,async()=>{
  const controls={cutoff:9000,volume:.65},a=await createRenderer(entry,rate,controls,'transpiled'),b=await createRenderer(entry,rate,controls,'wasm');
  assert.equal(a.engine,'transpiled');
  for(const count of [1,127,1024]){
    const actual=a.render(count),expected=b.render(count);let max=0;
    assert.equal(actual.length,expected.length);
    for(let i=0;i<actual.length;i++)max=Math.max(max,Math.abs(actual[i]-expected[i]));
    assert.ok(max<2e-7,'PCM error '+max);assert.deepEqual(a.core.rawSamples,b.core.rawSamples);sameCPU(a.core,b.core);
  }
  for(const renderer of [a,b])renderer.setAudioControls({cutoff:4000,volume:.2});
  const actual=a.render(1024),expected=b.render(1024);
  for(let i=0;i<actual.length;i++)assert.ok(Math.abs(actual[i]-expected[i])<2e-7,'smoothed PCM');
  sameCPU(a.core,b.core);
});
