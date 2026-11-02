import {test} from 'node:test';
import assert from 'node:assert/strict';
import {arduinoSpeechEntries} from '../lib/arduino-speech.js';
import {playerApp,deferred} from './helpers/player-app.mjs';
import {arduinoCatalog} from './helpers/atmega-speech-fixture.mjs';

const base='https://example.test/MicroMusic/web-player/app.js';
const flush=()=>new Promise(setImmediate);
const fixture=options=>playerApp({catalogs:{'firmware-atmega328p.json':arduinoCatalog()},...options});
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const choose=async(app,device)=>{app.get('device-select').value=device;await app.get('device-select').onchange();};
const select=(app,id)=>cards(app).find(card=>card.dataset.firmware===id).onclick();

test('Arduino catalog admits linked mono firmware with exact Flash/audio costs and source-bound assets',()=>{
  const source=arduinoCatalog(),catalog=arduinoSpeechEntries(source,base);
  assert.equal(catalog.defaultId,source.defaultId);assert.equal(catalog.entries.length,2);
  for(const entry of catalog.entries){
    assert.equal(entry.source,'https://example.test/MicroMusic/web-player/firmware/atmega328p/test.hex');
    assert.equal(entry.originalAudioUrl,'https://example.test/MicroMusic/web-player/audio/lpx-bread/original.wav');
    assert.equal(entry.programFlashBytes+entry.encodedBytes,entry.flashBytes);
    assert.equal(entry.playback,undefined);assert.ok(entry.playbackCycles>entry.phraseSamples*2000);
  }
  for(const mutate of [
    d=>d.entries[0].device='attiny88',d=>d.entries[0].board='mh-et-live-16mhz',d=>d.entries[0].cpuHz=8000000,
    d=>d.entries[0].executionEngine='wasm',d=>d.entries[0].supportedEngines.push('wasm'),
    d=>d.entries[0].pwmOutput='OC0B',d=>d.entries[0].outputPin='D9',d=>d.entries[0].audioChannels=2,
    d=>d.entries[0].eepromBytes=1,d=>d.entries[0].playback='native-pwm8',d=>d.entries[0].flashHex='not hex',
    d=>d.entries[0].encodedBytes++,d=>d.entries[0].flashBytes++,d=>d.entries[0].bitrateBps++,
    d=>d.entries[0].source='https://outside.test/test.hex',d=>d.entries[0].originalAudioUrl='../private.wav',
    d=>d.entries[0].playbackCycles=100,d=>d.entries[0].playbackCycles=NaN,d=>d.defaultId='missing',
    d=>d.entries.push({...d.entries[0]})
  ]){const data=structuredClone(source);mutate(data);assert.throws(()=>arduinoSpeechEntries(data,base));}
});

test('speech dropdown selects the Arduino catalog, real HEX worker, device facts, downloads and individual output pins',async()=>{
  const app=await fixture({device:'atmega328p'}),entry=arduinoCatalog().entries[0];
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),arduinoCatalog().entries.map(item=>item.id));
  assert.equal(app.body.dataset.device,'atmega328p');assert.equal(app.body.dataset.preview,'false');
  assert.equal(app.get('device-select').value,'atmega328p');assert.equal(app.get('device-arduino-option').hidden,false);
  assert.equal(app.get('board-control').hidden,true);assert.equal(app.get('chip-28-name').textContent,'ATmega328P');
  assert.equal(app.get('machine-memory').textContent,'32');assert.equal(app.get('machine-details').textContent,'2 КБ SRAM · 1 КБ EEPROM · 16 МГц');
  assert.equal(app.get('download').getAttribute('aria-disabled'),null);assert.match(app.get('download').href,/\/test\.hex$/);
  assert.match(app.get('download').download,/^arduino-atmega328p-16mhz-.*\.hex$/);
  assert.equal(app.get('download-eeprom').getAttribute('aria-disabled'),'true');assert.equal(app.get('download-eeprom').getAttribute('href'),null);
  assert.equal(app.get('package-import').hidden,true);assert.equal(app.get('package-file').disabled,true);
  assert.match(app.get('rom-details').textContent.replace(/\s/g,''),/496Бпрограмма\+16Бзвук=512\/32768БFlash/);
  assert.equal(app.get('fuse-low').textContent,'—');assert.equal(app.get('fuse-high').textContent,'—');
  assert.match(app.get('right-output-label').textContent,/PD3 \/ OC2B · D3/);
  const init=app.workers.at(-1).messages[0];assert.equal(init.engine,'avr8js');assert.equal(init.entry.flashHex,entry.flashHex);
  assert.equal(app.preview.src,'');assert.equal(app.contexts.length,0);
  assert.equal(app.location.searchParams.get('device'),'atmega328p');assert.equal(app.location.searchParams.get('board'),'arduino-16mhz');
  select(app,arduinoCatalog().entries[1].id);assert.match(app.get('right-output-label').textContent,/PB1 \/ OC1A · D9/);
  assert.match(app.get('scope-left-label').textContent,/D9/);
  app.get('signal-point').value='input';app.get('signal-point').onchange();assert.match(app.get('scope-left-label').textContent,/OCR1A/);
  assert.equal(app.get('speech-audit').textContent,'Исследование Speex ↗');
});

test('Arduino deep links work at root and Pages prefixes, while music retains exactly the original devices',async()=>{
  for(const prefix of ['/','/MicroMusic/'])for(const entry of arduinoCatalog().entries){
    const app=await fixture({prefix,firmware:entry.id});
    assert.equal(app.get('selected-title').textContent,entry.title);assert.equal(app.body.dataset.device,'atmega328p');
    assert.equal(app.location.searchParams.get('firmware'),entry.id);
    assert.equal(app.get('download').href,'https://example.test'+prefix+'web-player/firmware/atmega328p/test.hex');
  }
  const app=await fixture({speech:false,device:'atmega328p'});
  assert.equal(app.get('device-arduino-option').hidden,true);assert.equal(app.get('device-arduino-option').disabled,true);
  assert.equal(app.body.dataset.device,'attiny13a');assert.ok(app.fetches.every(url=>!url.includes('firmware-atmega328p')));
  assert.equal(app.radios.find(radio=>radio.value==='avr8js').disabled,true);
});

test('device switches stop prior playback and restore the previous supported engine without exposing Speex on Tiny88',async()=>{
  const app=await fixture();
  const js=app.radios.find(radio=>radio.value==='js');js.checked=true;js.onchange();
  const old=app.workers.at(-1);await app.get('play').onclick();await choose(app,'atmega328p');
  assert.equal(old.terminated,true);assert.equal(app.body.dataset.playing,'false');
  assert.equal(app.radios.find(radio=>radio.checked).value,'avr8js');
  for(const radio of app.radios)assert.equal(radio.disabled,radio.value!=='avr8js');
  await choose(app,'attiny88');assert.ok(cards(app).every(card=>card.dataset.firmware.startsWith('lpx-bread-')));
  assert.ok(cards(app).every(card=>card.dataset.firmware!=='lpx-bread-low15'));
  await choose(app,'attiny13a');assert.equal(app.radios.find(radio=>radio.checked).value,'js');
  assert.equal(app.get('device-select').value,'attiny13a');assert.match(app.get('download').download,/hq4/);
  assert.equal(app.get('package-file').disabled,false);
});

test('real Arduino transport drains the measured startup plus complete phrase before one-shot pause/replay',async()=>{
  const app=await fixture({device:'atmega328p'}),entry=arduinoCatalog().entries[0];
  await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  app.position(entry.phraseSamples*6);assert.equal(app.body.dataset.playing,'true','Content-only duration cannot cut the final firmware outputs');
  app.position(Math.ceil(entry.playbackCycles/entry.cpuHz*48000));
  assert.equal(app.body.dataset.playing,'false');assert.equal(app.get('play-label').textContent,'Ещё раз');
  const old=app.workers.at(-1);await app.get('play').onclick();await flush();
  assert.equal(old.terminated,true);assert.equal(app.body.dataset.playing,'true');
  await app.get('play-original').onclick();assert.equal(app.original.paused,false);assert.equal(app.body.dataset.playing,'false');
  await app.get('play').onclick();assert.equal(app.original.paused,true);
});

test('bad or delayed Arduino catalogs leave real HQ4 playback usable and stale selections cannot win a device race',async()=>{
  const invalid=arduinoCatalog();invalid.entries[0].flashBytes++;
  const app=await playerApp({catalogs:{'firmware-atmega328p.json':invalid}});
  assert.equal(app.body.dataset.device,'attiny13a');await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  await choose(app,'atmega328p');assert.equal(app.get('device-select').value,'attiny13a');assert.match(app.get('error').textContent,/Arduino/);
  const wait=deferred();let attempts=0;
  const delayed=await fixture({fetchHook:({url,response})=>{
    if(!url.pathname.endsWith('firmware-atmega328p.json'))return;
    return ++attempts===1?{ok:false,status:503}:attempts===2?wait.promise.then(()=>response):undefined;
  }});
  const pending=choose(delayed,'atmega328p');await choose(delayed,'attiny13a');wait.resolve();await pending;
  assert.equal(delayed.body.dataset.device,'attiny13a');
  // A previously validated catalog is reused; repeated switching does not issue
  // mutable duplicate catalog requests or duplicate the library entries.
  await choose(delayed,'atmega328p');await choose(delayed,'attiny13a');await choose(delayed,'atmega328p');
  assert.equal(cards(delayed).length,2);assert.equal(delayed.fetches.filter(url=>url.includes('firmware-atmega328p')).length,2);
});
