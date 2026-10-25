import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRenderer} from '../lib/engines.js';
const read=p=>readFileSync(new URL(p,import.meta.url));
const catalog=JSON.parse(read('../firmware-attiny88.json'));
const hash=b=>createHash('sha256').update(b).digest('hex');
test('all nine current compositions, including stereo, share executable bytes',()=>{
 let code,monoCount=0;
 assert.equal(catalog.entries.length,9);
 for(const entry of catalog.entries){
  assert.equal(entry.firmwareEngine,'UM88');
  const meta=JSON.parse(read('../'+entry.buildReport));
  const verification=JSON.parse(read('../'+entry.verificationSource));
  const binary=read('../'+entry.source.replace(/\.hex$/,'.bin'));
  const prefix=binary.subarray(0,meta.engineBytes);
  assert.equal(entry.archivedFirmware,false);
  assert.equal(meta.channels,entry.audioChannels);assert.equal(meta.pwmBufferFrames,192/meta.channels);
  if(meta.channels===1)monoCount++;
  if(code)assert.deepEqual(prefix,code);else code=prefix;
  assert.equal(hash(prefix),meta.engineSha256);assert.equal(hash(binary),verification.flashSha256);
  assert.equal(verification.fifoUnderruns,0);assert.equal(verification.completeLoops,1);
  assert.equal(meta.cpuHz,8000000);assert.equal(meta.synthesisHz,meta.cpuHz/1024);
 }
 assert.equal(monoCount,8);
});
for(const engine of ['js','wasm'])for(const id of ['lumiere-stereo','cancion-del-mariachi-ensemble']){
 test(engine+' browser rendering of UM88 '+id,async()=>{
  const entry=catalog.entries.find(e=>e.id===id),renderer=await createRenderer(entry,48000,{},engine);
  const pcm=renderer.render(16384);
  assert.ok(pcm.every(Number.isFinite));assert.ok(pcm.some(x=>Math.abs(x)>.005));
  assert.equal(pcm.length,16384*entry.audioChannels);assert.equal(renderer.core.lost,0);
 });
}
