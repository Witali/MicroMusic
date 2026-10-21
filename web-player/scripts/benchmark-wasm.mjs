import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {cpus,platform,arch} from 'node:os';
import assert from 'node:assert/strict';
import {Renderer} from '../lib/renderer.js';
import {ReferenceRenderer} from '../tests/helpers/reference-audio.mjs';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const manifest=JSON.parse(readFileSync(new URL('../wasm/build.json',import.meta.url)));
const median=a=>a.sort((x,y)=>x-y)[a.length>>1],sampleRate=48000,seconds=3;
const controls={cutoff:9000,volume:.65},results=[];
function run(Type,entry,duration=seconds){
  const renderer=new Type(entry,sampleRate,controls),started=performance.now();let checksum=0;
  for(let offset=0;offset<sampleRate*duration;offset+=4096){const out=renderer.render(Math.min(4096,sampleRate*duration-offset));checksum+=out[out.length-1];}
  return{renderer,checksum,ms:(performance.now()-started)/duration};
}
for(const entry of catalog.entries){
  run(Renderer,entry,1);run(ReferenceRenderer,entry,1);
  const js=[],wasm=[];
  for(let trial=0;trial<7;trial++){
    const types=trial%2?[Renderer,ReferenceRenderer]:[ReferenceRenderer,Renderer];
    const samples=types.map(Type=>[Type,run(Type,entry)]),a=samples[0][1],b=samples[1][1];
    assert.equal(a.renderer.core.cyc,b.renderer.core.cyc);
    assert.equal(a.renderer.core.irqCount,b.renderer.core.irqCount);
    assert.deepEqual(a.renderer.core.data,b.renderer.core.data);
    assert.ok(Math.abs(a.checksum-b.checksum)<2e-6,'Filtered PCM checksum');
    for(const [Type,result]of samples)(Type===Renderer?wasm:js).push(result.ms);
  }
  const jsMs=median(js),wasmMs=median(wasm);
  results.push({id:entry.id,flashSha256:entry.flashSha256,eepromSha256:entry.eepromSha256,
    jsMs,wasmMs,speedup:jsMs/wasmMs,realtimeHeadroom:1000/wasmMs});
}
const hash=p=>createHash('sha256').update(readFileSync(new URL(p,import.meta.url))).digest('hex');
const report={runtime:process.version,platform:platform(),arch:arch(),cpu:cpus()[0].model,
  sampleRate,controls,compiler:manifest.compilerVersion,wasmBytes:manifest.bytes,memoryBytes:65536,
  nativeSourceSha256:manifest.inputs['web-player/native/avr.c'],wasmSha256:manifest.artifacts['avr.wasm'],
  jsReferenceSha256:hash('../lib/avr-reference.js'),
  method:'Median of seven warmed alternating runs of three seconds, normalized to one second. Same firmware, resampling, 35-Hz HPF, 9-kHz LPF (Q=0.5), gain=0.65. JS uses the previous block interpreter and independent Direct Form I filtering; C/WASM uses one call per audio block and transposed Direct Form II. Construction/compilation excluded. Final memory, cycles, IRQs and filtered PCM checksum verified.',results};
writeFileSync(new URL('../reports/wasm-benchmark.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.table(results.map(r=>({firmware:r.id,js_ms:r.jsMs.toFixed(2),wasm_ms:r.wasmMs.toFixed(2),speedup:r.speedup.toFixed(2)+'x',headroom:r.realtimeHeadroom.toFixed(1)+'x'})));
