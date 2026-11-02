import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {speexDialogueProfiles} from '../lib/speex-preview.js';
import {previewWaveform} from '../lib/native-preview.js';
import {parseHex} from '../lib/hex.js';
import {playerApp} from './helpers/player-app.mjs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const data=JSON.parse(read('firmware-speex-dialogue-atmega328p.json'));
const lpx=JSON.parse(read('audio/lpx-dialogue/manifest.json'));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(row=>row.children[0]);

test('three complete Speex dialogue images fit the Nano budget and bind exact IRQ output',()=>{
  const {entries,unavailableProfiles}=speexDialogueProfiles(data,'https://example.test/MicroMusic/web-player/');
  assert.equal(entries.length,3);assert.equal(unavailableProfiles.length,0);
  assert.equal(data.sourceSamples,81254);assert.equal(data.sourceSampleHz,8000);
  assert.deepEqual(data.segments,lpx.segments.map(s=>({kind:s.kind,...(s.kind==='speech'?{clipId:s.clipId}:{seconds:s.seconds}),startSample:s.startSample,samples:s.samples})));
  assert.ok(data.sources.every(source=>Math.abs(source.normalized.lufs+18)<.1));
  for(const source of data.sources)assert.equal(hash(read(source.source)),source.sourceSha256);
  for(const [path,expected]of Object.entries(data.sourceSha256))
    assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),expected,path);
  assert.equal(data.sourceSha256['tools/dialogue_source.py'],lpx.sourceSha256['tools/dialogue_source.py']);
  for(const [i,v]of data.variants.entries()){
    assert.equal(v.available,true);assert.ok(v.flashBytes<=30720);
    const raw=read(v.stream),wav=read(v.audio),hex=read(v.source);
    assert.equal(hash(raw),v.streamSha256);assert.equal(raw.length,v.frames*v.packetBytes);
    assert.equal(hash(wav),v.audioSha256);assert.equal(hash(hex),v.hexSha256);
    assert.equal(previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),entries[i]).length,v.samples);
    const pcm=Buffer.from(Array.from({length:v.samples},(_,n)=>wav.readInt16LE(44+n*2)/256+128));
    assert.equal(hash(pcm),v.pwmSha256);assert.equal(hash(pcm),v.outputLevel.after.pcmSha256);
    assert.equal(v.outputLevel.saturatedSamples,0);
    const image=Buffer.from(parseHex(hex.toString(),30720));assert.equal(image.length,v.flashBytes);
    assert.ok(image.indexOf(raw)>=0);assert.equal(v.programFlashBytes+raw.length,image.length);
    assert.equal(v.staticSramBytes+v.peakStackBytes+v.freeSramAtPeak,2048);assert.ok(v.freeSramAtPeak>0);
    assert.equal(v.timing.samples,v.samples);assert.equal(v.timing.underruns,0);assert.equal(v.timing.includesInterrupts,true);
    assert.ok(v.samples>=v.inputSamples+v.sampleHz*.08);
  }
});

test('the fifth recording stays one card and its four choices have working audio, waveform and HEX',async()=>{
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'atmega328p',firmware:'lpx-nano-dialogue-quality'});await flush();
    assert.equal(cards(app).length,5);assert.equal(app.get('catalog-count').textContent,5);
    assert.equal(app.get('speech-profile-control').hidden,false);
    assert.deepEqual(app.get('speech-profile-select').children.map(o=>o.value),['lpx-nano-dialogue-quality',...data.variants.map(v=>v.id)]);
    for(const v of data.variants){
      app.get('speech-profile-select').value=v.id;app.get('speech-profile-select').onchange();await flush();
      assert.equal(app.location.searchParams.get('firmware'),v.id);
      assert.equal(app.get('selected-title').textContent,data.title);
      assert.equal(app.get('download').download,v.id+'.hex');
      assert.equal(new URL(app.get('download').href).pathname,prefix+'web-player/'+v.source);
      assert.equal(new URL(app.preview.src).pathname,prefix+'web-player/'+v.audio);
      assert.equal(app.get('wave').dataset.samples,String(v.samples));
      assert.equal(app.get('play-original').hidden,true);assert.equal(app.get('reference-wav').hidden,true);
      assert.equal(cards(app).length,5);assert.equal(cards(app).at(-1).dataset.firmware,v.id);
      await app.get('play').onclick();assert.equal(app.preview.paused,false);
    }
    const linked=await playerApp({prefix,firmware:data.variants[2].id});await flush();
    assert.equal(linked.get('device-select').value,'atmega328p');assert.equal(linked.location.searchParams.get('firmware'),data.variants[2].id);
  }
});

test('measured oversized dialogue profiles remain disabled in the quality menu',async()=>{
  const oversized=structuredClone(data),v=oversized.variants.find(v=>v.profile==='wb98');
  v.available=false;v.flashBytes=30721;v.programFlashBytes=v.flashBytes-v.streamBytes;
  delete v.source;delete v.audio;delete v.stream;
  const profiles=speexDialogueProfiles(oversized,'https://example.test/web-player/');
  assert.equal(profiles.entries.length,2);assert.equal(profiles.unavailableProfiles.length,1);
  const app=await playerApp({device:'atmega328p',firmware:'lpx-nano-dialogue-quality',catalogs:{'firmware-speex-dialogue-atmega328p.json':oversized}});await flush();
  const options=app.get('speech-profile-select').children;assert.equal(options.length,4);
  const disabled=options.find(o=>o.value===v.id);assert.equal(disabled.disabled,true);assert.match(disabled.textContent,/не помещается/);
  assert.ok(options.filter(o=>o!==disabled).every(o=>!o.disabled));
  app.get('speech-profile-select').value=v.id;app.get('speech-profile-select').onchange();await flush();
  assert.equal(app.location.searchParams.get('firmware'),'lpx-nano-dialogue-quality');
  assert.equal(app.get('speech-profile-select').value,'lpx-nano-dialogue-quality');
});

test('dialogue schema rejects bad timing, foreign assets and a false oversized claim',()=>{
  for(const mutate of [d=>d.variants[0].timing.underruns=1,d=>d.variants[0].source='https://other.test/dialogue.hex',
    d=>d.variants[0].available=false,d=>d.variants[0].flashBytes=32768,d=>d.variants.pop(),d=>d.variants[1]=d.variants[0]]){
    const invalid=structuredClone(data);mutate(invalid);assert.throws(()=>speexDialogueProfiles(invalid,'https://example.test/web-player/'));
  }
});
