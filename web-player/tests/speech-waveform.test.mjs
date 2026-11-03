import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {playerApp} from './helpers/player-app.mjs';
import {speechSignals,speechWindow} from '../lib/speech-waveform.js';
import {previewWaveform} from '../lib/native-preview.js';
import {Renderer} from '../lib/renderer-js.js';

const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const manifest=JSON.parse(read('audio/speech-waveforms/manifest.json'));
const entry=JSON.parse(read('firmware-attiny13a-speech-extra.json')).entries[0];
const asset=manifest.entries.find(item=>item.id===entry.id);
const wav=read(asset.audio);
const raw=previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),entry);
const flush=()=>new Promise(setImmediate);

test('complete phrase signal belongs to the exact retained firmware and PWM receipt',()=>{
  assert.equal(asset.flashSha256,entry.flashSha256);assert.equal(asset.eepromSha256,entry.eepromSha256);
  assert.equal(asset.wavSha256,createHash('sha256').update(wav).digest('hex'));
  const duties=Uint8Array.from(raw,value=>Math.round(value*128+128));
  assert.equal(asset.pwmSha256,createHash('sha256').update(duties).digest('hex'));
  assert.ok(raw.some(value=>Math.abs(value)>.1));assert.equal(raw.length,18048);
  assert.equal(entry.phraseSamples/entry.sampleHz,2.4064);
});

test('whole phrase input/output exactly match actual firmware resampling and player filters',()=>{
  const controls={cutoff:4000,volume:1},signals=speechSignals(raw,entry.sampleHz,controls);
  const renderer=new Renderer(entry,48000,controls);
  const output=new Float32Array(signals.output.length),input=new Float32Array(signals.input.length);
  for(let offset=0;offset<output.length;){
    const count=Math.min(4096,output.length-offset);output.set(renderer.render(count),offset);
    input.set(renderer.core.rawSamples,offset);offset+=count;
  }
  assert.deepEqual(signals.input,input);assert.deepEqual(signals.output,output);
  assert.equal(speechWindow(signals.output,48000,1).length,4080);
});

test('signal view switch preserves playback and renders full phrase for Tiny and LPX',async()=>{
  for(const options of [{firmware:entry.id},{device:'attiny88',firmware:'lpx-bread-quality'}]){
    const app=await playerApp(options);await flush();
    assert.ok(+app.get('wave').dataset.samples>0);
    assert.equal(app.get('wave').dataset.view,'phrase');
    assert.equal(app.get('signal-view-control').hidden,false);
    const workers=app.workers.length,firmware=app.location.searchParams.get('firmware');
    await app.get('play').onclick();
    app.get('signal-view').value='live';app.get('signal-view').onchange();
    assert.equal(app.get('wave').dataset.view,'live');
    assert.equal(app.workers.length,workers);assert.equal(app.location.searchParams.get('firmware'),firmware);
    app.get('signal-view').value='phrase';app.get('signal-view').onchange();
    assert.equal(app.get('wave').dataset.view,'phrase');
    if(app.preview.src)assert.equal(app.preview.paused,false);
  }
});

test('stale EEPROM waveform metadata cannot depict a different speech dictionary',async()=>{
  const stale=structuredClone(manifest);
  stale.entries.find(item=>item.id===entry.id).eepromSha256='0'.repeat(64);
  const app=await playerApp({firmware:entry.id,fetchHook:({url,response})=>
    url.pathname.endsWith('/audio/speech-waveforms/manifest.json')
      ? {...response,json:async()=>stale}:response});
  await flush();
  assert.equal(app.get('wave').dataset.samples,undefined);
  assert.ok(!app.fetches.some(url=>url.includes('/audio/speech-waveforms/'+entry.id+'.wav')));
  assert.match(app.get('scope-note').textContent,/текущий сигнал/);
  assert.equal(app.location.searchParams.get('firmware'),entry.id);
  assert.equal(app.get('play').disabled,false,'an unavailable saved waveform must not disable real playback');
});
