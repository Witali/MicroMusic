import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {parseHex} from '../lib/hex.js';
const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const catalog=JSON.parse(read('web-player/hq4-firmware.json'));
const frozen=JSON.parse(read('ATtiny13A/Sound/research/FROZEN_VERIFICATION.json')).variants;

test('public HQ4 catalog is complete and has no dependency on local files or media',()=>{
  assert.equal(catalog.entries.length,4);assert.equal(catalog.defaultId,'hq4-chego');
  assert.equal(new Set(catalog.entries.map(e=>e.id)).size,4);
  for(const e of catalog.entries){
    assert.equal(e.source,undefined);assert.equal(e.preview,undefined);
    assert.equal(e.reference,undefined);assert.equal(e.originalPlayer,undefined);
    assert.equal(e.sampleHz,7500);assert.equal(e.pwmHz,7500);assert.equal(e.carrierHz,37500);
  }
});
for(const entry of catalog.entries)test(`${entry.id}: public HEX, retained sources and both engines match the frozen PCM`,()=>{
  const name=entry.id.slice(4),expected=frozen[name],binary=parseHex(entry.flashHex);
  assert.equal(hash(binary),expected.image_sha256);assert.equal(hash(binary),entry.flashSha256);
  assert.equal(binary.length,entry.flashBytes);assert.ok(binary.length<=1024);
  for(const [path,sha] of Object.entries(entry.sourceInputs))assert.equal(hash(read(path)),sha,path);
  for(const Core of [Wasm,JS]){
    const c=new Core(binary),pcm=Buffer.alloc(expected.samples);
    for(let i=0;i<pcm.length;i++)pcm[i]=c.nextDuty();
    assert.equal(hash(pcm),expected.sha256);assert.equal(c.lost,0);assert.equal(c.irqCount,pcm.length*5);
  }
});
