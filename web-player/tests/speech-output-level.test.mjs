import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pwmGain} from '../../Codecs/common/pwm-gain.mjs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const json=path=>JSON.parse(read(path));
const hash=data=>createHash('sha256').update(data).digest('hex');

test('LPX and Speex public PWM spans use calibrated firmware gain without saturation',()=>{
  const nano=json('firmware-atmega328p.json'),tiny=json('firmware-lpx-attiny88.json');
  const speex=json('firmware-speex-atmega328p.json'),dialogue=json('audio/lpx-dialogue/manifest.json');
  const recordings=[...nano.variants.map(v=>({level:v.outputLevel,audio:nano.clips.find(c=>c.clipId===v.clipId).variants.find(p=>p.id===v.id).audio})),
    ...speex.variants.map(v=>({level:v.outputLevel,audio:v.audio})),{level:dialogue.outputLevel,audio:dialogue.audio}];
  assert.equal(recordings.length,18);
  for(const {level,audio}of recordings){
    assert.equal(level.implementation,'producer-constant-q7');assert.equal(level.saturatedSamples,0);
    assert.ok(level.numerator>=128&&level.numerator<=255);assert.equal(level.shift,7);
    const wav=read(audio),pcm=Buffer.from(Array.from({length:wav.readUInt32LE(40)/2},(_,i)=>wav.readInt16LE(44+i*2)/256+128));
    assert.equal(hash(pcm),level.after.pcmSha256,audio);
    assert.equal(Math.min(...pcm),level.after.minimumDuty);assert.equal(Math.max(...pcm),level.after.maximumDuty);
    assert.ok(Math.max(128-level.after.minimumDuty,level.after.maximumDuty-128)>=125,audio);
    if(level.numerator>128){
      assert.ok(level.after.minimumDuty>=2&&level.after.maximumDuty<=254);
      assert.ok(level.after.rms>level.before.rms);
    }
  }
  for(const v of tiny.variants){
    if(v.id==='low15')assert.equal(v.outputLevel.numerator,128);
    else assert.deepEqual(v.outputLevel,nano.variants.find(n=>n.clipId===v.clipId&&n.id===v.id).outputLevel);
  }
});

test('constant gain preserves silence and matches signed exact rounding for every PWM code',()=>{
  for(let n=128;n<=255;n++){
    const actual=pwmGain(Uint8Array.from({length:256},(_,v)=>v),n);
    assert.equal(actual[128],128);
    for(let v=0;v<256;v++)assert.equal(actual[v],Math.max(0,Math.min(255,Math.floor(((v-128)*n+64)/128)+128)));
  }
});
