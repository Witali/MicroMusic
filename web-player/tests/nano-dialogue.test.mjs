import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseHex} from '../lib/hex.js';
import {previewWaveform} from '../lib/native-preview.js';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=data=>createHash('sha256').update(data).digest('hex');
const manifest=JSON.parse(read('web-player/audio/lpx-dialogue/manifest.json'));
const wav=read('web-player/'+manifest.audio);
const waveform=previewWaveform(wav.buffer.slice(wav.byteOffset,wav.byteOffset+wav.byteLength),
                              {sampleHz:8000,phraseSamples:manifest.samples});

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
