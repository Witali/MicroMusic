import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {parseHex} from '../lib/hex.js';
const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
function wavData(wav){
  assert.equal(wav.toString('ascii',0,4),'RIFF');assert.equal(wav.toString('ascii',8,12),'WAVE');
  let format,pcm;
  for(let offset=12;offset+8<=wav.length;){
    const id=wav.toString('ascii',offset,offset+4),size=wav.readUInt32LE(offset+4),start=offset+8;
    assert.ok(start+size<=wav.length);
    if(id==='fmt ')format={encoding:wav.readUInt16LE(start),channels:wav.readUInt16LE(start+2),
      sampleRate:wav.readUInt32LE(start+4),bits:wav.readUInt16LE(start+14)};
    if(id==='data')pcm=wav.subarray(start,start+size);
    offset=start+size+(size&1);
  }
  assert.ok(format);assert.ok(pcm);
  return {format,pcm};
}
const catalog=JSON.parse(read('web-player/hq4-firmware.json'));
const archive=JSON.parse(read('ATtiny13A/Sound/research/hq4-catalog-archive.json'));
const references=JSON.parse(read('ATtiny13A/Sound/audio-references.json')).clips;
const frozen=JSON.parse(read('ATtiny13A/Sound/research/FROZEN_VERIFICATION.json')).variants;
const timbre=Object.fromEntries(['chego','chego-auto','chego-spectrum'].map(name=>
  [name,JSON.parse(read(`ATtiny13A/Sound/codec/timbre/${name}/verification.json`))]));

test('public speech catalog contains one selected image per phrase without private build dependencies',()=>{
  assert.equal(catalog.entries.length,3);assert.equal(catalog.defaultId,'hq4-chego-tiny');
  assert.deepEqual(catalog.entries.map(e=>e.id),['hq4-chego-tiny','hq4-otvechaesh-tiny','hq4-vinni']);
  assert.deepEqual(catalog.entries.map(e=>e.audioReferenceId),['chego','otvechaesh','vinni']);
  for(const e of catalog.entries){
    assert.equal(e.source,undefined);assert.equal(e.preview,undefined);
    assert.equal(e.reference,undefined);assert.equal(e.originalPlayer,undefined);
    assert.equal(e.sampleHz,7500);assert.equal(e.pwmHz,7500);assert.equal(e.carrierHz,37500);
    assert.equal(e.playOnce,true);
    assert.equal(e.phraseSamples,references.find(clip=>clip.id===e.audioReferenceId).samples);
  }
  assert.ok(catalog.entries.slice(0,2).every(e=>e.codec==='tiny-period'&&e.eepromBytes===64));
  assert.equal(catalog.entries[2].eepromBytes,0);
});

test('legacy variants remain in the research archive and old links preserve the selected phrase',()=>{
  assert.equal(archive.entries.length,7);assert.equal(archive.defaultId,'hq4-chego-auto');
  assert.equal(new Set(archive.entries.map(e=>e.id)).size,7);
  for(const entry of archive.entries){
    const selected=catalog.entries.find(e=>e.audioReferenceId===entry.audioReferenceId);
    assert.ok(selected);
    assert.equal(catalog.aliases[entry.id]??entry.id,selected.id);
  }
  for(const target of Object.values(catalog.aliases))assert.ok(catalog.entries.some(e=>e.id===target));
});

test('home page offers exactly the three selected speech phrases',()=>{
  const html=read('index.html').toString();
  const speech=html.match(/<article class="player player-speech">([\s\S]*?)<\/article>/)[1];
  const linkedIds=[...speech.matchAll(/firmware=([^"&]+)/g)].map(match=>match[1]);
  assert.deepEqual(linkedIds,catalog.entries.map(entry=>entry.id));
});
test('speech variants share the exact public canonical WAV for their phrase',()=>{
  const urls=new Set();
  for(const entry of [...catalog.entries,...archive.entries]){
    assert.equal(entry.kind,'speech');
    const reference=references.find(clip=>clip.id===entry.audioReferenceId);
    assert.ok(reference,entry.id+' has a canonical phrase');
    assert.equal(entry.originalAudioUrl,`./audio/originals/${reference.id}.wav`);
    assert.equal(entry.originalAudioSha256,reference.sha256);
    const wav=read('web-player/'+entry.originalAudioUrl);
    assert.equal(wav.length,reference.bytes);assert.equal(hash(wav),reference.sha256);
    const {format,pcm}=wavData(wav);
    assert.deepEqual(format,{encoding:1,channels:reference.channels,sampleRate:reference.sample_rate,bits:reference.bits_per_sample});
    assert.equal(pcm.length/(format.channels*format.bits/8),reference.samples);
    urls.add(entry.originalAudioUrl);
  }
  assert.equal(urls.size,3,'only one public WAV per phrase');
  const music=JSON.parse(read('web-player/firmware.json'));
  assert.ok(music.entries.every(entry=>entry.originalAudioUrl===undefined));
});

test('original playback uses standard-rate PCM with the canonical timing, samples and source hashes',()=>{
  const manifest=JSON.parse(read('web-player/audio/originals/playback/manifest.json'));
  assert.deepEqual(manifest.clips.map(clip=>clip.id),references.map(clip=>clip.id));
  const urls=new Set();
  for(const entry of [...catalog.entries,...archive.entries]){
    const reference=references.find(clip=>clip.id===entry.audioReferenceId);
    const copy=manifest.clips.find(clip=>clip.id===reference.id);
    assert.equal(copy.sourceSha256,reference.sha256);
    assert.equal(entry.originalPlaybackUrl,`./audio/originals/playback/${reference.id}.wav`);
    assert.equal(entry.originalPlaybackUrl,copy.url);
    const bytes=read('web-player/'+copy.url),{format,pcm}=wavData(bytes);
    assert.equal(hash(bytes),entry.originalPlaybackSha256);assert.equal(hash(bytes),copy.sha256);
    assert.equal(bytes.length,copy.bytes);assert.equal(pcm.length/2,copy.samples);
    assert.deepEqual(format,{encoding:1,channels:1,sampleRate:44100,bits:16});
    assert.equal(copy.sampleRate,format.sampleRate);
    assert.ok(Math.abs(copy.samples/copy.sampleRate-reference.samples/reference.sample_rate)<=1/copy.sampleRate);
    // The 7500 -> 44100 ratio is 25:147. At coincident sample times,
    // verify the original waveform, level and pitch rather than just a new header.
    const source=wavData(read('web-player/'+entry.originalAudioUrl)).pcm;
    let signal=0;
    for(let i=25;i<reference.samples-25;i+=25){
      const value=source.readInt16LE(i*2);signal+=value*value;
      assert.ok(Math.abs(pcm.readInt16LE(i/25*147*2)-value)<=1,entry.id+' preserves source samples');
    }
    assert.ok(signal>0);urls.add(copy.url);
  }
  assert.equal(urls.size,3);
});
for(const entry of catalog.entries)test(`${entry.id}: selected Flash/EEPROM plays once and then holds two phrase lengths of silence`,()=>{
  const binary=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  const report=JSON.parse(readFileSync(new URL(entry.verification,new URL('web-player/',root))));
  assert.equal(report.status,'verified');assert.equal(report.verifiedLoops,1);
  assert.equal(report.verification.pass,true);assert.equal(report.verification.mismatches,0);
  const samples=report.verification.verifiedSamples,expectedHash=report.verification.actualPcmSha256,imageHash=report.imageSha256;
  assert.equal(samples,entry.phraseSamples*3);assert.equal(report.phraseSamples,entry.phraseSamples);
  assert.equal(binary.length,report.flashBytes);
  if(eeprom){
    assert.equal(eeprom.length,64);
    assert.equal(hash(eeprom),report.eepromSha256);assert.equal(entry.eepromSha256,report.eepromSha256);
  }else assert.equal(entry.eepromBytes,0);
  assert.equal(hash(binary),imageHash);assert.equal(entry.flashSha256,imageHash);
  assert.equal(binary.length,entry.flashBytes);assert.ok(binary.length<=1024);
  for(const [path,sha] of Object.entries(entry.sourceInputs))assert.equal(hash(read(path)),sha,path);
  for(const Core of [Wasm,JS]){
    const core=new Core(binary,eeprom),pcm=Buffer.alloc(samples);
    for(let i=0;i<pcm.length;i++)pcm[i]=core.nextDuty();
    assert.equal(hash(pcm),expectedHash);assert.equal(core.lost,0);assert.equal(core.workLost,0);
    assert.equal(core.irqCount,samples*5);
    assert.ok(pcm.subarray(0,entry.phraseSamples).some(value=>value!==128),'speech is present before EOS');
    assert.ok(pcm.subarray(entry.phraseSamples).every(value=>value===128),'neutral PWM persists after EOS');
  }
});

for(const entry of archive.entries)test(`${entry.id}: archived HEX, retained sources and both engines match the frozen PCM`,()=>{
  const name=entry.id.slice(4),v=timbre[entry.variant],expected=entry.codec==='hq4-t'
    ? {image_sha256:v.imageSha256,sha256:v.pcmSha256,samples:v.samples}
    : frozen[name],binary=parseHex(entry.flashHex);
  assert.equal(hash(binary),expected.image_sha256);assert.equal(hash(binary),entry.flashSha256);
  assert.equal(binary.length,entry.flashBytes);assert.ok(binary.length<=1024);
  for(const [path,sha] of Object.entries(entry.sourceInputs))assert.equal(hash(read(path)),sha,path);
  for(const Core of [Wasm,JS]){
    const c=new Core(binary),pcm=Buffer.alloc(expected.samples);
    for(let i=0;i<pcm.length;i++)pcm[i]=c.nextDuty();
    assert.equal(hash(pcm),expected.sha256);assert.equal(c.lost,0);assert.equal(c.irqCount,pcm.length*5);
  }
});

test('public and archived speech catalogs preserve the firmware output level',()=>{
  for(const entry of [...catalog.entries,...archive.entries])assert.equal(entry.monitorGain,undefined,entry.id);
});
