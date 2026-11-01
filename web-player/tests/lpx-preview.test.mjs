import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {playerApp,deferred} from './helpers/player-app.mjs';

const manifest=JSON.parse(readFileSync(new URL('../audio/lpx-bread/manifest.json',import.meta.url)));
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const flush=()=>new Promise(setImmediate);
const fixture=options=>playerApp({speech:true,firmware:'hq4-chego-tiny',catalogs:{'manifest.json':manifest},...options});
const media=app=>['reference','compact','quality'].map(id=>app.get('lpx-'+id+'-audio'));
const compactText=text=>text.replace(/\s/g,'');

test('native LPX comparison belongs to speech, with actual costs and project-relative downloads',async()=>{
  for(const options of [{device:'attiny13a'},{device:'attiny88'},{device:'attiny88',board:'mh-et-live-16mhz'}]){
    const music=await fixture({speech:false,...options});
    assert.equal(music.get('lpx-previews').hidden,true);
    assert.equal(music.get('lpx-preview-jump').hidden,true);
    assert.ok(music.fetches.every(url=>!url.endsWith('/lpx-bread/manifest.json')));
  }
  const app=await fixture();await flush();
  assert.equal(app.get('lpx-previews').hidden,false);
  assert.equal(app.get('lpx-preview-jump').hidden,false);
  assert.match(html,/id="lpx-preview-jump"[^>]*href="#lpx-previews"/);
  assert.match(html,/MH-ET LIVE Tiny88 · 16 МГц/);
  assert.match(html,/точные PWM8-превью нативного декодера/);
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
  const root=await fixture({prefix:'/'});await flush();
  assert.equal(root.get('lpx-quality-download').href,'https://example.test/web-player/'+manifest.variants[1].stream);
});

test('native controls pause each other and real firmware transport without creating another AVR engine',async()=>{
  const app=await fixture();await flush();
  const init=app.workers[0].messages.find(message=>message.type==='init');
  const expected=app.catalog.entries.find(entry=>entry.id==='hq4-chego-tiny');
  assert.equal(init.entry.id,expected.id);assert.equal(init.entry.flashHex,expected.flashHex);
  assert.equal(app.body.dataset.device,'attiny13a');assert.equal(init.engine,'wasm');
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

test('speech previews cancel a pending HQ4 original and original playback pauses every preview',async()=>{
  const app=await fixture();await flush();
  app.original.pendingPlay=deferred();const pending=app.get('play-original').onclick();
  await app.get('lpx-quality-audio').play();
  app.original.pendingPlay.resolve();await pending;
  assert.equal(app.original.paused,true);assert.equal(app.get('lpx-quality-audio').paused,false);
  assert.equal(app.get('run-status').textContent,'WAV-превью LPX');
  await app.get('play-original').onclick();
  assert.ok(media(app).every(audio=>audio.paused));assert.equal(app.original.paused,false);
});

test('speech never loads music firmware, and hidden music previews reject late media events',async()=>{
  const held=deferred();
  const app=await fixture({device:'attiny88',board:'mh-et-live-16mhz',fetchHook:({url,response})=>url.pathname.endsWith('/lpx-bread/manifest.json')?held.promise.then(()=>response):undefined});
  assert.equal(app.get('lpx-preview-cards').hidden,true);
  assert.equal(app.get('device-control').hidden,true);assert.equal(app.get('board-control').hidden,true);
  app.get('device-select').value='attiny88';await app.get('device-select').onchange();
  app.get('board-select').value='mh-et-live-16mhz';await app.get('board-select').onchange();
  assert.ok(app.fetches.every(url=>!new URL(url).pathname.endsWith('/firmware.json')&&!url.includes('firmware-attiny88')));
  assert.equal(app.workers.length,1);
  assert.equal(app.workers[0].messages[0].entry.id,'hq4-chego-tiny');
  held.resolve();await flush();
  assert.equal(app.get('lpx-previews').hidden,false);
  const music=await fixture({speech:false,device:'attiny88'});
  await music.get('lpx-reference-audio').play();
  assert.ok(media(music).every(audio=>audio.paused));
});

test('direct LPX fragment waits for async cards and scrolls once; ordinary speech visits stay put',async()=>{
  const held=deferred();
  const app=await fixture({hash:'#lpx-previews',fetchHook:({url,response})=>url.pathname.endsWith('/lpx-bread/manifest.json')?held.promise.then(()=>response):undefined});
  assert.equal(app.get('lpx-previews').scrolls.length,0);
  held.resolve();await flush();
  assert.equal(app.get('lpx-previews').scrolls.length,1);
  assert.equal(app.get('lpx-previews').scrolls[0].block,'start');
  app.changeHash('#lpx-previews');assert.equal(app.get('lpx-previews').scrolls.length,1);
  const ordinary=await fixture();await flush();assert.equal(ordinary.get('lpx-previews').scrolls.length,0);
  ordinary.changeHash('#lpx-previews');assert.equal(ordinary.get('lpx-previews').scrolls.length,1);
  const music=await fixture({speech:false,device:'attiny88',hash:'#lpx-previews'});await flush();
  assert.equal(music.get('lpx-previews').scrolls.length,0);
});

test('leaving the LPX fragment before the manifest arrives does not pull the page back',async()=>{
  const held=deferred();
  const app=await fixture({hash:'#lpx-previews',fetchHook:({url,response})=>url.pathname.endsWith('/lpx-bread/manifest.json')?held.promise.then(()=>response):undefined});
  app.changeHash('#other');held.resolve();await flush();
  assert.equal(app.get('lpx-previews').scrolls.length,0);
  app.changeHash('#lpx-previews');assert.equal(app.get('lpx-previews').scrolls.length,1);
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
