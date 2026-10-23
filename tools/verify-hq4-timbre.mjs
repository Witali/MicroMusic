// Verify the actual HEX against an independently generated numerical-model PCM.
import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore as JS} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';
const [imagePath,expectedPath,reportPath]=process.argv.slice(2);
if(!imagePath||!expectedPath)throw new Error('Usage: node tools/verify-hq4-timbre.mjs firmware.bin expected.raw [report.json]');
const image=readFileSync(imagePath),expected=readFileSync(expectedPath);
const hash=x=>createHash('sha256').update(x).digest('hex');
const js=new JS(image),wasm=new Wasm(image),slow=new Wasm(image,null,{fastIdle:false,fastBlocks:false});
let minPeriod=Infinity,maxPeriod=0,previous=0;
for(let i=0;i<expected.length;i++){
  for(const [name,cpu] of [['JS',js],['WASM',wasm],['WASM unoptimized',slow]])
    assert.equal(cpu.nextDuty(),expected[i],`${name} sample ${i}`);
  assert.deepEqual(js.data,wasm.data,`JS/WASM memory ${i}`);
  assert.deepEqual(slow.data,wasm.data,`slow/fast memory ${i}`);
  for(const key of ['cyc','pc','irqCount','lost','maxIRQ','writes','minSP']){
    assert.equal(js[key],wasm[key],`${key} ${i}`);
    assert.equal(slow[key],wasm[key],`slow ${key} ${i}`);
  }
  if(i){minPeriod=Math.min(minPeriod,wasm.cyc-previous);maxPeriod=Math.max(maxPeriod,wasm.cyc-previous);}
  previous=wasm.cyc;
}
assert.equal(wasm.lost,0);
assert.equal(wasm.irqCount,expected.length*5);
assert.equal(wasm.workLost,0);
// Every sample needs exactly five PWM overflows. ISR return timing can vary by
// foreground instruction latency; a missed sample would add 1280 cycles.
assert.ok(minPeriod>=1276&&maxPeriod<=1284,`sample period ${minPeriod}..${maxPeriod}`);
assert.ok(wasm.minSP>=0x78,'stack collides with lattice states');
const report={pass:true,hardwareTested:false,samples:expected.length,flashBytes:image.length,
  imageSha256:hash(image),pcmSha256:hash(expected),mismatches:0,irqCount:wasm.irqCount,
  lostOverflows:wasm.lost,missedSamples:wasm.workLost,maxISRCycles:wasm.maxIRQ,
  minimumSamplePeriod:minPeriod,maximumSamplePeriod:maxPeriod,minimumSP:wasm.minSP};
if(reportPath)writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
