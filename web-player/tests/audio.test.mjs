import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { Renderer } from '../lib/renderer.js';
import { AVRCore } from '../lib/avr-core.js';
import { AudioQueue } from '../lib/audio-queue.js';
import { parseHex } from '../lib/hex.js';
const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));

for (const entry of catalog.entries) {
  test(`${entry.id}: image hashes and original HTML playback are preserved`,()=>{
    const flash=parseHex(entry.flashHex),ep=entry.eepromHex ? parseHex(entry.eepromHex,64) : null;
    assert.equal(createHash('sha256').update(flash).digest('hex'),entry.flashSha256);
    if (ep) assert.equal(createHash('sha256').update(ep).digest('hex'),entry.eepromSha256);
    const html=readFileSync(new URL(entry.originalPlayer,new URL('../',import.meta.url)),'utf8');
    const coreAt=html.indexOf('class AVRCore'),start=html.lastIndexOf('<script>',coreAt)+8,end=html.indexOf('</script>',coreAt);
    assert.ok(start>=0 && end>start);
    const Original=runInNewContext(html.slice(start,end)+'\nAVRCore;');
    const original=new Original(flash,ep),optimized=new AVRCore(flash,ep);
    for (let i=0;i<37500;i++) {
      assert.equal(optimized.nextDuty(),original.nextDuty(),`Original HTML PWM ${i}`);
      assert.ok(Math.abs(optimized.cyc-original.cyc)<=2,`RETI foreground latency ${i}`);
    }
  });
}

for (const rate of [22050,44100,48000,96000]) {
  test(`audio at ${rate} Hz stays continuous across arbitrary block boundaries`,()=>{
    const entry=catalog.entries.find(x=>x.id===catalog.defaultId),whole=new Renderer(entry,rate),parts=new Renderer(entry,rate);
    const channels=whole.channels,expected=whole.render(8192),actual=new Float32Array(8192*channels);
    let offset=0;
    for (const size of [1,127,4096,17,3951]) { actual.set(parts.render(size),offset*channels); offset+=size; }
    assert.equal(offset,8192); assert.deepEqual(actual,expected);
    assert.equal(whole.core.cyc,parts.core.cyc);
    assert.ok(actual.some(x=>Math.abs(x)>.01));
  });
}

test('audio queue wraps without loss, zero-fills underruns and bounds memory',()=>{
  const q=new AudioQueue(8),out=new Float32Array(3);
  q.push(Float32Array.of(1,2,3,4,5)); assert.equal(q.take(out),3); assert.deepEqual(Array.from(out),[1,2,3]);
  q.push(Float32Array.of(6,7,8,9,10,11)); assert.equal(q.size,8);
  assert.throws(()=>q.push(Float32Array.of(12)));
  const tail=new Float32Array(10); assert.equal(q.take(tail),8);
  assert.deepEqual(Array.from(tail),[4,5,6,7,8,9,10,11,0,0]);
  q.push(Float32Array.of(12)); q.clear(); assert.equal(q.size,0);
});

test('AudioWorklet primes, pauses, resumes and clears old firmware audio',()=>{
  let Processor;
  const messages=[],mockPort={postMessage:message=>messages.push(message)};
  let text=readFileSync(new URL('../audio-worklet.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/,'');
  runInNewContext(text,{AudioQueue,AudioWorkletProcessor:class { constructor(){this.port=mockPort;} },registerProcessor:(name,Class)=>{Processor=Class;}});
  const p=new Processor(),requests=[],source={start(){},close(){},postMessage:m=>requests.push(m)};
  p.port.onmessage({data:{type:'connect',port:source,session:1}});
  p.port.onmessage({data:{type:'playing',value:true}});
  const out=new Float32Array(128);
  p.process([],[[out]]); assert.equal(requests.length,1); assert.ok(out.every(x=>x===0));
  source.onmessage({data:{type:'samples',samples:new Float32Array(4096).fill(.25)}});
  p.process([],[[out]]); assert.equal(requests.length,2); assert.ok(out.every(x=>x===0));
  source.onmessage({data:{type:'samples',samples:new Float32Array(4096).fill(.5)}});
  p.process([],[[out]]); assert.ok(out.every(x=>x===.25));
  p.port.onmessage({data:{type:'playing',value:false}});
  const size=p.queue.size; p.process([],[[out]]); assert.equal(p.queue.size,size); assert.ok(out.every(x=>x===0));
  p.port.onmessage({data:{type:'playing',value:true}}); p.process([],[[out]]); assert.ok(out.every(x=>x===.25));
  p.port.onmessage({data:{type:'disconnect',session:2}}); p.process([],[[out]]);
  assert.equal(p.queue.size,0); assert.equal(p.frames,0); assert.ok(out.every(x=>x===0));
  source.onmessage({data:{type:'samples',samples:new Float32Array(4096).fill(.9)}});
  assert.equal(p.queue.size,0,'Late packet from previous firmware leaked into new playback');
});
