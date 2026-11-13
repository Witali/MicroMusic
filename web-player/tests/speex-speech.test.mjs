import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {speexFirmwareEntries} from '../lib/speex-preview.js';
import {previewWaveform} from '../lib/native-preview.js';
import {parseHex} from '../lib/hex.js';
import {playerApp} from './helpers/player-app.mjs';
import {assertRecordedBuildSource} from './helpers/recorded-build-source.mjs';
const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const catalog=JSON.parse(read('firmware-speex-atmega328p.json'));
const common=JSON.parse(read('speech-examples.json'));
const hash=b=>createHash('sha256').update(b).digest('hex');
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(row=>row.children[0]);

test('twelve public Speex examples bind complete originals, raw packets, PWM WAVs and Nano HEX',()=>{
  assert.equal(catalog.pwmPin,3);assert.equal(catalog.pwmOutput,'D3 / PD3 / OC2B');
  assert.equal(catalog.physicalBoardMeasured,false);
  const entries=speexFirmwareEntries(catalog,'https://example.test/MicroMusic/web-player/');
  assert.equal(entries.length,12);
  assert.deepEqual([...new Set(entries.map(v=>v.nominalBitrateBps))],[2150,3950,9800]);
  for(const clip of catalog.clips){
    const original=common.examples.find(c=>c.id===clip.id);
    assert.equal(clip.originalSha256,original.originalSha256);
    assert.equal(hash(read(clip.originalAudioUrl)),clip.originalSha256);
  }
  for(const [i,v] of catalog.variants.entries()){
    const raw=read(v.stream),wav=read(v.audio),hex=read(v.source);
    assert.equal(hash(raw),v.streamSha256);assert.equal(raw.length,v.packetBytes*v.frames);
    assert.equal(hash(wav),v.audioSha256);assert.equal(hash(hex),v.hexSha256);
    assert.equal(wav.toString('ascii',12,16),'fmt ');assert.equal(wav.toString('ascii',36,40),'data');
    assert.equal(wav.length,44+v.samples*2);assert.equal(wav.readUInt32LE(24),v.sampleHz);
    const signal=previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),entries[i]);
    assert.equal(signal.length,v.samples);assert.ok(signal.some(s=>s!==0));
    const pwm=Buffer.alloc(v.samples);
    for(let s=0;s<v.samples;s++){
      const sample=wav.readInt16LE(44+s*2);assert.ok(Number.isInteger(sample/256));pwm[s]=sample/256+128;
    }
    assert.equal(hash(pwm),v.pwmSha256);
    const firmware=Buffer.from(parseHex(hex.toString('ascii'),30720));
    assert.equal(firmware.length,v.flashBytes);const at=firmware.indexOf(raw);
    assert.ok(at>=0);assert.equal(firmware.indexOf(raw,at+1),-1);
    assert.equal(v.staticSramBytes+v.peakStackBytes+v.freeSramAtPeak,2048);
    assert.equal(v.timing.underruns,0);assert.equal(v.timing.includesInterrupts,true);
    assert.ok(v.samples>=v.inputSamples+v.sampleHz*.08);
  }
  for(const [path,expected] of Object.entries(catalog.sourceSha256))
    assertRecordedBuildSource('b0375795b56a40efb9d90b7ae0fe7be30f7310ad',path,expected);
});

test('Speex schema rejects wrong rates, pin routing, foreign assets and unverified timing',()=>{
  for(const mutate of [
    d=>d.pwmPin=4,d=>d.pwmPin=9,d=>d.pwmOutput='D3',d=>d.variants[0].sampleHz=16000,
    d=>d.variants[0].source='https://other.test/player.hex',d=>d.variants[0].stream='../outside.spxraw',
    d=>d.variants[0].audio+='?v=2',d=>d.variants[0].flashBytes=32768,
    d=>d.variants[0].timing.underruns=1,d=>d.variants[0].timing.includesInterrupts=false,
    d=>d.variants[0].timing.timerIntervalMaxCycles=3000,d=>d.variants[0].freeSramAtPeak=0,
    d=>d.variants[0]=d.variants[1],d=>d.variants.pop()
  ]){
    const bad=structuredClone(catalog);mutate(bad);assert.throws(()=>speexFirmwareEntries(bad,'https://example.test/web-player/'));
  }
  const alternate=structuredClone(catalog);alternate.pwmPin=9;alternate.pwmOutput='D9 / PB1 / OC1A';
  assert.ok(speexFirmwareEntries(alternate,'https://example.test/web-player/').every(e=>e.firmware.pwmPin===9));
});

test('the fourth Nano recording offers the same five codec/quality choices as the first three',async()=>{
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'atmega328p',firmware:'lpx-nano-bread-compact'});await flush();
    assert.equal(app.get('speech-profile-control').hidden,false);
    const ids=['lpx-nano-bread-compact','lpx-nano-bread-quality',
      'speex-nano-bread-nb215','speex-nano-bread-wb395','speex-nano-bread-wb98'];
    assert.deepEqual(app.get('speech-profile-select').children.map(option=>option.value),ids);
    for(const id of ids){
      app.get('speech-profile-select').value=id;app.get('speech-profile-select').onchange();await flush();
      assert.equal(app.location.searchParams.get('firmware'),id);assert.equal(app.location.searchParams.get('device'),'atmega328p');
      assert.equal(app.get('download').download,id+'.hex');
      assert.equal(new URL(app.get('download').href).pathname,prefix+'web-player/firmware/arduino-nano/'+id+'.hex');
      assert.equal(app.get('download').getAttribute('aria-disabled'),null);
      assert.equal(app.get('wave').dataset.samples,String(id.startsWith('speex-')?catalog.variants.find(v=>v.id===id).samples:19200));
      await app.get('play').onclick();assert.equal(app.preview.paused,false);
      await app.get('play-original').onclick();assert.equal(app.preview.paused,true);
      assert.equal(app.original.paused,false);assert.ok(app.original.src.endsWith('/audio/lpx-bread/original.wav'));
    }
  }
});

test('older three-phrase Speex catalogs still load, while incomplete fourth-phrase data is rejected',()=>{
  const old=structuredClone(catalog);old.clips=old.clips.filter(c=>c.id!=='bread');
  old.variants=old.variants.filter(v=>v.clipId!=='bread');
  assert.equal(speexFirmwareEntries(old,'https://example.test/web-player/').length,9);
  for(const mutate of [d=>d.variants.pop(),d=>d.clips.pop(),
    d=>d.clips.find(c=>c.id==='bread').originalAudioUrl='audio/originals/bread.wav']){
    const bad=structuredClone(catalog);mutate(bad);assert.throws(()=>speexFirmwareEntries(bad,'https://example.test/web-player/'));
  }
});

test('all Speex deep links select the right sample rate, shared D3 pin, audio and HEX at root and Pages paths',async()=>{
  for(const prefix of ['/','/MicroMusic/'])for(const variant of catalog.variants){
    const app=await playerApp({prefix,device:'atmega328p',firmware:variant.id});await flush();
    assert.equal(app.location.searchParams.get('firmware'),variant.id);
    assert.equal(app.preview.src,'https://example.test'+prefix+'web-player/'+variant.audio+(variant.outputLevel.numerator>128?'?v='+variant.outputLevel.after.pcmSha256.slice(0,16):''));
    assert.equal(app.get('download').href,'https://example.test'+prefix+'web-player/'+variant.source+(variant.outputLevel.numerator>128?'?v='+variant.hexSha256.slice(0,16):''));
    assert.equal(app.get('download').download,variant.id+'.hex');
    assert.match(app.get('tiny88-power').textContent,/D3 \/ PD3 \/ OC2B/);
    assert.equal(app.get('speech-profile-select').children.length,5);
    assert.equal(app.get('speech-profile-details').hidden,false);
    assert.equal(app.get('speech-profile-details').textContent,`Прошивка: ${variant.programFlashBytes.toLocaleString('ru')} байт · Звук: ${variant.streamBytes.toLocaleString('ru')} байт`);
    assert.ok(cards(app).slice(0,3).every(card=>!card.children[1].children[1].textContent.includes('Б код')));
    assert.equal(cards(app).length,5);assert.equal(app.workers.length,0);
    await app.get('play').onclick();assert.equal(app.preview.paused,false);
    assert.equal(app.get('run-status').textContent,'Нативное превью Speex');
    await app.get('play-original').onclick();assert.equal(app.preview.paused,true);
    assert.equal(app.original.paused,false);
    assert.ok(app.original.src.endsWith(variant.clipId==='bread'?'/audio/lpx-bread/original.wav':'/playback/'+variant.clipId+'.wav'));
  }
});

test('switching all four phrases preserves codec/quality and the same five choices',async()=>{
  for(const profile of ['wb98','wb395','nb215']){
    const app=await playerApp({device:'atmega328p',firmware:'speex-nano-vinni-'+profile});await flush();
    const labels=app.get('speech-profile-select').children.map(option=>option.textContent);
    assert.equal(labels.length,5);
    for(const [index,clip] of ['chego','otvechaesh','vinni','bread'].entries()){
      cards(app)[index].onclick();await flush();assert.equal(app.location.searchParams.get('firmware'),`speex-nano-${clip}-${profile}`);
      assert.equal(app.get('speech-profile-select').value,`speex-nano-${clip}-${profile}`);
      assert.deepEqual(app.get('speech-profile-select').children.map(option=>option.textContent),labels);
    }
  }
  const lpx=await playerApp({device:'atmega328p',firmware:'lpx-nano-vinni-quality'});await flush();
  for(const [index,clip] of ['chego','otvechaesh','vinni','bread'].entries()){
    cards(lpx)[index].onclick();await flush();assert.equal(lpx.location.searchParams.get('firmware'),`lpx-nano-${clip}-quality`);
  }
});

test('switching device stops Speex playback',async()=>{
  const app=await playerApp({device:'atmega328p',firmware:'speex-nano-chego-wb98'});await flush();
  app.get('speech-profile-select').value='speex-nano-chego-nb215';app.get('speech-profile-select').onchange();await flush();
  assert.ok(new URL(app.preview.src).pathname.endsWith('/chego/nb215.wav'));
  await app.get('play').onclick();app.get('device-select').value='attiny88';await app.get('device-select').onchange();await flush();
  assert.equal(app.preview.paused,true);assert.equal(app.get('device-select').value,'attiny88');
});

test('either Nano codec catalog can fail while the other remains usable',async()=>{
  for(const failed of ['firmware-atmega328p.json','firmware-speex-atmega328p.json']){
    const app=await playerApp({device:'atmega328p',fetchHook:({url,response})=>url.pathname.endsWith('/'+failed)?{ok:false,status:503}:response});await flush();
    assert.equal(app.get('device-select').value,'atmega328p');assert.equal(app.get('error').hidden,true);
    const options=app.get('speech-profile-select').children.map(o=>o.value);
    assert.ok(options.length>0&&options.every(id=>id.startsWith(failed.startsWith('firmware-speex')?'lpx-':'speex-')));
  }
});
