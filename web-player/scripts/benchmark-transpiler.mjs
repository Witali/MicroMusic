import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {cpus,platform,arch} from 'node:os';
import assert from 'node:assert/strict';
import {Renderer as NativeRenderer} from '../lib/renderer.js';
import {Renderer as AudioRenderer} from '../lib/renderer-js.js';
import {AVRCore} from '../lib/avr-transpiled.js';
import {sameCPU} from '../tests/helpers/avr-test-state.mjs';

const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const speech=JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url)));
const controls={cutoff:9000,volume:.65},rate=48000,seconds=1,trials=5;
class AllFlags extends AVRCore{constructor(rom,eeprom){super(rom,eeprom,{optimizeFlags:false});}}
const make=(engine,entry)=>engine==='interpreter'?new NativeRenderer(entry,rate,controls):new AudioRenderer(entry,rate,controls,engine==='translated'?AVRCore:AllFlags);
function execute(renderer){
  const start=performance.now();let checksum=0;
  for(let n=0;n<rate*seconds;n+=4096){const output=renderer.render(Math.min(4096,rate*seconds-n));checksum+=output[output.length-1];}
  return {ms:(performance.now()-start)/seconds,checksum};
}
const median=values=>values.sort((a,b)=>a-b)[values.length>>1],results=[];
for(const entry of [...catalog.entries,...speech.entries]){
  const engines=['interpreter','translated','allFlags'],samples=Object.fromEntries(engines.map(e=>[e,[]])),construction=[];
  for(const engine of engines)execute(make(engine,entry));
  let generated;
  for(let trial=0;trial<trials;trial++){
    const measured=[];
    for(const engine of trial%2?[...engines].reverse():engines){
      const before=performance.now(),renderer=make(engine,entry),buildMs=performance.now()-before;
      if(engine==='translated'){generated=renderer.core;construction.push(buildMs);}
      const result=execute(renderer);samples[engine].push(result.ms);measured.push({renderer,...result});
    }
    for(const result of measured.slice(1)){
      sameCPU(result.renderer.core,measured[0].renderer.core);
      assert.ok(Math.abs(result.checksum-measured[0].checksum)<2e-6,'PCM checksum');
      assert.deepEqual(result.renderer.core.rawSamples,measured[0].renderer.core.rawSamples);
    }
  }
  const interpreterMs=median(samples.interpreter),translatedMs=median(samples.translated),allFlagsMs=median(samples.allFlags);
  results.push({id:entry.id,flashSha256:entry.flashSha256,eepromSha256:entry.eepromSha256,
    interpreterMs,translatedMs,allFlagsMs,translationSpeedup:interpreterMs/translatedMs,flagEliminationSpeedup:allFlagsMs/translatedMs,
    realtimeHeadroom:1000/translatedMs,constructionMs:median(construction),moduleBytes:generated.transpiledBytes.length,...generated.transpilation.stats});
}
const hash=path=>createHash('sha256').update(readFileSync(new URL(path,import.meta.url),'utf8').replaceAll('\r\n','\n')).digest('hex');
const report={runtime:process.version,platform:platform(),arch:arch(),cpu:cpus()[0].model,sampleRate:rate,seconds,trials,controls,
  sources:Object.fromEntries(['../lib/avr-transpiler.js','../lib/avr-transpiled.js','../lib/renderer-js.js','../native/avr.c','./benchmark-transpiler.mjs'].map(p=>[p,hash(p)])),
  runtimeSha256:createHash('sha256').update(readFileSync(new URL('../wasm/avr.wasm',import.meta.url))).digest('hex'),
  method:'Median of five warmed alternating runs rendering one emulated second at 48 kHz. Execution excludes construction/generation/compilation, reported separately. Interpreter uses production C/WASM CPU/DSP; translated variants use generated WASM CPU and shared C/WASM peripherals with JS DSP. All variants have equal cycles, full memory, IRQ counters and raw PCM, with filtered checksums within 2e-6. Flag-elimination ratio compares otherwise identical translated pipelines. No idle-loop skipping in translated variants. Node measurements are not a browser speed guarantee.',results};
writeFileSync(new URL('../reports/transpiler-benchmark.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.table(results.map(r=>({firmware:r.id,C_WASM_ms:r.interpreterMs.toFixed(2),translated_ms:r.translatedMs.toFixed(2),flags_gain:r.flagEliminationSpeedup.toFixed(2)+'x',vs_interpreter:r.translationSpeedup.toFixed(2)+'x',realtime:r.realtimeHeadroom.toFixed(1)+'x',compile_ms:r.constructionMs.toFixed(1),bytes:r.moduleBytes})));
