import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {deferred,playerApp} from './helpers/player-app.mjs';
import {speexManifest} from './helpers/speex-manifest.mjs';
import {publishedManifest as lpxManifest} from './helpers/lpx-manifests.mjs';
import {speexPreviewEntries} from '../lib/speex-preview.js';
import {previewWaveform} from '../lib/native-audio.js';

const flush=()=>new Promise(setImmediate);
// This tests UI routing with existing PCM fixtures, not Speex decoding quality.
const fixture=({catalogs={},assets={},...options}={})=>playerApp({device:'attiny88',...options,
  catalogs:{'audio/speex-bread/manifest.json':speexManifest,...catalogs},
  assets:{'audio/speex-bread/compact.wav':readFileSync(new URL('../audio/lpx-bread/compact.wav',import.meta.url)),
    'audio/speex-bread/quality.wav':readFileSync(new URL('../audio/lpx-bread/quality.wav',import.meta.url)),...assets}});
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const select=(app,id)=>cards(app).find(card=>card.dataset.firmware===id).onclick();
const changeDevice=async(app,id)=>{app.get('device-select').value=id;await app.get('device-select').onchange();};
const disabledFirmware=app=>{
  for(const id of ['download','download-eeprom']){
    assert.equal(app.get(id).hidden,false);assert.equal(app.get(id).getAttribute('aria-disabled'),'true');
    assert.equal(app.get(id).getAttribute('href'),null);assert.equal(app.get(id).getAttribute('download'),null);
  }
  assert.equal(app.get('avr-inspector').hidden,true);assert.equal(app.get('board-upload').hidden,true);
};

test('actual Speex assets bind complete packets, aligned WAVs and all five public catalog choices',async()=>{
  const data=JSON.parse(readFileSync(new URL('../audio/speex-bread/manifest.json',import.meta.url)));
  assert.equal(data.title,lpxManifest.title);assert.equal(data.reference.audio,'audio/lpx-bread/original.wav');
  const entries=speexPreviewEntries(data,'https://example.test/MicroMusic/web-player/app.js');
  const app=await playerApp({device:'attiny88'});await flush();
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-bread-low15','lpx-bread-compact','lpx-bread-quality','speex-bread-compact','speex-bread-quality']);
  assert.equal(app.get('catalog-count').textContent,5);
  for(const [index,entry] of entries.entries()){
    const variant=data.variants.find(item=>entry.id==='speex-bread-'+item.id);
    const raw=readFileSync(new URL('../'+variant.stream,import.meta.url)),wav=readFileSync(new URL('../'+variant.audio,import.meta.url));
    assert.equal(raw.length,[726,2420][index]);assert.equal(raw.length,variant.packetBytes*variant.packets);
    assert.equal(variant.packets,121);assert.equal(variant.decodedSamples,19360);
    assert.equal(variant.trimStartSamples,80);assert.equal(variant.trimEndSamples,80);
    assert.equal(variant.bitrateBps,raw.length*8/2.4);assert.equal(wav.length,38444);
    const waveform=previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),entry);
    assert.equal(waveform.length,19200);
    for(let sample=0;sample<waveform.length;sample++)assert.equal(waveform[sample],wav.readInt16LE(44+sample*2)/32768);
    select(app,entry.id);await flush();
    assert.equal(app.preview.src,entry.nativeAudioUrl);assert.equal(app.get('rom-name').href,entry.streamUrl);
    assert.equal(app.get('rom-name').download,entry.id+'.spxraw');assert.equal(app.get('wave').dataset.samples,'19200');
    disabledFirmware(app);assert.match(app.get('rom-details').textContent,/не измерено/);
    await app.get('play').onclick();assert.equal(app.get('run-status').textContent,'Нативное превью Speex NB');
  }
  assert.equal(app.workers.length,0);
});

test('the same Tiny88 library keeps LPX first and appends Speex as fourth/fifth entries',async()=>{
  const app=await fixture();
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-bread-low15','lpx-bread-compact','lpx-bread-quality','speex-bread-compact','speex-bread-quality']);
  assert.deepEqual(cards(app).map(card=>card.children[0].textContent),['01','02','03','04','05']);
  assert.equal(app.get('catalog-count').textContent,5);assert.equal(app.location.searchParams.get('firmware'),'lpx-bread-low15');
  assert.equal(app.workers.length,0);
  await changeDevice(app,'attiny13a');assert.equal(cards(app).length,3);
  assert.ok(cards(app).every(card=>card.dataset.firmware.startsWith('hq4-')));
  assert.equal(app.workers.at(-1).messages[0].entry.flashHex,app.catalog.entries[0].flashHex);
});

test('Speex direct links use actual stored and nominal rates, raw names, docs and honest hardware notices',async()=>{
  for(const prefix of ['/','/MicroMusic/'])for(const variant of speexManifest.variants){
    const app=await fixture({prefix,device:undefined,firmware:'speex-bread-'+variant.id});await flush();
    assert.equal(app.get('device-select').value,'attiny88');assert.equal(app.location.searchParams.get('firmware'),'speex-bread-'+variant.id);
    assert.equal(app.location.searchParams.get('board'),'mh-et-live-16mhz');
    assert.equal(app.preview.src,'https://example.test'+prefix+'web-player/'+variant.audio);
    assert.equal(app.original.src,'https://example.test'+prefix+'web-player/audio/lpx-bread/original.wav');
    assert.equal(app.get('rom-name').href,'https://example.test'+prefix+'web-player/'+variant.stream);
    assert.equal(app.get('rom-name').download,'speex-bread-'+variant.id+'.spxraw');
    assert.equal(app.get('selected-title').textContent,'Speex NB · '+variant.label);
    const details=app.get('rom-details').textContent.replace(/\s/g,'');
    assert.ok(details.includes(variant.bytes+'БданныхSpeex'));
    assert.ok(details.includes(variant.bitrateBps.toLocaleString('ru').replace(/\s/g,'')+'бит/спофайлу'));
    assert.ok(details.includes(variant.nominalBitrateBps.toLocaleString('ru').replace(/\s/g,'')+'бит/сноминально'));
    assert.match(app.get('rom-details').textContent,/не измерено/);assert.equal(app.get('flash-measurement-note').hidden,true);
    assert.equal(app.get('preview-format-note').hidden,true);
    assert.match(app.get('preview-playback-note').textContent,/ATmega328P; прошивки для ATtiny88 нет/);
    assert.equal(app.get('tiny88-power').textContent,'Декодер: ATmega328P · Speex NB.');
    assert.equal(app.get('board-note').textContent,'Сравнение Speex NB · декодер ATmega328P.');
    assert.equal(app.get('chip-attiny88').getAttribute('aria-label'),app.get('board-note').textContent);
    assert.equal(app.get('speech-audit').textContent,'Исследование Speex ↗');assert.match(app.get('speech-audit').href,/Codecs\/Speex\/AVR\/README\.md$/);
    assert.equal(app.get('wave').dataset.samples,'19200');assert.match(app.get('wave').getAttribute('aria-label'),/Speex NB/);
    disabledFirmware(app);assert.equal(app.workers.length,0);
  }
});

test('Speex shares main play/pause, one-shot replay, original and volume without an AVR worker',async()=>{
  const app=await fixture({firmware:'speex-bread-compact'});await app.get('play').onclick();
  assert.equal(app.get('run-status').textContent,'Нативное превью Speex NB');app.preview.advance(.8);
  await app.get('play').onclick();assert.equal(app.preview.paused,true);assert.equal(app.preview.currentTime,.8);
  await app.get('play').onclick();app.preview.finish();assert.equal(app.get('elapsed').textContent,'00:02.4');
  assert.equal(app.get('play-label').textContent,'Ещё раз');await app.get('play').onclick();await flush();
  assert.equal(app.preview.currentTime,0);assert.equal(app.preview.paused,false);
  await app.get('play-original').onclick();assert.equal(app.preview.paused,true);assert.equal(app.original.paused,false);
  await app.get('play').onclick();assert.equal(app.original.paused,true);
  app.get('volume').value='.2';app.get('volume').oninput();assert.equal(app.preview.volume,.2);assert.equal(app.original.volume,.2);
  app.get('reset').onclick();assert.equal(app.preview.currentTime,0);assert.equal(app.preview.paused,true);
  assert.equal(app.workers.length,0);assert.equal(app.worklets.length,0);
});

test('codec switches restore LPX/S15 notices, measured sizes, status, docs and download extensions',async()=>{
  const app=await fixture({firmware:'lpx-bread-low15'});await app.get('play').onclick();
  assert.equal(app.get('preview-format-note').hidden,false);assert.equal(app.get('flash-measurement-note').hidden,false);
  select(app,'speex-bread-quality');assert.equal(app.preview.paused,true);
  assert.equal(app.get('preview-format-note').hidden,true);assert.equal(app.get('flash-measurement-note').hidden,true);
  assert.doesNotMatch(app.get('rom-details').textContent,/4743|5160|LPX/);
  await app.get('play').onclick();assert.equal(app.get('run-status').textContent,'Нативное превью Speex NB');
  select(app,'lpx-bread-quality');assert.equal(app.preview.paused,true);assert.equal(app.get('flash-measurement-note').hidden,false);
  assert.match(app.get('tiny88-power').textContent,/Целевой профиль: MH-ET LIVE/);assert.doesNotMatch(app.get('board-note').textContent,/Speex|ATmega/);
  assert.equal(app.get('speech-audit').textContent,'Исследование LPX ↗');assert.match(app.get('speech-audit').href,/Codecs\/LPX\/README\.md$/);
  assert.match(app.get('rom-name').download,/\.lpx$/);assert.match(app.get('rom-details').textContent,/6.310 Б Flash/);
  await app.get('play').onclick();assert.equal(app.get('run-status').textContent,'Нативное превью LPX');
  await changeDevice(app,'attiny13a');assert.equal(app.preview.paused,true);assert.equal(app.get('preview-note').hidden,true);
  assert.equal(app.get('engine-controls').hidden,false);assert.equal(app.get('download').getAttribute('aria-disabled'),null);
});

test('a canceled Speex play or waveform failure cannot overwrite a later LPX selection',async()=>{
  const wave=deferred();
  const app=await fixture({firmware:'speex-bread-compact',fetchHook:({url})=>url.pathname.endsWith('/speex-bread/compact.wav')?wave.promise:undefined});
  app.preview.pendingPlay=deferred();const pending=app.get('play').onclick(),old=app.preview.pendingPlay;
  select(app,'lpx-bread-quality');app.preview.pendingPlay=null;await app.get('play').onclick();
  old.reject(new Error('old Speex failure'));await pending;wave.resolve({ok:false,status:503});await flush();
  assert.equal(app.preview.paused,false);assert.equal(app.get('error').hidden,true);
  assert.equal(app.get('run-status').textContent,'Нативное превью LPX');
  assert.match(app.get('scope-left-label').textContent,/LPX/);assert.doesNotMatch(app.get('scope-left-label').textContent,/НЕДОСТУПНА/);
  assert.equal(app.get('speech-audit').textContent,'Исследование LPX ↗');
});

test('manifest failure is isolated by codec and leaves the other native entries and real HQ4 usable',async()=>{
  const invalid=structuredClone(speexManifest);invalid.variants[0].packetBytes=20;
  const app=await fixture({catalogs:{'audio/speex-bread/manifest.json':invalid}});
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-bread-low15','lpx-bread-compact','lpx-bread-quality']);
  assert.equal(app.get('error').hidden,true);await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  await changeDevice(app,'attiny13a');assert.equal(app.workers.at(-1).messages[0].entry.flashHex,app.catalog.entries[0].flashHex);
  const badLPX=structuredClone(lpxManifest);badLPX.codec='wrong';
  const speex=await fixture({firmware:'speex-bread-quality',catalogs:{'audio/lpx-bread/manifest.json':badLPX}});
  assert.deepEqual(cards(speex).map(card=>card.dataset.firmware),['speex-bread-compact','speex-bread-quality']);
  assert.equal(speex.get('error').hidden,true);await speex.get('play').onclick();assert.equal(speex.get('run-status').textContent,'Нативное превью Speex NB');
  const missing=await fixture({firmware:'speex-bread-quality',catalogs:{'audio/speex-bread/manifest.json':invalid}});
  assert.match(missing.get('error').textContent,/Speex.*недоступны/);assert.equal(missing.location.searchParams.get('firmware'),'lpx-bread-low15');
});
