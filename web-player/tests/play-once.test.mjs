import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {deferred,playerApp} from './helpers/player-app.mjs';

const catalog=JSON.parse(readFileSync(new URL('../hq4-firmware.json',import.meta.url)));
const references=JSON.parse(readFileSync(new URL('../../ATtiny13A/Sound/audio-references.json',import.meta.url))).clips;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const endFrame=entry=>Math.ceil(entry.phraseSamples/entry.sampleHz*48000);

for(const selected of catalog.entries)test(`${selected.id}: speech completes once and later position messages cannot restart it`,async()=>{
  const entry={...selected,phraseSamples:references.find(clip=>clip.id===selected.audioReferenceId).samples};
  const app=await playerApp({firmware:entry.id,playOnce:true}),{get}=app;
  await get('play').onclick();
  app.position(endFrame(entry)-1);assert.equal(app.body.dataset.playing,'true');
  app.position(endFrame(entry)+2048);
  assert.equal(app.body.dataset.playing,'false');assert.equal(get('run-status').textContent,'Завершено');
  assert.equal(get('play-label').textContent,'Ещё раз');assert.equal(get('play').disabled,false);
  const elapsed=get('elapsed').textContent;
  assert.equal(elapsed,'00:'+((entry.phraseSamples/entry.sampleHz).toFixed(1).padStart(4,'0')));
  assert.equal(app.worklets[0].messages.at(-1).value,false);
  app.position(endFrame(entry)*10);
  assert.equal(get('elapsed').textContent,elapsed);assert.equal(get('run-status').textContent,'Завершено');
});

test('replay reloads the real firmware and cancels a pending original before starting at zero',async()=>{
  const app=await playerApp({playOnce:true}),{get,original}=app,entry=app.catalog.entries[0];
  await get('play').onclick();app.position(endFrame(entry));
  const old=app.workers[0],oldSession=app.worklets[0].messages.findLast(message=>message.type==='connect').session;
  original.pendingPlay=deferred();const pending=get('play-original').onclick();
  await get('play').onclick();await flush();
  original.pendingPlay.resolve();await pending;
  assert.equal(old.terminated,true);assert.equal(app.workers.length,2);
  assert.equal(app.workers[1].messages[0].type,'init');assert.equal(app.workers[1].messages[0].entry.id,entry.id);
  assert.equal(app.body.dataset.playing,'true');assert.equal(original.paused,true);
  assert.equal(get('elapsed').textContent,'00:00.0');assert.equal(get('play-label').textContent,'Пауза');
  const connection=app.worklets[0].messages.findLast(message=>message.type==='connect');
  assert.notEqual(connection.session,oldSession);
  app.position(endFrame(entry),{session:oldSession});assert.equal(app.body.dataset.playing,'true');
  app.position(endFrame(entry));assert.equal(get('run-status').textContent,'Завершено');
});

test('choosing the original while replay waits for Worker ready cancels replay autoplay',async()=>{
  const app=await playerApp({holdWorker:true,playOnce:true}),{get}=app,entry=app.catalog.entries[0];
  app.workers[0].ready();await get('play').onclick();app.position(endFrame(entry));
  await get('play').onclick();const replay=app.workers[1];
  await get('play-original').onclick();
  replay.ready();await flush();
  assert.equal(app.original.paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.equal(get('run-status').textContent,'Оригинальная запись');
});

test('changing phrase while replay waits for Worker ready cannot autoplay the old firmware',async()=>{
  const app=await playerApp({holdWorker:true,playOnce:true}),{get}=app,entry=app.catalog.entries[0];
  app.workers[0].ready();await get('play').onclick();app.position(endFrame(entry));
  await get('play').onclick();const replay=app.workers[1];
  get('catalog').children.find(item=>item.children[0].dataset.firmware==='hq4-otvechaesh-tiny').children[0].onclick();
  replay.ready();app.workers.at(-1).ready();await flush();
  assert.equal(replay.terminated,true);assert.equal(app.body.dataset.playing,'false');
  assert.equal(get('play-label').textContent,'Слушать');assert.equal(get('elapsed').textContent,'00:00.0');
  assert.equal(app.workers.at(-1).messages[0].entry.id,'hq4-otvechaesh-tiny');
});

test('pause and resume keep cumulative speech position, while music continues normally',async()=>{
  const app=await playerApp({playOnce:true}),{get}=app,entry=app.catalog.entries[0];
  await get('play').onclick();app.position(Math.floor(endFrame(entry)/2));
  await get('play').onclick();assert.equal(get('run-status').textContent,'Пауза');
  app.position(endFrame(entry));assert.equal(get('run-status').textContent,'Пауза');
  await get('play').onclick();app.position(endFrame(entry));assert.equal(get('run-status').textContent,'Завершено');
  const music=await playerApp({speech:false});await music.get('play').onclick();
  music.position(48000*120);assert.equal(music.body.dataset.playing,'true');
});
