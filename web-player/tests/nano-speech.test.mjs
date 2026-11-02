import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {lpxFirmwareEntries} from '../lib/native-preview.js';
import {playerApp} from './helpers/player-app.mjs';

const catalog=JSON.parse(readFileSync(new URL('../firmware-atmega328p.json',import.meta.url)));
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const choose=async(app,device)=>{app.get('device-select').value=device;await app.get('device-select').onchange();await flush();};
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');

test('Nano releases contain the exact public LPX streams and match sanitized timing receipts',()=>{
  assert.equal(catalog.cpuHz,16000000);assert.equal(catalog.sampleHz,8000);
  assert.equal(catalog.physicalBoardMeasured,false);
  for(const variant of catalog.variants){
    const hex=readFileSync(new URL('../'+variant.source,import.meta.url));
    const bytes=Buffer.from(parseHex(hex.toString(),30720));
    assert.equal(hash(hex),variant.hexSha256);
    assert.equal(bytes.length,variant.flashBytes);
    const clip=catalog.clips.find(item=>item.clipId===variant.clipId);
    const preview=clip.variants.find(item=>item.id===variant.id);
    const stream=readFileSync(new URL('../'+preview.stream,import.meta.url));
    assert.equal(hash(stream),variant.streamSha256);
    const start=bytes.indexOf(stream);assert.ok(start>=0);assert.equal(bytes.indexOf(stream,start+1),-1);
    assert.equal(variant.programFlashBytes+stream.length,variant.flashBytes);
    assert.ok(variant.staticSramBytes<2048);assert.ok(variant.timing.stackMarginBytes>0);
    assert.equal(variant.timing.playedSamples,clip.samples);assert.equal(variant.timing.underruns,0);
    assert.equal(variant.timing.irqEntryCycles,4);assert.equal(variant.timing.irqRetiComplete,true);
    assert.ok(variant.timing.minTickCycles>=1995);assert.ok(variant.timing.maxTickCycles<=2005);
  }
  assert.equal(catalog.sourceHashEncoding,'text-lf');
  for(const [path,expected] of Object.entries(catalog.sourceSha256))
    assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),expected,path);
});

test('Nano deep links reuse the shared page at root and GitHub Pages paths',async()=>{
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'atmega328p'});await flush();
    assert.equal(app.get('device-select').value,'atmega328p');
    assert.equal(app.get('machine-memory').textContent,'32');
    assert.equal(app.get('chip-nano').hidden,false);assert.equal(app.get('chip-attiny13a').hidden,true);
    assert.equal(app.get('board-control').hidden,true);
    assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-nano-chego-compact','lpx-nano-otvechaesh-compact','lpx-nano-vinni-compact','lpx-nano-bread-compact']);
    assert.equal(app.workers.length,0);assert.equal(app.get('download').getAttribute('aria-disabled'),null);
    assert.ok(app.get('download').href.endsWith('/web-player/firmware/arduino-nano/lpx-nano-chego-compact.hex'));
    assert.match(app.get('tiny88-power').textContent,/D3 \/ PD3 \/ OC2B/);
    assert.match(app.get('rom-details').textContent,/756 Б SRAM/);
    assert.match(app.get('preview-playback-note').textContent,/В браузере воспроизводится WAV/);
    assert.equal(app.get('flash-measurement-note').hidden,true);
    assert.equal(app.location.searchParams.get('device'),'atmega328p');
  }
});

test('switching devices stops audio, replaces catalog and restores the right download policy',async()=>{
  const app=await playerApp({device:'atmega328p'});await flush();
  await app.get('play').onclick();assert.equal(app.preview.paused,false);
  await choose(app,'attiny88');assert.equal(app.preview.paused,true);
  assert.ok(cards(app).every(card=>card.dataset.firmware.startsWith('lpx-')));
  assert.equal(app.get('download').getAttribute('aria-disabled'),'true');
  await choose(app,'attiny13a');assert.ok(cards(app).slice(0,3).every(card=>card.dataset.firmware.startsWith('hq4-')));
  assert.equal(app.get('chip-nano').hidden,true);
  const worker=app.workers.at(-1);await choose(app,'atmega328p');assert.equal(worker.terminated,true);
  cards(app)[3].onclick();await flush();
  app.get('speech-profile-select').value='lpx-nano-bread-quality';app.get('speech-profile-select').onchange();await flush();
  assert.equal(app.location.searchParams.get('firmware'),'lpx-nano-bread-quality');
  assert.equal(app.get('download').download,'lpx-nano-bread-quality.hex');
  assert.equal(app.get('download-eeprom').getAttribute('aria-disabled'),'true');
});

test('choosing Nano from music routes to the same AVR page with speech selected',async()=>{
  const app=await playerApp({speech:false});await choose(app,'atmega328p');
  assert.equal(app.location.searchParams.get('collection'),'hq4');
  assert.equal(app.location.searchParams.get('device'),'atmega328p');
  assert.equal(app.location.searchParams.has('firmware'),false);
});

test('a failed Nano catalog leaves other speech devices usable',async()=>{
  const app=await playerApp({fetchHook:({url,response})=>/\/firmware-(speex-)?atmega328p\.json$/.test(url.pathname)?{ok:false,status:503}:response});
  assert.equal(app.get('error').hidden,true);assert.equal(cards(app).length,4);
  await choose(app,'atmega328p');assert.match(app.get('error').textContent,/недоступны/);
  assert.equal(app.get('device-select').value,'attiny13a');
  await choose(app,'attiny88');assert.ok(cards(app).length>=2);
});

test('the Nano catalog rejects images exceeding board memory and foreign download URLs',()=>{
  for(const change of [v=>v.flashBytes=32768,v=>v.staticSramBytes=2048,v=>v.source='https://example.net/player.hex',v=>v.timing.underruns=1]){
    const bad=structuredClone(catalog);change(bad.variants[0]);
    assert.throws(()=>lpxFirmwareEntries(bad,'https://example.test/MicroMusic/web-player/'));
  }
});
