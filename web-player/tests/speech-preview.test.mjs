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
  const entry=previews.entries[0],paired=catalog.entries.find(row=>row.id===entry.firmwareId);
  assert.deepEqual(paired.qualityPreview,entry);assert.equal(entry.flashQualified,false);
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
});

test('improved speech, original and AVR playback stop each other and the preview does not repeat',async()=>{
  const app=await playerApp({firmware:'hq4-vinni'}),{get,original}=app,improved=get('improved-audio');
  assert.equal(get('speech-preview').hidden,false);assert.match(improved.src,/vinni-q5-playback\.wav$/);
  await get('play-improved').onclick();assert.equal(improved.paused,false);assert.equal(app.contexts.length,0);
  assert.equal(get('run-status').textContent,'Улучшенная запись Q5');assert.match(get('speech-preview-score').textContent,/0,8931/);
  improved.currentTime=.7;await get('play-original').onclick();assert.equal(improved.paused,true);assert.equal(improved.currentTime,0);
  await get('play-improved').onclick();assert.equal(original.paused,true);
  await get('play').onclick();assert.equal(improved.paused,true);assert.equal(app.body.dataset.playing,'true');
  await get('play-improved').onclick();assert.equal(app.body.dataset.playing,'false');
  improved.finish();assert.equal(get('play-improved').getAttribute('aria-pressed'),'false');
  assert.equal(improved.plays,3);assert.equal(get('error').hidden,true);
});

test('improved playback cancels a pending AVR audio start',async()=>{
  const app=await playerApp({firmware:'hq4-vinni',holdWorklet:true}),{get}=app;
  const pending=get('play').onclick();await get('play-improved').onclick();
  app.workletSetup.resolve();await pending;
  assert.equal(get('improved-audio').paused,false);assert.equal(app.body.dataset.playing,'false');
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
});

test('changing the phrase cancels a preview and ignores its stale play rejection',async()=>{
  const app=await playerApp({firmware:'hq4-vinni'}),{get}=app,improved=get('improved-audio');
  improved.pendingPlay=deferred();const pending=get('play-improved').onclick();
  const next=get('catalog').children.map(row=>row.children[0]).find(card=>card.dataset.firmware==='hq4-chego-tiny');next.onclick();
  improved.pendingPlay.reject(new Error('Canceled old playback'));await pending;
  assert.equal(get('speech-preview').hidden,true);assert.equal(improved.src,'');assert.equal(improved.paused,true);
  assert.equal(get('error').hidden,true);
});
