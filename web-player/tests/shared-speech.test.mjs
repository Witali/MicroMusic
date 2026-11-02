import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {playerApp} from './helpers/player-app.mjs';
import {lpxPreviewEntries,previewWaveform} from '../lib/native-preview.js';

const definitions=JSON.parse(readFileSync(new URL('../speech-examples.json',import.meta.url)));
const clips=JSON.parse(readFileSync(new URL('../audio/lpx-speech/manifest.json',import.meta.url))).clips;
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const choose=async(app,device)=>{app.get('device-select').value=device;await app.get('device-select').onchange();await flush();};

test('all speech devices show the same four phrases in the same order',async()=>{
  const app=await playerApp();await flush();
  for(const device of ['attiny13a','attiny88','atmega328p']){
    await choose(app,device);
    assert.deepEqual(cards(app).map(card=>card.children[1].children[0].textContent),definitions.examples.map(item=>item.title));
    assert.deepEqual(cards(app).map(card=>card.children[0].textContent),['01','02','03','04']);
    assert.equal(app.get('catalog-count').textContent,4);
  }
});

test('changing microcontroller retains the phrase and supported quality',async()=>{
  const app=await playerApp({device:'atmega328p',firmware:'lpx-nano-vinni-quality'});await flush();
  assert.equal(app.get('speech-profile-select').children.length,5);
  await choose(app,'attiny88');assert.equal(app.location.searchParams.get('firmware'),'lpx-vinni-quality');
  await choose(app,'attiny13a');assert.equal(app.location.searchParams.get('firmware'),'hq4-vinni');
  assert.equal(app.get('speech-profile-control').hidden,true);
  await choose(app,'atmega328p');assert.equal(app.location.searchParams.get('firmware'),'lpx-nano-vinni-compact');
  assert.equal(app.get('speech-profile-control').hidden,false);
  app.get('speech-profile-select').value='lpx-nano-vinni-quality';app.get('speech-profile-select').onchange();await flush();
  assert.equal(app.location.searchParams.get('firmware'),'lpx-nano-vinni-quality');
  assert.equal(cards(app).length,4);
});

test('an oversized image remains in its ordered slot with a precise size and no click action',async()=>{
  const unavailable={...definitions,unavailable:[{device:'attiny13a',phraseId:'bread',flashBytes:1074,flashLimitBytes:1024}]};
  const app=await playerApp({catalogs:{'speech-examples.json':unavailable},fetchHook:({url,response})=>url.pathname.endsWith('/firmware-attiny13a-speech-extra.json')?{ok:false,status:404}:response});
  const row=cards(app)[3];
  assert.equal(row.disabled,true);assert.equal(row.getAttribute('aria-disabled'),'true');
  assert.equal(row.onclick,undefined);assert.match(row.title,/1.?074 Б Flash \/ лимит 1.?024 Б/);
  assert.equal(row.children[0].textContent,'04');
  assert.equal(app.location.searchParams.get('firmware'),'hq4-chego-tiny');
});

test('all additional LPX previews use complete public sources and valid PWM WAVs',()=>{
  for(const clip of clips){
    const example=definitions.examples.find(item=>item.id===clip.clipId);
    const source=readFileSync(new URL('../'+example.originalAudioUrl,import.meta.url));
    assert.equal(createHash('sha256').update(source).digest('hex'),example.originalSha256);
    for(const entry of lpxPreviewEntries(clip,'https://example.test/MicroMusic/web-player/')){
      assert.equal(entry.audioReferenceId,clip.clipId);
      const variant=clip.variants.find(v=>v.profile===entry.profile);
      const bytes=readFileSync(new URL('../'+variant.audio,import.meta.url));
      assert.equal(previewWaveform(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),entry).length,clip.samples);
      assert.equal(readFileSync(new URL('../'+variant.stream,import.meta.url)).length,entry.streamBytes);
      assert.ok(entry.originalPlaybackUrl.endsWith('/'+clip.clipId+'.wav'));
    }
  }
});
