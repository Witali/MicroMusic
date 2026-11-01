import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {playerApp,deferred} from './helpers/player-app.mjs';

const manifest=JSON.parse(readFileSync(new URL('../audio/lpx-bread/manifest.json',import.meta.url)));
const flush=()=>new Promise(setImmediate);
const fixture=options=>playerApp({speech:false,device:'attiny88',board:'mh-et-live-16mhz',catalogs:{'manifest.json':manifest},...options});
const media=app=>['reference','compact','quality'].map(id=>app.get('lpx-'+id+'-audio'));
const compactText=text=>text.replace(/\s/g,'');

test('native LPX comparison appears only on ATtiny88 with actual costs and project-relative downloads',async()=>{
  const small=await fixture({device:'attiny13a'});
  assert.equal(small.get('lpx-previews').hidden,true);
  assert.ok(small.fetches.every(url=>!url.endsWith('/lpx-bread/manifest.json')));
  const app=await fixture();await flush();
  assert.equal(app.get('lpx-previews').hidden,false);
  assert.equal(app.get('lpx-preview-cards').hidden,false);
  assert.equal(app.get('lpx-preview-title').textContent,manifest.title);
  assert.equal(app.get('lpx-reference-label').textContent,manifest.reference.label);
  assert.equal(app.get('lpx-reference-audio').src,'https://example.test/MicroMusic/web-player/'+manifest.reference.audio);
  for(const item of manifest.variants){
    assert.equal(app.get('lpx-'+item.id+'-label').textContent,item.label);
    assert.equal(app.get('lpx-'+item.id+'-audio').src,'https://example.test/MicroMusic/web-player/'+item.audio);
    const text=compactText(app.get('lpx-'+item.id+'-meta').textContent);
    assert.ok(text.includes(String(item.bytes)+'Б'));
    assert.ok(text.includes(String(item.bitrateBps)+'бит/с'));
    assert.equal(app.get('lpx-'+item.id+'-download').href,'https://example.test/MicroMusic/web-player/'+item.stream);
    assert.equal(app.get('lpx-'+item.id+'-download').download,item.id+'.lpx');
  }
  const speech=await playerApp({device:'attiny88',catalogs:{'manifest.json':manifest}});
  assert.equal(speech.get('lpx-previews').hidden,true);
  const root=await fixture({prefix:'/'});await flush();
  assert.equal(root.get('lpx-quality-download').href,'https://example.test/web-player/'+manifest.variants[1].stream);
});

test('native controls pause each other and real firmware transport without creating another AVR engine',async()=>{
  const app=await fixture();await flush();
  const [reference,compact,quality]=media(app);
  await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  await quality.play();
  assert.equal(app.body.dataset.playing,'false');assert.equal(app.body.dataset.lpxPreviewPlaying,'true');
  assert.equal(app.get('run-status').textContent,'WAV-превью LPX');
  assert.equal(app.worklets[0].messages.at(-1).value,false);
  await compact.play();assert.equal(quality.paused,true);
  await reference.play();assert.equal(compact.paused,true);
  assert.equal(app.workers.length,1);
  await app.get('play').onclick();
  assert.ok(media(app).every(audio=>audio.paused));assert.equal(app.body.dataset.playing,'true');
  app.get('volume').value='.3';app.get('volume').oninput();
  assert.ok(media(app).every(audio=>audio.volume===.3));
});

test('preview cancels a pending firmware start and pagehide stops native audio',async()=>{
  const app=await fixture({holdWorklet:true});await flush();
  const pending=app.get('play').onclick();
  await app.get('lpx-compact-audio').play();
  app.workletSetup.resolve();await pending;
  assert.equal(app.body.dataset.playing,'false');assert.equal(app.get('lpx-compact-audio').paused,false);
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
  app.pagehide();assert.ok(media(app).every(audio=>audio.paused));
});

test('LPX speech metadata uses its actual sample rate and native previews cancel a pending original',async()=>{
  const catalog=JSON.parse(readFileSync(new URL('../firmware-attiny88-16mhz.json',import.meta.url)));
  const entry={...catalog.entries[0],kind:'speech',codec:'lpx-v5',sampleHz:8000,phraseSamples:manifest.samples,
    originalAudioUrl:'./'+manifest.reference.audio,playOnce:true};
  catalog.defaultId=entry.id;catalog.entries=[entry];
  const app=await fixture({catalogs:{'manifest.json':manifest,'firmware-attiny88-16mhz.json':catalog}});await flush();
  assert.match(app.get('catalog').children[0].children[0].children[1].children[1].textContent,/речь 8 кГц/);
  assert.equal(app.get('speech-audit').textContent,'Исследование LPX ↗');
  assert.match(app.get('speech-audit').href,/Codecs\/LPX\/README\.md$/);
  app.original.pendingPlay=deferred();const pending=app.get('play-original').onclick();
  await app.get('lpx-quality-audio').play();
  app.original.pendingPlay.resolve();await pending;
  assert.equal(app.original.paused,true);assert.equal(app.get('lpx-quality-audio').paused,false);
  assert.equal(app.get('run-status').textContent,'WAV-превью LPX');
  await app.get('play-original').onclick();
  assert.ok(media(app).every(audio=>audio.paused));assert.equal(app.original.paused,false);
});

test('device changes and late manifest/media events cannot play a hidden LPX section',async()=>{
  const held=deferred();
  const app=await fixture({fetchHook:({url,response})=>url.pathname.endsWith('/lpx-bread/manifest.json')?held.promise.then(()=>response):undefined});
  assert.equal(app.get('lpx-preview-cards').hidden,true);
  app.get('device-select').value='attiny13a';await app.get('device-select').onchange();
  held.resolve();await flush();
  assert.equal(app.get('lpx-previews').hidden,true);
  await app.get('lpx-reference-audio').play();assert.equal(app.get('lpx-reference-audio').paused,true);
  app.get('device-select').value='attiny88';await app.get('device-select').onchange();await flush();
  await app.get('lpx-quality-audio').play();
  app.get('device-select').value='attiny13a';await app.get('device-select').onchange();
  assert.ok(media(app).every(audio=>audio.paused));
});

test('invalid manifest costs or external asset paths do not affect the working firmware',async()=>{
  for(const change of [data=>{data.variants[0].bitrateBps+=100;},data=>{data.variants[1].audio='https://invalid.example/quality.wav';}]){
    const invalid=structuredClone(manifest);change(invalid);
    const app=await fixture({catalogs:{'manifest.json':invalid}});await flush();
    assert.equal(app.get('lpx-preview-cards').hidden,true);
    assert.match(app.get('lpx-preview-status').textContent,/недоступны/);
    assert.equal(app.get('error').hidden,true);
    await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  }
});

test('Space on a native audio control stays with that control rather than starting firmware',async()=>{
  const app=await fixture();await flush();
  let prevented=false;
  app.keydown({code:'Space',repeat:false,target:app.get('lpx-compact-audio'),preventDefault(){prevented=true;}});
  await flush();
  assert.equal(prevented,false);assert.equal(app.contexts.length,0);assert.equal(app.body.dataset.playing,'false');
});
