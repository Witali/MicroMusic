import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {lpxPreviewEntries,previewWaveform} from '../lib/native-preview.js';

const manifest=JSON.parse(readFileSync(new URL('../audio/lpx-bread/manifest.json',import.meta.url)));
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
    for(const field of ['flashHex','flashBytes','flashSha256','eepromHex','cpuHz','sramBytes'])assert.equal(entry[field],undefined);
    assert.equal(entry.nativeAudioUrl,'https://example.test/MicroMusic/web-player/'+manifest.variants[index].audio);
  }
});

test('manifest rejects inconsistent costs, external paths and unsupported native geometry',()=>{
  for(const mutate of [d=>d.variants[0].bytes++,d=>d.variants[1].audio='https://invalid.example/audio.wav',
    d=>d.reference.audio='../outside.wav',d=>d.sampleRate=7500,d=>d.samples=0,d=>d.variants[1].profile=4]){
    const data=structuredClone(manifest);mutate(data);assert.throws(()=>lpxPreviewEntries(data,base));
  }
});

test('waveform uses every actual mono PCM16 sample from the same published native WAV',()=>{
  const entries=lpxPreviewEntries(manifest,base);
  for(const [index,entry] of entries.entries()){
    const wav=readFileSync(new URL('../'+manifest.variants[index].audio,import.meta.url));
    const waveform=previewWaveform(buffer(wav),entry);assert.equal(waveform.length,19200);
    for(let sample=0;sample<waveform.length;sample++)assert.equal(waveform[sample],wav.readInt16LE(44+sample*2)/32768);
    assert.ok(waveform.some(value=>value!==0));
  }
});

test('waveform refuses truncated or mismatched WAVs rather than displaying synthetic samples',()=>{
  const entry=lpxPreviewEntries(manifest,base)[0],wav=readFileSync(new URL('../'+manifest.variants[0].audio,import.meta.url));
  for(const mutate of [bytes=>bytes.subarray(0,bytes.length-2),bytes=>{bytes.writeUInt32LE(44100,24);return bytes;},
    bytes=>{bytes.writeUInt16LE(2,22);return bytes;},bytes=>{bytes.writeUInt32LE(2,40);return bytes;}]){
    assert.throws(()=>previewWaveform(buffer(mutate(Buffer.from(wav))),entry));
  }
});
