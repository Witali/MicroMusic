import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {playerApp,deferred} from './helpers/player-app.mjs';
import {legacyManifest as manifest,publishedManifest,threeVariantManifest,low15Fixture} from './helpers/lpx-manifests.mjs';

const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
const flush=()=>new Promise(setImmediate);
const legacyApp=options=>playerApp({catalogs:{'manifest.json':manifest},...options});
const fixture=options=>legacyApp({firmware:'lpx-bread-compact',...options});
// Before publication, the VM uses an existing same-length WAV solely to test
// waveform transport; this fixture does not test the experimental decoder.
const s15App=options=>playerApp({catalogs:{'manifest.json':threeVariantManifest},
  assets:{'low15.wav':readFileSync(new URL('../audio/lpx-bread/quality.wav',import.meta.url))},...options});
const cards=app=>app.get('catalog').children.map(item=>item.children[0]);
const choose=async(app,device)=>{app.get('device-select').value=device;await app.get('device-select').onchange();await flush();};
const select=(app,id)=>cards(app).find(card=>card.dataset.firmware===id).onclick();

test('speech uses the unchanged shared selector, filtering three real HQ4 entries or two LPX previews',async()=>{
  assert.match(html,/<label for="device-select">Микроконтроллер<\/label>/);
  assert.match(html,/<option value="attiny13a">ATtiny13A<\/option><option value="attiny88">ATtiny88<\/option>/);
  assert.doesNotMatch(html,/id="lpx-previews"|lpx-preview-jump|lpx-compact-audio/);
  const app=await legacyApp();
  assert.equal(app.get('device-control').hidden,false);assert.equal(cards(app).length,3);
  assert.ok(cards(app).every(card=>card.dataset.firmware.startsWith('hq4-')));
  const worker=app.workers[0];
  await choose(app,'attiny88');
  assert.equal(worker.terminated,true);assert.equal(app.workers.length,1);
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-bread-compact','lpx-bread-quality']);
  assert.equal(app.get('catalog-count').textContent,2);
  assert.equal(app.get('board-select').value,'mh-et-live-16mhz');assert.equal(app.get('board-isp-option').disabled,true);
  assert.equal(app.get('board-control').hidden,false);
  assert.equal(app.get('board-isp-option').textContent,'ATtiny88 · 8 МГц · ISP');
  assert.ok(app.fetches.every(url=>!url.includes('firmware-attiny88')));
  const music=await playerApp({speech:false,device:'attiny88'});
  assert.ok(cards(music).every(card=>!card.dataset.firmware.startsWith('lpx-')));
  assert.ok(music.fetches.every(url=>!new URL(url).pathname.endsWith('/lpx-bread/manifest.json')));
});

test('LPX deep links choose Tiny88 and the correct native asset at both root and Pages paths',async()=>{
  for(const prefix of ['/','/MicroMusic/'])for(const variant of manifest.variants){
    const app=await fixture({prefix,firmware:'lpx-bread-'+variant.id});await flush();
    assert.equal(app.workers.length,0);assert.equal(app.contexts.length,0);
    assert.equal(app.get('device-select').value,'attiny88');assert.equal(app.body.dataset.preview,'true');
    assert.equal(app.preview.src,'https://example.test'+prefix+'web-player/'+variant.audio);
    assert.equal(app.location.searchParams.get('device'),'attiny88');
    assert.equal(app.location.searchParams.get('board'),'mh-et-live-16mhz');
    assert.equal(app.location.searchParams.get('firmware'),'lpx-bread-'+variant.id);
    assert.equal(app.get('selected-title').textContent,'LPX · '+variant.label);
    assert.equal(app.get('selected-description').textContent,manifest.title);
  }
});

test('S15 becomes the first Tiny88 choice and labels the separate experimental decoder in the shared player',async()=>{
  const app=await s15App({device:'attiny88'});await flush();
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-bread-low15','lpx-bread-compact','lpx-bread-quality']);
  assert.equal(app.get('catalog-count').textContent,3);assert.equal(app.workers.length,0);
  assert.equal(app.get('selected-title').textContent,'LPX-S15 · Очень низкий битрейт');
  assert.equal(app.get('preview-format-note').hidden,false);
  assert.equal(app.get('preview-format-note').textContent,'LPX-S15 · экспериментальный формат; нужен отдельный декодер. ');
  assert.equal(app.location.searchParams.get('firmware'),'lpx-bread-low15');
  const text=app.get('rom-details').textContent.replace(/\s/g,'');
  assert.ok(text.includes(low15Fixture.bytes+'БданныхLPX'));assert.ok(text.includes(low15Fixture.bitrateBps+'бит/с'));
  assert.match(app.get('download').href,/\/low15\.lpx$/);assert.equal(app.get('download').download,'lpx-bread-low15.lpx');
  assert.equal(app.get('wave').dataset.samples,'19200');assert.equal(app.get('avr-inspector').hidden,true);
  select(app,'lpx-bread-quality');
  assert.equal(app.get('preview-format-note').hidden,true);assert.equal(app.get('preview-format-note').textContent,'');
  assert.equal(app.get('selected-title').textContent,'LPX · Повышенное качество');
});

test('actual published Tiny88 cards are ordered low15, compact, quality with their real costs and waveform',async()=>{
  const low=publishedManifest.variants.find(variant=>variant.id==='low15');
  const ids=low?['low15','compact','quality']:['compact','quality'];
  const app=await playerApp({device:'attiny88'});await flush();
  assert.deepEqual(cards(app).map(card=>card.dataset.firmware),ids.map(id=>'lpx-bread-'+id));
  for(const id of ids){
    const variant=publishedManifest.variants.find(item=>item.id===id);select(app,'lpx-bread-'+id);await flush();
    const card=cards(app).find(item=>item.dataset.firmware==='lpx-bread-'+id);
    assert.doesNotMatch(card.children[1].children[1].textContent,/превью/i);
    const text=app.get('rom-details').textContent.replace(/\s/g,'');
    const cardText=card.children[1].children[1].textContent.replace(/\s/g,'');
    if(variant.flashMeasurement){
      const {programFlashBytes,encodedBytes,totalFlashBytes}=variant.flashMeasurement;
      assert.ok(cardText.includes(programFlashBytes+'Бкод'));assert.ok(cardText.includes(encodedBytes+'Бданных'));
      assert.ok(text.includes(programFlashBytes+'Бпрограмма+'+encodedBytes+'Бзвук='+totalFlashBytes+'БFlash'));
      assert.match(app.get('rom-details').textContent,/тестовая сборка/);
      assert.equal(app.get('flash-measurement-note').hidden,false);
      assert.match(app.get('flash-measurement-note').textContent,/без очереди и звукового ISR/);
    }else{
      assert.match(cardText,/—Бкод/);assert.match(app.get('rom-details').textContent,/не измерено/);
      assert.ok(text.includes(variant.bytes+'БданныхLPX'));assert.equal(app.get('flash-measurement-note').hidden,true);
      assert.doesNotMatch(text,/Бпрограмма|БFlash/);
    }
    assert.ok(text.includes(variant.bitrateBps+'бит/с'));
    assert.equal(app.get('machine-memory').textContent,'8');
    assert.equal(app.get('wave').dataset.samples,String(publishedManifest.samples));
  }
  if(low){
    assert.deepEqual(ids.map(id=>publishedManifest.variants.find(item=>item.id===id).bitrateBps),[1390,3360,6330]);
    select(app,'lpx-bread-low15');await app.get('play').onclick();app.preview.advance(1.2);
    assert.equal(app.get('elapsed').textContent,'00:01.2');assert.equal(app.preview.paused,false);
    await app.get('play-original').onclick();assert.equal(app.preview.paused,true);assert.equal(app.original.paused,false);
  }
});

test('actual Tiny88 test-image Flash split is shown without turning test code into firmware playback',async()=>{
  const app=await playerApp({device:'attiny88'});
  const expected={compact:[4412,1008,5420],quality:[4411,1899,6310]};
  for(const [id,values] of Object.entries(expected)){
    const measurement=publishedManifest.variants.find(variant=>variant.id===id).flashMeasurement;
    assert.deepEqual([measurement.programFlashBytes,measurement.encodedBytes,measurement.totalFlashBytes],values);
    select(app,'lpx-bread-'+id);assert.equal(app.get('board-upload').hidden,true);assert.equal(app.get('avr-inspector').hidden,true);
    assert.equal(app.get('download').textContent,'↓ Поток LPX');assert.match(app.get('download').download,/\.lpx$/);
    assert.equal(app.workers.length,0);
  }
  select(app,'lpx-bread-low15');assert.match(app.get('rom-details').textContent,/не измерено/);
  assert.equal(app.get('flash-measurement-note').hidden,true);
  assert.doesNotMatch(app.get('rom-details').textContent,/4412|4411|5420|6310/);
});

test('all three direct preview IDs retain correct assets and device URLs at root and Pages paths',async()=>{
  for(const prefix of ['/','/MicroMusic/'])for(const variant of threeVariantManifest.variants){
    const app=await s15App({prefix,firmware:'lpx-bread-'+variant.id});await flush();
    assert.equal(app.location.searchParams.get('firmware'),'lpx-bread-'+variant.id);
    assert.equal(app.location.searchParams.get('device'),'attiny88');assert.equal(app.location.searchParams.get('board'),'mh-et-live-16mhz');
    assert.equal(app.preview.src,'https://example.test'+prefix+'web-player/'+variant.audio);
    assert.equal(app.get('download').href,'https://example.test'+prefix+'web-player/'+variant.stream);
    assert.equal(app.workers.length,0);
  }
});

test('S15 uses the same pause/replay/original/volume path and restores genuine HQ4 after a device switch',async()=>{
  const app=await s15App({firmware:'lpx-bread-low15'});await flush();
  await app.get('play').onclick();app.preview.advance(.8);
  await app.get('play').onclick();assert.equal(app.preview.paused,true);assert.equal(app.preview.currentTime,.8);
  await app.get('play').onclick();app.preview.finish();assert.equal(app.get('play-label').textContent,'Ещё раз');
  await app.get('play').onclick();await flush();assert.equal(app.preview.currentTime,0);assert.equal(app.preview.paused,false);
  await app.get('play-original').onclick();assert.equal(app.preview.paused,true);assert.equal(app.original.paused,false);
  app.get('volume').value='.25';app.get('volume').oninput();assert.equal(app.preview.volume,.25);assert.equal(app.original.volume,.25);
  await choose(app,'attiny13a');assert.equal(app.original.paused,true);assert.equal(app.get('preview-format-note').hidden,true);
  assert.equal(app.workers.at(-1).messages[0].entry.flashHex,app.catalog.entries[0].flashHex);
  await choose(app,'attiny88');assert.equal(app.get('selected-title').textContent,'LPX-S15 · Очень низкий битрейт');
  assert.equal(app.get('preview-format-note').hidden,false);assert.equal(app.preview.volume,.25);
});

test('native selection exposes exact data costs and LPX download, with no invented firmware/CPU UI',async()=>{
  const app=await fixture();await flush();
  for(const variant of manifest.variants){
    select(app,'lpx-bread-'+variant.id);await flush();
    const text=app.get('rom-details').textContent.replace(/\s/g,'');
    assert.ok(text.includes(variant.bytes+'БданныхLPX'));
    assert.ok(text.includes(variant.bitrateBps+'бит/с'));assert.ok(text.includes('19200отсчётов'));
    assert.doesNotMatch(text,/Flash|SRAM|EEPROM/);
    assert.match(app.get('rom-details').textContent,/не измерено/);
    assert.equal(app.get('flash-measurement-note').hidden,true);
    assert.equal(app.get('download').textContent,'↓ Поток LPX');
    assert.equal(app.get('download').href,'https://example.test/MicroMusic/web-player/'+variant.stream);
    assert.equal(app.get('download').download,'lpx-bread-'+variant.id+'.lpx');
    assert.equal(app.get('rom-name').href,app.get('download').href);
    for(const id of ['fuses','engine-controls','cutoff-control','signal-point-control','scope-metrics','avr-inspector','package-import','rom-hash','board-upload','download-eeprom'])
      assert.equal(app.get(id).hidden,true,id);
    assert.equal(app.get('preview-note').hidden,false);
    assert.match(app.get('tiny88-power').textContent,/Целевой профиль: MH-ET LIVE Tiny88 · 16 МГц/);
    assert.equal(app.get('upload-command').textContent,'');assert.equal(app.get('memory').textContent,'');
    assert.equal(app.get('cpu-status').textContent,'');assert.equal(app.get('headroom').textContent,'—');
  }
});

test('main Play/Pause, one-shot completion, replay and reset use native audio without AVR jobs',async()=>{
  const app=await fixture();await flush();
  await app.get('play').onclick();assert.equal(app.preview.paused,false);assert.equal(app.body.dataset.playing,'true');
  assert.equal(app.get('run-status').textContent,'Нативное превью LPX');
  app.preview.advance(1.2);assert.equal(app.get('elapsed').textContent,'00:01.2');
  await app.get('play').onclick();assert.equal(app.preview.paused,true);assert.equal(app.get('run-status').textContent,'Пауза');
  assert.equal(app.preview.currentTime,1.2);
  await app.get('play').onclick();assert.equal(app.preview.currentTime,1.2);
  app.preview.finish();assert.equal(app.body.dataset.playing,'false');
  assert.equal(app.get('elapsed').textContent,'00:02.4');assert.equal(app.get('play-label').textContent,'Ещё раз');
  app.preview.advance(.1);assert.equal(app.get('elapsed').textContent,'00:02.4');
  await app.get('play').onclick();await flush();
  assert.equal(app.preview.currentTime,0);assert.equal(app.preview.paused,false);
  app.get('reset').onclick();assert.equal(app.preview.paused,true);assert.equal(app.preview.currentTime,0);
  assert.equal(app.get('elapsed').textContent,'00:00.0');assert.equal(app.get('play-label').textContent,'Слушать');
  assert.equal(app.workers.length,0);assert.equal(app.worklets.length,0);
});

test('original reference and selected LPX share main transport and volume exclusively',async()=>{
  const app=await fixture();await app.get('play').onclick();
  await app.get('play-original').onclick();
  assert.equal(app.preview.paused,true);assert.equal(app.original.paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.equal(app.original.src,'https://example.test/MicroMusic/web-player/'+manifest.reference.audio);
  await app.get('play').onclick();assert.equal(app.original.paused,true);assert.equal(app.preview.paused,false);
  app.get('volume').value='.3';app.get('volume').oninput();
  assert.equal(app.preview.volume,.3);assert.equal(app.original.volume,.3);
  app.pagehide();assert.equal(app.preview.paused,true);assert.equal(app.original.paused,true);
});

test('changing LPX quality stops both media and resets the shared transport',async()=>{
  const app=await fixture();await app.get('play').onclick();app.preview.advance(.8);
  select(app,'lpx-bread-quality');assert.equal(app.preview.paused,true);assert.equal(app.preview.currentTime,0);
  assert.match(app.preview.src,/quality\.wav$/);assert.equal(app.get('elapsed').textContent,'00:00.0');
  assert.equal(app.location.searchParams.get('firmware'),'lpx-bread-quality');
  await app.get('play-original').onclick();select(app,'lpx-bread-compact');
  assert.equal(app.original.paused,true);assert.equal(app.original.currentTime,0);
});

test('returning to Tiny13 restores exact HQ4 firmware, controls, binary downloads and AVR playback',async()=>{
  const app=await fixture();await app.get('play').onclick();
  await choose(app,'attiny13a');
  const init=app.workers.at(-1).messages[0],expected=app.catalog.entries[0];
  assert.equal(app.preview.paused,true);assert.equal(app.preview.src,'');
  assert.equal(init.entry.id,expected.id);assert.equal(init.entry.flashHex,expected.flashHex);assert.equal(init.engine,'wasm');
  for(const id of ['fuses','engine-controls','cutoff-control','signal-point-control','scope-metrics','avr-inspector','rom-hash'])
    assert.equal(app.get(id).hidden,false,id);
  assert.equal(app.get('preview-note').hidden,true);assert.equal(app.body.dataset.preview,'false');
  assert.equal(app.get('board-isp-option').disabled,true);assert.equal(app.get('board-control').hidden,true);
  assert.equal(app.get('download').textContent,'↓ Flash HEX');assert.match(app.get('download').download,/\.hex$/);
  assert.equal(app.location.searchParams.has('device'),false);assert.equal(app.location.searchParams.has('board'),false);
  await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');assert.equal(app.get('run-status').textContent,'Воспроизведение');
});

test('a pending native play cannot resume after device/reset changes or overwrite fresh playback',async()=>{
  for(const change of [app=>choose(app,'attiny13a'),app=>app.get('reset').onclick()]){
    const app=await fixture();app.preview.pendingPlay=deferred();const pending=app.get('play').onclick();
    await change(app);app.preview.pendingPlay.resolve();await pending;
    assert.equal(app.preview.paused,true);assert.equal(app.body.dataset.playing,'false');assert.equal(app.get('error').hidden,true);
  }
  const app=await fixture();app.preview.pendingPlay=deferred();const pending=app.get('play').onclick(),old=app.preview.pendingPlay;
  select(app,'lpx-bread-quality');app.preview.pendingPlay=null;await app.get('play').onclick();
  old.reject(new Error('stale playback failure'));await pending;
  assert.equal(app.body.dataset.playing,'true');assert.equal(app.get('error').hidden,true);
});

test('switching to native preview cancels pending AVR AudioWorklet startup and old worker events',async()=>{
  const app=await legacyApp({holdWorklet:true});const old=app.workers[0],pending=app.get('play').onclick();
  await choose(app,'attiny88');await app.get('play').onclick();
  app.workletSetup.resolve();await pending;
  old.onmessage({data:{type:'error',message:'stale AVR error'}});
  assert.equal(app.preview.paused,false);assert.equal(app.body.dataset.playing,'true');assert.equal(app.get('error').hidden,true);
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
});

test('a pending original is canceled when the selected LPX starts or the device changes',async()=>{
  const app=await fixture();app.original.pendingPlay=deferred();const pending=app.get('play-original').onclick();
  await app.get('play').onclick();app.original.pendingPlay.resolve();await pending;
  assert.equal(app.original.paused,true);assert.equal(app.preview.paused,false);
  app.original.pendingPlay=deferred();const second=app.get('play-original').onclick();
  await choose(app,'attiny13a');app.original.pendingPlay.reject(Object.assign(new Error('aborted'),{name:'AbortError'}));await second;
  assert.equal(app.original.paused,true);assert.equal(app.get('error').hidden,true);
});

test('choosing the original cancels native audio that is still waiting for play approval',async()=>{
  const app=await fixture();app.preview.pendingPlay=deferred();const pending=app.get('play').onclick();
  await app.get('play-original').onclick();app.preview.pendingPlay.resolve();await pending;
  assert.equal(app.original.paused,false);assert.equal(app.preview.paused,true);
  assert.equal(app.body.dataset.playing,'false');assert.equal(app.get('run-status').textContent,'Оригинальная запись');
});

test('actual WAV samples populate the shared waveform, with stale waveform results ignored',async()=>{
  const held=deferred();
  const app=await fixture({fetchHook:({url,response})=>url.pathname.endsWith('/compact.wav')?held.promise.then(()=>response):undefined});
  assert.equal(app.get('wave').dataset.samples,undefined);
  select(app,'lpx-bread-quality');await flush();assert.equal(app.get('wave').dataset.samples,'19200');
  await choose(app,'attiny13a');held.resolve();await flush();
  assert.equal(app.get('wave').dataset.samples,undefined);assert.doesNotMatch(app.get('scope-left-label').textContent,/ПРЕВЬЮ/);
});

test('invalid manifest leaves real HQ4 usable and native waveform failure does not invent CPU state',async()=>{
  const invalid=structuredClone(manifest);invalid.variants[0].bitrateBps+=100;
  const unavailable=await playerApp({catalogs:{'manifest.json':invalid}});
  assert.equal(cards(unavailable).length,3);await unavailable.get('play').onclick();
  assert.equal(unavailable.body.dataset.playing,'true');await choose(unavailable,'attiny88');
  assert.equal(unavailable.get('device-select').value,'attiny13a');assert.equal(unavailable.workers.length,1);
  const app=await fixture({fetchHook:({url})=>url.pathname.endsWith('/compact.wav')?{ok:false,status:503}:undefined});await flush();
  assert.match(app.get('scope-left-label').textContent,/НЕДОСТУПНА/);
  assert.equal(app.get('avr-inspector').hidden,true);await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
});

test('native play rejection is reported, and Space still drives the same primary transport',async()=>{
  const app=await fixture();app.preview.pendingPlay=deferred();const pending=app.get('play').onclick();
  app.preview.pendingPlay.reject(new Error('unavailable'));await pending;
  assert.match(app.get('error').textContent,/LPX-превью/);assert.equal(app.get('play').disabled,false);
  app.preview.pendingPlay=null;let prevented=false;
  app.keydown({code:'Space',repeat:false,target:{tagName:'BODY'},preventDefault(){prevented=true;}});await flush();
  assert.equal(prevented,true);assert.equal(app.body.dataset.playing,'true');
});
