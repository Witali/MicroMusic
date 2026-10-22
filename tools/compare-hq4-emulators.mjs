// Differential HQ4 audit. Inputs can be rebuilt by verify-frozen-speech.py;
// no source audio or ZIP is required for this comparison.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import assert from 'node:assert/strict';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';
import {AVRCore as JS} from '../web-player/lib/avr-reference.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const {values}=parseArgs({options:{data:{type:'string'},report:{type:'string'}}});
const data=resolve(values.data||resolve(root,'build/frozen-speech'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const read=path=>readFileSync(resolve(root,path));
const frozen=JSON.parse(read('ATtiny13A/Sound/research/FROZEN_VERIFICATION.json')).variants;
const archivedPaths=[
  'ATtiny13A/Sound/codec/release/avr_emulator.js',
  'ATtiny13A/Sound/codec/MicroMusic_MulQ4_Opt_release/avr_emulator.js',
  'ATtiny13A/Sound/fast-encoder/avr_emulator.js',
  'ATtiny13A/Sound/research/alternatives/hq4-alternative-fit/avr_emulator.js',
];
const {AVRCore:Archived}=createRequire(import.meta.url)(resolve(root,archivedPaths[0]));
const report={schema:'micromusic-hq4-emulator-comparison-v1',hardwareTested:false,
  archivedCores:Object.fromEntries(archivedPaths.map(path=>[path,hash(read(path))])),
  inputs:Object.fromEntries(['web-player/lib/avr-reference.js','web-player/native/avr.c',
    'web-player/wasm/avr.wasm', 'tools/compare-hq4-emulators.mjs'].map(path=>[path,
      hash(path.endsWith('.wasm')?read(path):read(path).toString('utf8').replaceAll('\r\n','\n'))])),
  variants:{},pass:false};
const fields=['pc','cyc','irqCount','lost','maxIRQ','writes','minSP','overflowAt','inIRQ'];
// A matching speech stream does not make the historical interpreter a hardware oracle.
// These independent edge cases follow DS40002198A §§5.1, 5.66 and 5.80.
const registerWord=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
report.archivedSpecificationDifferences=[];
for(const [instruction,word,a,b,initial,mask,expected] of [
  ['ADC zero flag',registerWord(0x1c00,17,18),255,0,1,2,2],
  ['NEG half-carry',0x9511,1,0,0,32,32],
]) {
  const binary=Uint8Array.of(word&255,word>>8),old=new Archived(binary),current=new Wasm(binary);
  for(const c of [old,current]){c.r[17]=a;c.r[18]=b;c.sreg=initial;c.step();}
  assert.equal(current.sreg&mask,expected);
  report.archivedSpecificationDifferences.push({instruction,mask,expected,
    archived:old.sreg&mask,repository:current.sreg&mask});
}
{
  const binary=Uint8Array.of(0x0e,0x91); // LD r16,-X (supported by the archived HQ4 core)
  const old=new Archived(binary),current=new Wasm(binary);
  old.r[26]=current.r[26]=97;old.r[27]=current.r[27]=1;
  old.sram[0]=current.sram[0]=0xa5;
  let error=null;try{old.step();}catch(e){error=e.message;}
  current.step();assert.equal(current.r[16],0xa5);assert.equal(current.r[27],1);
  report.archivedSpecificationDifferences.push({instruction:'LD -X with unused XH=1',
    expected:165,archivedError:error,repository:current.r[16]});
}
for(const [name,expected] of Object.entries(frozen)) {
  const binary=readFileSync(resolve(data,name,'firmware.bin'));
  assert.equal(hash(binary),expected.image_sha256,name+' image');
  const old=new Archived(binary),js=new JS(binary),wasm=new Wasm(binary);
  const slow=new Wasm(binary,null,{fastIdle:false,fastBlocks:false});
  const output={archived:Buffer.alloc(expected.samples),js:Buffer.alloc(expected.samples),wasm:Buffer.alloc(expected.samples)};
  let minDelta=Infinity,maxDelta=-Infinity,minPeriod=Infinity,maxPeriod=-Infinity,lastCycle=0;
  for(let i=0;i<expected.samples;i++) {
    output.archived[i]=old.takeSample();output.js[i]=js.nextDuty();output.wasm[i]=wasm.nextDuty();
    assert.equal(slow.nextDuty(),output.wasm[i],name+' slow PCM '+i);
    assert.deepEqual(wasm.data,js.data,name+' memory '+i);
    assert.deepEqual(wasm.data,slow.data,name+' slow memory '+i);
    for(const field of fields) {
      assert.equal(wasm[field],js[field],name+' JS '+field+' '+i);
      assert.equal(wasm[field],slow[field],name+' slow '+field+' '+i);
    }
    const delta=wasm.cyc-old.cycles;minDelta=Math.min(minDelta,delta);maxDelta=Math.max(maxDelta,delta);
    if(i){const period=wasm.cyc-lastCycle;minPeriod=Math.min(minPeriod,period);maxPeriod=Math.max(maxPeriod,period);}
    lastCycle=wasm.cyc;
  }
  for(const [engine,pcm] of Object.entries(output))assert.equal(hash(pcm),expected.sha256,name+' '+engine+' PCM');
  assert.equal(wasm.lost,0);assert.equal(old.missedOverflows,0);
  assert.equal(wasm.irqCount,expected.samples*5);assert.equal(old.irqCount,wasm.irqCount);
  report.variants[name]={samples:expected.samples,flashBytes:binary.length,pcmSha256:expected.sha256,
    pcmMismatches:0,jsWasmSlowStateMismatches:0,timerLost:wasm.lost,
    irqs:wasm.irqCount,maxISRCycles:wasm.maxIRQ,minimumSamplePeriod:minPeriod,maximumSamplePeriod:maxPeriod,
    cycles:{repository:wasm.cyc,archived:old.cycles,minimumSampleDelta:minDelta,maximumSampleDelta:maxDelta}};
}
report.archivedCopiesIdentical=new Set(Object.values(report.archivedCores)).size===1;
report.totalSamples=Object.values(report.variants).reduce((sum,v)=>sum+v.samples,0);report.pass=true;
if(values.report){const path=resolve(values.report);mkdirSync(dirname(path),{recursive:true});writeFileSync(path,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report,null,2));
