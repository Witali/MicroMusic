import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const previews=JSON.parse(read('web-player/audio/speech-previews/manifest.json'));

test('published preview is the measured Q5 output with a paired mobile copy and no firmware-fit claim',()=>{
  const catalog=JSON.parse(read('web-player/hq4-firmware.json'));
  const entry=previews.entries[0];
  assert.equal(catalog.entries.length,3);
  for(const firmware of catalog.entries){
    assert.ok(firmware.flashHex);assert.notEqual(firmware.playback,'audio');
    assert.equal(firmware.id.includes('q5'),false);
  }
  assert.equal(entry.flashQualified,false);
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
  const html=read('web-player/index.html').toString();
  assert.doesNotMatch(html,/id="speech-preview"|id="play-improved"|id="improved-audio"/);
});
