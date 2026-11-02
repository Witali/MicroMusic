import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {AVRCore as Wasm} from '../lib/avr-core.js';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const json=path=>JSON.parse(read(path));
const hash=data=>createHash('sha256').update(data).digest('hex');
const entry=json('web-player/firmware-attiny13a-speech-extra.json').entries.find(item=>item.id==='hq4-bread-tiny');
const waveform=json('web-player/audio/speech-waveforms/manifest.json').entries.find(item=>item.id===entry.id);
const selection=json('ATtiny13A/Sound/research/shared-speech/bread-selection.json');
const image=parseHex(entry.flashHex,1024),eeprom=parseHex(entry.eepromHex,64);

test('public Tiny bread image matches the selected model, build receipt and waveform identity',()=>{
  assert.equal(image.length,1014);assert.equal(eeprom.length,64);
  assert.equal(hash(image),entry.flashSha256);assert.equal(hash(eeprom),entry.eepromSha256);
  assert.equal(selection.selected.flashBytes,image.length);
  assert.equal(selection.selected.eepromBytes,eeprom.length);
  assert.equal(selection.selected.modelSha256,hash(read('ATtiny13A/Sound/research/shared-speech/bread-model.json')));
  assert.equal(selection.selectedVerification.pass,true);
  assert.equal(selection.selectedVerification.imageSha256,entry.flashSha256);
  assert.equal(selection.selectedVerification.eepromSha256,entry.eepromSha256);
  assert.equal(waveform.flashSha256,entry.flashSha256);
  assert.equal(waveform.eepromSha256,entry.eepromSha256);
  assert.equal(entry.phraseSamples,18048);assert.equal(entry.sampleHz,7500);
  assert.equal(entry.phraseSamples/entry.sampleHz,2.4064);
});

for(const [name,make] of [
  ['reference JS',()=>new Reference(image,eeprom)],
  ['optimized WASM',()=>new Wasm(image,eeprom)],
  ['unoptimized WASM',()=>new Wasm(image,eeprom,{fastIdle:false,fastBlocks:false})],
])test(`public Tiny bread replays exact speech then centered silence in ${name}`,()=>{
  const cpu=make(),total=entry.phraseSamples*3,actual=Buffer.alloc(total);
  let minimumPeriod=Infinity,maximumPeriod=0,previous=0;
  for(let i=0;i<total;i++){
    const writes=cpu.writes;actual[i]=cpu.nextDuty();
    assert.equal(cpu.writes,writes+1,`${name}: sample ${i} produced one PWM write`);
    if(i){const period=cpu.cyc-previous;minimumPeriod=Math.min(minimumPeriod,period);maximumPeriod=Math.max(maximumPeriod,period);}
    previous=cpu.cyc;
  }
  assert.equal(hash(actual.subarray(0,entry.phraseSamples)),waveform.pwmSha256);
  assert.ok(actual.subarray(entry.phraseSamples).every(value=>value===128),'one shot remains silent after the whole phrase');
  assert.equal(hash(actual),selection.selectedVerification.actualPcmSha256);
  assert.equal(cpu.lost,0);assert.equal(cpu.workLost,0);
  assert.equal(cpu.irqCount,total*5);
  assert.ok(minimumPeriod>=1279);assert.ok(maximumPeriod<=1281);
  assert.deepEqual(Buffer.from(cpu.eeprom),Buffer.from(eeprom),'playback never writes EEPROM');
});
