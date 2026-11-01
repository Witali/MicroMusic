import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {lpxPreviewEntries,previewWaveform} from '../lib/native-preview.js';
import {legacyManifest as manifest,publishedManifest,threeVariantManifest} from './helpers/lpx-manifests.mjs';

const base='https://example.test/MicroMusic/web-player/app.js';
const buffer=bytes=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);

test('manifest produces only source-bound preview entries, with exact costs and no fabricated firmware',()=>{
  const entries=lpxPreviewEntries(manifest,base);
  assert.deepEqual(entries.map(entry=>entry.id),['lpx-bread-compact','lpx-bread-quality']);
  for(const [index,entry] of entries.entries()){
    assert.equal(entry.streamBytes,manifest.variants[index].bytes);assert.equal(entry.bitrateBps,manifest.variants[index].bitrateBps);
    assert.equal(entry.phraseSamples,19200);assert.equal(entry.sampleHz,8000);
    assert.equal(entry.device,'attiny88');assert.equal(entry.intendedBoard,'mh-et-live-16mhz');
    assert.equal(entry.playback,'native-pwm8');assert.equal(entry.playOnce,true);
    assert.equal(entry.flashMeasurement,undefined);
    for(const field of ['flashHex','flashBytes','flashSha256','eepromHex','cpuHz','sramBytes'])assert.equal(entry[field],undefined);
    assert.equal(entry.nativeAudioUrl,'https://example.test/MicroMusic/web-player/'+manifest.variants[index].audio);
  }
});

test('optional Flash measurement preserves exact target/test-image metadata and rejects invalid splits',()=>{
  const entries=lpxPreviewEntries(publishedManifest,base);
  for(const entry of entries){
    const variant=publishedManifest.variants.find(item=>entry.id==='lpx-bread-'+item.id);
    assert.deepEqual(entry.flashMeasurement,variant.flashMeasurement);
  }
  const compact=publishedManifest.variants.find(variant=>variant.id==='compact');
  for(const change of [
    m=>{m.programFlashBytes=0;},m=>{m.programFlashBytes=1.5;},m=>{m.totalFlashBytes++;},m=>{m.encodedBytes++;},
    m=>{m.totalFlashBytes=Number.MAX_SAFE_INTEGER+1;},m=>{m.target='atmega328p';},m=>{m.memoryProfile='generic';},
    m=>{m.flashMeasurementKind='realtime-firmware';},m=>{delete m.programFlashBytes;}
  ]){
    const data=structuredClone(publishedManifest),variant=data.variants.find(item=>item.id==='compact');
    variant.flashMeasurement=structuredClone(compact.flashMeasurement);change(variant.flashMeasurement);
    assert.throws(()=>lpxPreviewEntries(data,base),/Flash/);
  }
  const data=structuredClone(publishedManifest);data.variants.find(item=>item.id==='compact').flashMeasurement=null;
  assert.throws(()=>lpxPreviewEntries(data,base),/Flash/);
});

test('manifest rejects inconsistent costs, external paths and unsupported native geometry',()=>{
  for(const mutate of [d=>d.variants[0].bytes++,d=>d.variants[1].audio='https://invalid.example/audio.wav',
    d=>d.reference.audio='../outside.wav',d=>d.sampleRate=7500,d=>d.samples=0,d=>d.variants[1].profile=4]){
    const data=structuredClone(manifest);mutate(data);assert.throws(()=>lpxPreviewEntries(data,base));
  }
});

test('optional S15 is first, explicitly version8, and preserves both existing v5 identities',()=>{
  const entries=lpxPreviewEntries(threeVariantManifest,base),legacy=lpxPreviewEntries(manifest,base);
  assert.deepEqual(entries.map(entry=>entry.id),['lpx-bread-low15','lpx-bread-compact','lpx-bread-quality']);
  assert.deepEqual(entries.map(entry=>entry.order),['01','02','03']);
  assert.equal(entries[0].codec,'lpx-s15');assert.equal(entries[0].formatVersion,8);assert.equal(entries[0].profile,15);
  assert.equal(entries[0].title,'LPX-S15 · Очень низкий битрейт');
  assert.equal(entries[0].formatNotice,'LPX-S15 · экспериментальный формат; нужен отдельный декодер.');
  for(let index=0;index<2;++index){
    const {order,...before}=legacy[index],{order:afterOrder,...after}=entries[index+1];assert.deepEqual(after,before);
    assert.equal(after.codec,'lpx-v5');assert.equal(after.formatVersion,5);
  }
  const shuffled=structuredClone(threeVariantManifest);shuffled.variants.reverse();
  assert.deepEqual(lpxPreviewEntries(shuffled,base),entries);
});

test('S15 and v5 reject unknown, duplicate, missing, or incompatible format declarations',()=>{
  for(const mutate of [
    d=>{d.variants[2].id='other';},d=>{d.variants[2].id='compact';},d=>{d.variants[2].profile=6;},
    d=>{d.variants[2].codec='lpx-v5';},d=>{delete d.variants[2].codec;},d=>{d.variants[2].formatVersion=5;},
    d=>{delete d.variants[2].formatVersion;},d=>{d.variants[0].codec='lpx-s15';},d=>{d.variants[1].formatVersion=8;},
    d=>{d.variants[0].codec=null;},d=>{d.variants[1].formatVersion=null;},
    d=>{d.variants[2].bytes++;},d=>{d.variants[2].bitrateBps=NaN;},d=>{d.codec='unknown';},
    d=>{d.variants.splice(0,1);},d=>{d.variants.push({...d.variants[2]});}
  ]){
    const data=structuredClone(threeVariantManifest);mutate(data);assert.throws(()=>lpxPreviewEntries(data,base));
  }
});

test('waveform uses every actual mono PCM16 sample from the same published native WAV',()=>{
  const entries=lpxPreviewEntries(publishedManifest,base);
  for(const entry of entries){
    const variant=publishedManifest.variants.find(item=>entry.id==='lpx-bread-'+item.id);
    const wav=readFileSync(new URL('../'+variant.audio,import.meta.url));
    const waveform=previewWaveform(buffer(wav),entry);assert.equal(waveform.length,19200);
    for(let sample=0;sample<waveform.length;sample++)assert.equal(waveform[sample],wav.readInt16LE(44+sample*2)/32768);
    assert.ok(waveform.some(value=>value!==0));
  }
});

test('published preview metadata matches complete stream bytes, format, profile and sample geometry',()=>{
  for(const entry of lpxPreviewEntries(publishedManifest,base)){
    const variant=publishedManifest.variants.find(item=>entry.id==='lpx-bread-'+item.id);
    const stream=readFileSync(new URL('../'+variant.stream,import.meta.url));
    assert.equal(stream.length,entry.streamBytes);assert.equal(stream.toString('ascii',0,4),'L4HY');
    assert.equal(stream[4],entry.formatVersion);assert.equal(stream[5]&127,entry.profile);
    assert.equal(stream.readUInt16LE(6),entry.sampleHz);assert.equal(stream.readUInt32LE(8),entry.phraseSamples);
    assert.equal(entry.bitrateBps,stream.length*8*entry.sampleHz/entry.phraseSamples);
  }
});

test('waveform refuses truncated or mismatched WAVs rather than displaying synthetic samples',()=>{
  const entry=lpxPreviewEntries(manifest,base)[0],wav=readFileSync(new URL('../'+manifest.variants[0].audio,import.meta.url));
  for(const mutate of [bytes=>bytes.subarray(0,bytes.length-2),bytes=>{bytes.writeUInt32LE(44100,24);return bytes;},
    bytes=>{bytes.writeUInt16LE(2,22);return bytes;},bytes=>{bytes.writeUInt32LE(2,40);return bytes;}]){
    assert.throws(()=>previewWaveform(buffer(mutate(Buffer.from(wav))),entry));
  }
});
