import {test} from 'node:test';
import assert from 'node:assert/strict';
import {deferred,playerApp} from './helpers/player-app.mjs';

test('public original plays directly, shares the Pages URL and stops on repeat or firmware playback',async()=>{
  const app=await playerApp(),{original,get}=app;
  assert.equal(get('play-original').hidden,false);
  assert.equal(original.src,'https://example.test/MicroMusic/web-player/audio/originals/chego.wav');
  await get('play-original').onclick();
  assert.equal(original.paused,false);assert.equal(app.contexts.length,0,'original does not create an AVR AudioWorklet');
  assert.equal(app.body.dataset.playing,'false');assert.equal(get('run-status').textContent,'Оригинальная запись');
  assert.equal(get('play-original').textContent,'Остановить оригинал');
  original.currentTime=.5;
  await get('play-original').onclick();
  assert.equal(original.paused,true);assert.equal(original.currentTime,0);
  await get('play-original').onclick();
  await get('play').onclick();
  assert.equal(original.paused,true);assert.equal(app.body.dataset.playing,'true');
  await get('play-original').onclick();
  assert.equal(original.paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.equal(app.worklets[0].messages.at(-1).value,false);
  get('volume').value='.25';get('volume').oninput();assert.equal(original.volume,.25);
  original.finish();assert.equal(get('play-original').textContent,'Прослушать оригинал');
});

test('pending original play cannot change transport after emulator start or phrase change',async()=>{
  const app=await playerApp(),{original,get}=app;
  original.pendingPlay=deferred();
  const pending=get('play-original').onclick();
  await get('play').onclick();
  original.pendingPlay.resolve();await pending;
  assert.equal(original.paused,true);assert.equal(app.body.dataset.playing,'true');
  assert.equal(get('play-original').getAttribute('aria-pressed'),'false');
  original.pendingPlay=deferred();
  const second=get('play-original').onclick();
  const vinni=get('catalog').children.find(item=>item.children[0].dataset.firmware==='hq4-vinni').children[0];
  vinni.onclick();
  original.pendingPlay.reject(Object.assign(new Error('Playback interrupted'),{name:'AbortError'}));await second;
  assert.equal(original.paused,true);assert.match(original.src,/\/originals\/vinni\.wav$/);
  assert.equal(get('error').hidden,true);assert.equal(get('play-original').getAttribute('aria-pressed'),'false');
});

test('opening the original cancels an emulator start still waiting for its AudioWorklet',async()=>{
  const app=await playerApp({holdWorklet:true}),{get,original}=app;
  const pending=get('play').onclick();
  assert.equal(app.contexts.length,1);assert.equal(get('play').disabled,true);
  await get('play-original').onclick();
  app.workletSetup.resolve();await pending;
  assert.equal(original.paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.equal(get('run-status').textContent,'Оригинальная запись');
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
});

test('a canceled AudioWorklet failure does not interrupt or report an error over the original',async()=>{
  const app=await playerApp({holdWorklet:true}),{get,original}=app;
  const pending=get('play').onclick();
  await get('play-original').onclick();
  app.workletSetup.reject(new Error('AudioWorklet failed'));await pending;
  assert.equal(original.paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.equal(get('run-status').textContent,'Оригинальная запись');assert.equal(get('error').hidden,true);
});

test('music entries hide original playback and root hosting resolves the same asset',async()=>{
  const music=await playerApp({speech:false});
  assert.equal(music.get('play-original').hidden,true);assert.equal(music.original.src,'');
  await music.get('play-original').onclick();assert.equal(music.original.plays,0);
  const root=await playerApp({prefix:'/'});
  assert.equal(root.original.src,'https://example.test/web-player/audio/originals/chego.wav');
});

test('legacy speech URLs open the selected version of the same phrase',async()=>{
  const initial=await playerApp();
  for(const [previous,current] of Object.entries(initial.catalog.aliases)){
    const app=await playerApp({firmware:previous});
    const entry=app.workers.at(-1).messages.find(message=>message.type==='init').entry;
    assert.equal(entry.id,current,previous);
    assert.equal(app.location.searchParams.get('firmware'),current);
    assert.equal(app.original.src,`https://example.test/MicroMusic/web-player/audio/originals/${entry.audioReferenceId}.wav`);
    assert.equal(app.get('catalog').children.length,3);
  }
});

test('tiny speech shows its paired EEPROM image and research, while Vinni uses its selected HQ4 image',async()=>{
  const app=await playerApp({firmware:'hq4-otvechaesh-tiny'}),{get}=app;
  const entry=app.workers.at(-1).messages.find(message=>message.type==='init').entry;
  assert.equal(entry.codec,'tiny-period');assert.equal(get('download-eeprom').hidden,false);
  assert.equal(get('download-eeprom').href,'data:text/plain;charset=utf-8,'+encodeURIComponent(entry.eepromHex));
  assert.match(get('speech-audit').href,/tiny-speech\/otvechaesh\/README\.md$/);
  assert.equal(get('speech-audit').textContent,'Исследование речевого ядра ↗');
  assert.match(get('rom-details').textContent,/64 \/ 64 Б EEPROM/);
  const cards=get('catalog').children.map(item=>item.children[0]);
  assert.match(cards.find(card=>card.dataset.firmware===entry.id).children[1].children[1].textContent,/\+ 64 Б EEPROM/);
  cards.find(card=>card.dataset.firmware==='hq4-vinni').onclick();
  assert.equal(get('download-eeprom').hidden,true);assert.match(get('rom-details').textContent,/0 \/ 64 Б EEPROM/);
  assert.equal(get('speech-audit').textContent,'Сверка HQ4 ↗');
});
