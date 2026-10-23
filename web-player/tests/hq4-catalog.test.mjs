import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {parseHex} from '../lib/hex.js';
import {Renderer} from '../lib/renderer-js.js';
const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const catalog=JSON.parse(read('web-player/hq4-firmware.json'));
const frozen=JSON.parse(read('ATtiny13A/Sound/research/FROZEN_VERIFICATION.json')).variants;
const timbre=Object.fromEntries(['chego','chego-auto','chego-spectrum'].map(name=>
  [name,JSON.parse(read(`ATtiny13A/Sound/codec/timbre/${name}/verification.json`))]));

test('public HQ4 catalog is complete and has no dependency on local files or media',()=>{
  assert.equal(catalog.entries.length,7);assert.equal(catalog.defaultId,'hq4-chego-auto');
  assert.equal(new Set(catalog.entries.map(e=>e.id)).size,7);
  for(const e of catalog.entries){
    assert.equal(e.source,undefined);assert.equal(e.preview,undefined);
    assert.equal(e.reference,undefined);assert.equal(e.originalPlayer,undefined);
    assert.equal(e.sampleHz,7500);assert.equal(e.pwmHz,7500);assert.equal(e.carrierHz,37500);
  }
});
for(const entry of catalog.entries)test(`${entry.id}: public HEX, retained sources and both engines match the frozen PCM`,()=>{
  const name=entry.id.slice(4),v=timbre[entry.variant],expected=entry.codec==='hq4-t'
    ? {image_sha256:v.imageSha256,sha256:v.pcmSha256,samples:v.samples}
    : frozen[name],binary=parseHex(entry.flashHex);
  assert.equal(hash(binary),expected.image_sha256);assert.equal(hash(binary),entry.flashSha256);
  assert.equal(binary.length,entry.flashBytes);assert.ok(binary.length<=1024);
  for(const [path,sha] of Object.entries(entry.sourceInputs))assert.equal(hash(read(path)),sha,path);
  for(const Core of [Wasm,JS]){
    const c=new Core(binary),pcm=Buffer.alloc(expected.samples);
    for(let i=0;i<pcm.length;i++)pcm[i]=c.nextDuty();
    assert.equal(hash(pcm),expected.sha256);assert.equal(c.lost,0);assert.equal(c.irqCount,pcm.length*5);
  }
});

test('HQ4-T listening gain matches original HQ4 through the actual default audio chain',()=>{
  const rate=48000,count=Math.round(9216/7500*rate),powers=[];
  for(const id of ['hq4-chego',...catalog.entries.filter(e=>e.codec==='hq4-t').map(e=>e.id)]) {
    const entry=catalog.entries.find(e=>e.id===id);
    const renderer=new Renderer(entry,rate,{cutoff:9000,volume:entry.monitorGain??1});
    let sum=0;
    for(let i=0;i<count;i+=4096)for(const x of renderer.render(Math.min(4096,count-i)))sum+=x*x;
    powers.push(sum/count);
  }
  for(const power of powers.slice(1))assert.ok(Math.abs(10*Math.log10(power/powers[0]))<.001);
});
