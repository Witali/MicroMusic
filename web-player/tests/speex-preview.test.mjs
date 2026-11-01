import {test} from 'node:test';
import assert from 'node:assert/strict';
import {speexPreviewEntries} from '../lib/speex-preview.js';
import {previewWaveform as compatibilityWaveform} from '../lib/native-preview.js';
import {previewWaveform} from '../lib/native-audio.js';
import {speexManifest} from './helpers/speex-manifest.mjs';

const base='https://example.test/MicroMusic/web-player/app.js';

test('Speex adapter binds complete mode1/mode3 packets and aligned native playback without Tiny88 firmware metadata',()=>{
  const entries=speexPreviewEntries(speexManifest,base);
  assert.deepEqual(entries.map(entry=>entry.id),['speex-bread-compact','speex-bread-quality']);
  for(const [index,entry] of entries.entries()){
    const variant=speexManifest.variants[index];
    assert.equal(entry.codec,'speex-nb');assert.equal(entry.codecLabel,'Speex NB');
    assert.equal(entry.decoderTarget,'atmega328p');assert.equal(entry.device,'attiny88');
    assert.equal(entry.streamExtension,'.spxraw');assert.equal(entry.phraseSamples,19200);assert.equal(entry.sampleHz,8000);
    assert.equal(entry.streamBytes,variant.packetBytes*variant.packets);assert.equal(entry.bitrateBps,entry.streamBytes*8/2.4);
    assert.equal(entry.decodedSamples-entry.trimStartSamples-entry.trimEndSamples,19200);
    assert.equal(entry.nominalBitrateBps,variant.nominalBitrateBps);assert.equal(entry.playOnce,true);
    assert.equal(entry.originalAudioUrl,'https://example.test/MicroMusic/web-player/audio/lpx-bread/original.wav');
    assert.equal(entry.streamUrl,'https://example.test/MicroMusic/web-player/'+variant.stream);
    assert.match(entry.nativeNotice,/ATmega328P; прошивки для ATtiny88 нет/);
    assert.equal(entry.research,'../Codecs/Speex/AVR/README.md');
    for(const key of ['flashHex','flashBytes','flashMeasurement','cpuHz','eepromHex'])assert.equal(entry[key],undefined);
  }
  const shuffled=structuredClone(speexManifest);shuffled.variants.reverse();assert.deepEqual(speexPreviewEntries(shuffled,base),entries);
  assert.equal(compatibilityWaveform,previewWaveform,'the existing public waveform import stays compatible');
});

test('Speex validates framing, nominal/actual bitrate, complete alignment, original reference and decoder target independently',()=>{
  for(const change of [
    d=>{d.codec='LPX';},d=>{d.decoderTarget='attiny88';},d=>{d.sampleRate=16000;},d=>{d.variants[0].mode=3;},
    d=>{d.variants[1].packetBytes=6;},d=>{d.variants[0].nominalBitrateBps=2400;},d=>{d.variants[0].bytes++;},
    d=>{d.variants[0].bitrateBps++;},d=>{d.variants[0].packets=0;},d=>{d.variants[0].decodedSamples++;},
    d=>{d.variants[0].trimStartSamples=-1;},d=>{d.variants[0].trimEndSamples++;},d=>{d.variants[0].codec='lpx-v5';},
    d=>{d.variants[0].id='other';},d=>{d.variants[1].id='compact';},d=>{d.variants.pop();},
    d=>{d.reference.audio='audio/lpx-bread/quality.wav';},d=>{d.variants[0].stream='https://invalid.example/raw.spxraw';},
    d=>{d.variants[0].audio='audio/lpx-bread/compact.wav';},d=>{d.variants[0].stream='audio/speex-bread/compact.lpx';},
    d=>{d.variants[0].flashMeasurement={programFlashBytes:4743};}
  ]){
    const data=structuredClone(speexManifest);change(data);assert.throws(()=>speexPreviewEntries(data,base));
  }
});
