import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {deferred,playerApp} from './helpers/player-app.mjs';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const previews=JSON.parse(read('web-player/audio/speech-previews/manifest.json'));

test('published preview is the measured Q5 output with a paired mobile copy and no firmware-fit claim',()=>{
  const catalog=JSON.parse(read('web-player/hq4-firmware.json'));
  const entry=previews.entries[0],paired=catalog.entries.find(row=>row.id===entry.catalogId);
  assert.equal(paired.playback,'audio');assert.equal(paired.audioUrl,entry.audioUrl);
  assert.equal(paired.playbackUrl,entry.playbackUrl);assert.equal(paired.flashHex,undefined);
  assert.equal(paired.flashBytes,undefined);assert.equal(paired.flashQualified,false);
  assert.equal(entry.flashQualified,false);
  assert.equal(entry.releaseStatus,'pc-prototype');assert.equal(entry.stoi,.893135861645246);
  for(const [url,sha,rate] of [[entry.audioUrl,entry.audioSha256,7500],[entry.playbackUrl,entry.playbackSha256,44100]]){
    const bytes=read('web-player/'+url);assert.equal(hash(bytes),sha);
    assert.equal(bytes.toString('ascii',0,4),'RIFF');assert.equal(bytes.readUInt16LE(22),1);
    assert.equal(bytes.readUInt32LE(24),rate);assert.equal(bytes.readUInt16LE(34),16);
    const samples=bytes.readUInt32LE(40)/2;assert.ok(Math.abs(samples/rate-entry.samples/7500)<1/rate);
    if(rate===7500){
      const pcm=Buffer.alloc(samples);
      for(let i=0;i<samples;i++){const value=bytes.readInt16LE(44+i*2);assert.ok(value%256===0);pcm[i]=value/256+128;}
      assert.equal(hash(pcm),'19286c14df85e5a88e074b519646615bf549df1ca7547c52a357f41d5f2dbc4d');
      assert.equal(hash(pcm),entry.pcmSha256);
    }
  }
  assert.equal(hash(read('web-player/audio/speech-previews/vinni-q5-model.json')),entry.modelSha256);
  const html=read('web-player/index.html').toString();
  assert.doesNotMatch(html,/id="speech-preview"|id="play-improved"/);
});

test('Q5 uses the catalog and main transport, supports pause and original, and does not repeat',async()=>{
  const app=await playerApp({firmware:'hq4-vinni-q5'}),{get,original}=app,improved=get('improved-audio');
  assert.match(improved.src,/vinni-q5-playback\.wav$/);assert.equal(app.workers.length,0);
  assert.equal(app.selectors.get('.inspector').hidden,true);assert.equal(get('cutoff-control').hidden,true);
  assert.equal(get('download').textContent,'↓ WAV');assert.match(get('download').href,/vinni-q5\.wav$/);
  await get('play').onclick();assert.equal(improved.paused,false);assert.equal(app.contexts.length,0);
  assert.equal(get('run-status').textContent,'Улучшенная запись Q5');assert.equal(get('play-label').textContent,'Пауза');
  improved.currentTime=.7;await get('play').onclick();assert.equal(improved.paused,true);assert.equal(improved.currentTime,.7);
  await get('play').onclick();improved.emit('timeupdate');assert.equal(get('elapsed').textContent,'00:00.7');
  improved.currentTime=.7;await get('play-original').onclick();assert.equal(improved.paused,true);assert.equal(improved.currentTime,0);
  await get('play').onclick();assert.equal(original.paused,true);
  improved.finish();assert.equal(get('play-label').textContent,'Ещё раз');assert.equal(app.body.dataset.playing,'false');
  await get('play').onclick();assert.equal(improved.currentTime,0);
  assert.equal(improved.plays,4);assert.equal(get('error').hidden,true);
  get('catalog').children.map(row=>row.children[0]).find(card=>card.dataset.firmware==='hq4-vinni').onclick();
  assert.equal(improved.paused,true);assert.equal(app.selectors.get('.inspector').hidden,false);
  assert.equal(get('download').textContent,'↓ Flash HEX');assert.equal(app.workers.length,1);
});

test('improved playback cancels a pending AVR audio start',async()=>{
  const app=await playerApp({firmware:'hq4-vinni',holdWorklet:true}),{get}=app;
  const pending=get('play').onclick();
  get('catalog').children.map(row=>row.children[0]).find(card=>card.dataset.firmware==='hq4-vinni-q5').onclick();
  await get('play').onclick();
  app.workletSetup.resolve();await pending;
  assert.equal(get('improved-audio').paused,false);assert.equal(app.body.dataset.playing,'true');
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
});

test('changing the phrase cancels a preview and ignores its stale play rejection',async()=>{
  const app=await playerApp({firmware:'hq4-vinni-q5'}),{get}=app,improved=get('improved-audio');
  improved.pendingPlay=deferred();const pending=get('play').onclick();
  const next=get('catalog').children.map(row=>row.children[0]).find(card=>card.dataset.firmware==='hq4-chego-tiny');next.onclick();
  improved.pendingPlay.reject(new Error('Canceled old playback'));await pending;
  assert.equal(improved.src,'');assert.equal(improved.paused,true);
  assert.equal(get('error').hidden,true);
});

test('the previously published preview link now selects Q5 in the catalog',async()=>{
  const app=await playerApp({firmware:'hq4-vinni',hash:'#speech-preview'});
  assert.equal(app.location.searchParams.get('firmware'),'hq4-vinni-q5');assert.equal(app.location.hash,'');
  assert.equal(app.workers.length,0);assert.match(app.get('selected-title').textContent,/Q5/);
  const cards=app.get('catalog').children.map(row=>row.children[0]);
  assert.equal(cards.length,4);
  assert.match(cards.find(card=>card.dataset.firmware==='hq4-vinni-q5').children[1].children[1].textContent,/аудиопример/);
});
