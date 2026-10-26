// Retained native baseline versus current default mode; no timing benchmark.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a.js';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-file':{type:'string',default:'build/comparator-physical-verification.json'},
  'full-tap':{type:'string',default:'build/comparator-physical-full-suite.log'},
  'additional-tap':{type:'string',default:'build/comparator-physical-additional-suite.log'}}});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const baselineCommit=execFileSync('git',['rev-parse','--verify','23ef393d^{commit}'],{cwd:root,encoding:'utf8'}).trim();
const baseline=execFileSync('git',['show',baselineCommit+':web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:2*1024*1024});
assert.equal(hash(baseline),'bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715');
const current=readFileSync(resolve(root,'web-player/wasm/attiny13a.wasm'));
const modules=[baseline,current].map(bytes=>new WebAssembly.Module(bytes));
const catalog=JSON.parse(readFileSync(resolve(root,'web-player/firmware.json'))),audio=[];
for(const id of ['rhythmic','lumiere-stereo'])for(const optimized of [false,true]){
  const entry=catalog.entries.find(row=>row.id===id);assert.ok(entry,id);
  const options={...nominalVerificationDeviceOptions(entry.cpuHz),cacheTranslation:false,
    ...(optimized?{fastBlocks:true,optimizeFlags:true,maxBlockInstructions:32,boundedRegions:true,optimizePhaseLocals:true}:{})};
  const cores=modules.map(runtimeModule=>new ATtiny13A(parseHex(entry.flashHex),null,{...options,runtimeModule}));
  for(const core of cores)core.observePins(63,{retainDuringAudio:true});
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  for(let chunk=0;chunk<16;chunk++){
    const samples=cores.map(core=>core.capturePhysical(256,48000,entry.audioChannels||1));assert.deepEqual(...samples);
    pcm.update(new Uint8Array(samples[0].buffer,samples[0].byteOffset,samples[0].byteLength));
    const traces=cores.map(core=>core.drainPinsPs());assert.deepEqual(...traces);pinCount+=traces[0].length;
    pins.update(JSON.stringify(traces[0],(_key,value)=>typeof value==='bigint'?value+'n':value));
    for(const field of ['data','eeprom','rom'])assert.deepEqual(cores[0][field],cores[1][field]);
    assert.deepEqual(Array.from(cores[0]._state),Array.from(cores[1]._state));
    assert.deepEqual(cores[0].state(),cores[1].state());
    for(const core of cores)assert.equal(core.state().deviceFault,0);
  }
  const state=cores[1].state();assert.ok(state.irqs>0&&pinCount>0);
  audio.push({firmware:id,policy:optimized?'bounded-phase-locals':'verification',frames:4096,
    sampleRate:48000,pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex'),pinCount,
    irqs:state.irqs,retired:state.cpuPhase.retired.toString(),timePs:state.timePs.toString()});
}
function suite(path){
  const tap=readFileSync(resolve(root,path));
  const result=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo','duration_ms'].map(name=>{
    const match=tap.toString().match(new RegExp('^# '+name+' ([0-9.]+)$','m'));assert.ok(match,'Incomplete TAP: '+name);return [name,Number(match[1])];
  }));
  assert.ok(result.tests>0&&result.tests===result.pass);assert.equal(result.fail+result.cancelled+result.skipped+result.todo,0);
  return {...result,tapSha256:hash(tap)};
}
const fullSuite=suite(values['full-tap']),additionalSuite=suite(values['additional-tap']);
const report={schema:'micromusic-comparator-physical-verification-v1',baseline:{commit:baselineCommit,bytes:baseline.length,sha256:hash(baseline)},
  current:{bytes:current.length,sha256:hash(current),imports:WebAssembly.Module.imports(modules[1]),
    exports:WebAssembly.Module.exports(modules[1]).length},
  sources:Object.fromEntries(['web-player/scripts/verify-comparator-timing.mjs',
    'web-player/tests/analog-comparator-physical.test.mjs','web-player/tests/attiny13a-comparator-timing-runtime.test.mjs',
    'web-player/tests/device-comparator-profile.test.mjs',
    'web-player/tests/attiny13a-comparator-irq-sleep.test.mjs',
    'web-player/tests/attiny13a-comparator-profile.test.mjs','web-player/tests/attiny13a-comparator-package.test.mjs'].map(path=>
    [path,hash(readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n'))])),
  fullSuite,additionalSuite,audio,
  meaning:'Current null-profile output/state parity against retained native baseline, with active IRQs. New physical-delay tests use explicit synthetic delays; no silicon calibration, official-simulator execution, speed or real-time support claim.'};
const output=resolve(root,values['out-file']);mkdirSync(dirname(output),{recursive:true});writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({fullSuite,cases:audio.length,allPcmPinsAndStatesMatch:true,currentSha256:report.current.sha256}));
