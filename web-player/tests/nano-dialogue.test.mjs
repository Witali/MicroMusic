import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {lpxDialogueEntry,previewWaveform} from '../lib/native-preview.js';
import {playerApp} from './helpers/player-app.mjs';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=data=>createHash('sha256').update(data).digest('hex');
const manifest=JSON.parse(read('web-player/audio/lpx-dialogue/manifest.json'));
const wav=read('web-player/'+manifest.audio);
const waveform=previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),
                              {sampleHz:8000,phraseSamples:manifest.samples});
const flush=()=>new Promise(setImmediate);
const cards=app=>app.get('catalog').children.map(row=>row.children[0]);

test('dialogue is selectable in the shared speech catalog with working audio, waveform and HEX',async()=>{
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'atmega328p',firmware:'speex-nano-vinni-wb98'});await flush();
    const row=cards(app).at(-1);
    assert.equal(row.dataset.firmware,'lpx-nano-dialogue-quality');assert.equal(row.children[0].textContent,'05');
    assert.equal(row.children[1].children[0].textContent,manifest.title);
    row.onclick();await flush();
    assert.equal(app.location.searchParams.get('firmware'),'lpx-nano-dialogue-quality');
    assert.equal(app.get('selected-title').textContent,manifest.title);
    assert.equal(app.preview.src,'https://example.test'+prefix+'web-player/'+manifest.audio);
    assert.equal(app.get('download').href,'https://example.test'+prefix+'web-player/'+manifest.firmware);
    assert.equal(app.get('download').download,'lpx-nano-dialogue-quality.hex');
    assert.equal(app.get('download').getAttribute('aria-disabled'),null);
    assert.equal(app.get('download-eeprom').getAttribute('aria-disabled'),'true');
    assert.equal(app.get('wave').dataset.samples,String(manifest.samples));
    assert.equal(app.get('play-original').hidden,true);assert.equal(app.get('reference-wav').hidden,true);
    assert.equal(app.get('reference-wav').getAttribute('href'),null);
    assert.equal(app.get('speech-profile-control').hidden,true);assert.equal(app.workers.length,0);
    await app.get('play').onclick();assert.equal(app.preview.paused,false);
    app.preview.advance(4);app.get('reset').onclick();await flush();
    assert.equal(app.preview.paused,true);assert.equal(app.preview.currentTime,0);
    app.get('search').value='разговор';app.get('search').oninput();
    assert.deepEqual(cards(app).map(card=>card.dataset.firmware),['lpx-nano-dialogue-quality']);
    app.get('device-select').value='attiny88';await app.get('device-select').onchange();await flush();
    assert.ok(cards(app).every(card=>card.dataset.firmware!=='lpx-nano-dialogue-quality'));
  }
});

test('dialogue deep links infer Nano and unavailable dialogue assets leave existing phrases usable',async()=>{
  const linked=await playerApp({firmware:'lpx-nano-dialogue-quality'});await flush();
  assert.equal(linked.get('device-select').value,'atmega328p');
  assert.equal(linked.location.searchParams.get('firmware'),'lpx-nano-dialogue-quality');
  const without=await playerApp({device:'atmega328p',fetchHook:({url,response})=>url.pathname.endsWith('/audio/lpx-dialogue/manifest.json')?{ok:false,status:404}:response});await flush();
  assert.equal(without.get('error').hidden,true);assert.equal(cards(without).length,4);
  const only=await playerApp({device:'atmega328p',fetchHook:({url,response})=>/\/firmware-(speex-)?atmega328p\.json$/.test(url.pathname)?{ok:false,status:503}:response});await flush();
  assert.equal(only.get('error').hidden,true);assert.equal(only.get('device-select').value,'atmega328p');
  assert.equal(only.location.searchParams.get('firmware'),'lpx-nano-dialogue-quality');
  assert.equal(only.get('download').getAttribute('aria-disabled'),null);
});

test('dialogue adapter rejects foreign assets, oversized images and incomplete IRQ verification',()=>{
  for(const mutate of [d=>d.audio='https://other.test/dialogue.wav',d=>d.firmware='../outside.hex',
    d=>d.audio+='?v=2',d=>d.flashBytes=32768,d=>d.staticSramBytes=2048,d=>d.samples--,
    d=>d.timing.underruns=1,d=>d.timing.irq_entry_cycles=0,d=>d.timing.irq_reti_complete=false,
    d=>d.timing.timer_events--,d=>d.timing.tick_interval_max_cycles=3000]){
    const bad=structuredClone(manifest);mutate(bad);
    assert.throws(()=>lpxDialogueEntry(bad,'https://example.test/web-player/'));
  }
});

test('combined Nano dialogue preserves the requested order and exact three pauses',()=>{
  assert.equal(manifest.device,'atmega328p');assert.equal(manifest.cpuHz,16000000);
  assert.equal(manifest.samples,81254);assert.equal(manifest.durationSeconds,10.15675);
  assert.deepEqual(manifest.segments.map(item=>item.clipId??item.seconds),
                   ['vinni',0.5,'chego',1.5,'otvechaesh',0.5,'bread']);
  let at=0;
  for(const segment of manifest.segments){
    assert.equal(segment.startSample,at);assert.ok(segment.samples>0);
    const data=waveform.subarray(at,at+segment.samples);
    if(segment.kind==='silence')assert.ok(data.every(sample=>sample===0));
    else assert.ok(data.some(sample=>Math.abs(sample)>.05));
    at+=segment.samples;
  }
  assert.equal(at,waveform.length);
});

test('retained HEX contains every exact compressed segment and leaves bootloader space',()=>{
  const hex=read('web-player/'+manifest.firmware),image=Buffer.from(parseHex(hex.toString(),30720));
  assert.equal(hash(hex),manifest.hexSha256);assert.equal(image.length,manifest.flashBytes);
  assert.ok(image.length<=30720);assert.ok(manifest.staticSramBytes<2048);
  assert.equal(manifest.programFlashBytes+manifest.streamBytes,image.length);
  for(const segment of manifest.segments){
    const stream=read('web-player/'+segment.stream);
    assert.equal(hash(stream),segment.streamSha256);assert.equal(stream.length,segment.streamBytes);
    assert.equal(stream.subarray(0,5).toString('binary'),'L4HY\x05');
    assert.equal(stream.readUInt32LE(8),segment.samples);
    assert.deepEqual(image.subarray(segment.romOffset,segment.romEnd),stream);
  }
});

test('normalization, exact WAV and complete active-IRQ receipts remain bound to source',()=>{
  assert.equal(hash(wav),manifest.wavSha256);
  const clips=manifest.segments.filter(item=>item.kind==='speech');
  assert.ok(clips.every(item=>Math.abs(item.normalized.lufs-manifest.normalization.targetLufs)<.1));
  assert.ok(clips.every(item=>item.decoded.truePeakDb<=-1.5));
  assert.ok(Math.max(...clips.map(item=>item.decoded.lufs))-Math.min(...clips.map(item=>item.decoded.lufs))<=1.1);
  for(const clip of clips)assert.equal(hash(read('web-player/'+clip.source)),clip.sourceSha256);
  for(const [path,expected]of Object.entries(manifest.sourceSha256))
    assert.equal(hash(read(path).toString('utf8').replaceAll('\r\n','\n')),expected,path);
  const timing=manifest.timing;
  assert.equal(timing.underruns,0);assert.equal(timing.played,81254);
  assert.equal(timing.timer_ticks,timing.played);assert.equal(timing.timer_events,timing.played);
  assert.equal(timing.queued_at_stop,0);assert.equal(timing.irq_entry_cycles,4);
  assert.equal(timing.irq_reti_complete,true);assert.ok(timing.stack_margin_all_bytes>0);
});
