import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRenderer} from '../lib/engines.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';

const read=p=>readFileSync(new URL(p,import.meta.url));
const json=p=>JSON.parse(read(p));
const catalog=json('../firmware-attiny88-16mhz.json');
const bare=json('../firmware-attiny88.json');
const hash=b=>createHash('sha256').update(b).digest('hex');
const clock={target:'attiny88',cpuHz:16000000};

test('all USB arrangements share one universal executable within the loader limit',()=>{
  let code;
  assert.equal(catalog.entries.length,9);
  assert.deepEqual(catalog.entries.map(e=>e.id),bare.entries.map(e=>e.id));
  for(const e of catalog.entries){
    const meta=json('../'+e.buildReport),v=json('../'+e.verificationSource);
    const binary=read('../'+e.source.replace(/\.hex$/,'.bin'));
    const score=json('../'+e.source.replace(/synth\.hex$/,'score.json'));
    const original=bare.entries.find(b=>b.id===e.id);
    assert.deepEqual(score,json('../'+original.source.replace(/synth\.hex$/,'score.json')));
    assert.equal(e.firmwareEngine,'UM88');assert.equal(e.archivedFirmware,false);
    assert.equal(e.cpuHz,16000000);assert.equal(e.pwmHz,62500);assert.equal(e.synthesisHz,15625);
    assert.equal(meta.channels,e.audioChannels);assert.equal(meta.renderABI,'packed-stereo-u32');
    assert.ok(binary.length<=6012);assert.equal(binary.length,meta.flashBytes);
    const prefix=binary.subarray(0,meta.engineBytes);
    if(code)assert.deepEqual(prefix,code);else code=prefix;
    assert.equal(hash(prefix),meta.engineSha256);assert.equal(hash(binary),v.flashSha256);
    assert.equal(meta.requiredFuses,null);assert.equal(meta.eepromRequired,false);
    assert.equal(e.eepromHex,null);assert.equal(e.eepromBytes,0);
    assert.equal(v.passed,true);assert.equal(v.completeLoops,1);
    for(const key of ['allControlFramesMatch','allTonalMixesMatch','allPwmFramesMatch','allPercussionStatesMatch',
      'bootloaderHandoffChecked','erasedEepromChecked'])assert.equal(v[key],true,key);
    assert.equal(v.fifoUnderruns,0);assert.equal(v.lostInterrupts,0);
    assert.ok(v.minimumQueuedFrames>0);assert.ok(v.stackMarginBytes>=0);
  }
});

for(const entry of catalog.entries){
  test(entry.id+': universal USB image gives identical PCM on both AVR engines',async()=>{
    const js=await createRenderer(entry,48000,{filtered:false},'js');
    const wasm=await createRenderer(entry,48000,{filtered:false},'wasm');
    const a=new Float32Array(48000*entry.audioChannels),b=new Float32Array(a.length);
    for(let i=0;i<3;i++)a.set(js.render(16000),i*16000*entry.audioChannels);
    let at=0;
    for(const count of [1,127,8192,17,16384,16384,6895]){b.set(wasm.render(count),at*entry.audioChannels);at+=count;}
    assert.deepEqual(a,b);assert.deepEqual(js.core.data,wasm.core.data);
    assert.equal(js.core.cyc,wasm.core.cyc);assert.equal(js.core.lost,0);
    assert.ok(a.some(v=>Math.abs(v)>.005));assert.ok(js.core.eeprom.every(v=>v===255));
    assert.ok(Math.abs(js.core.irqCount-62500)<20);
    assert.equal(js.core.data[0x80],entry.audioChannels===2?0xa1:0x21);
  });
  test(entry.id+': universal application clears inherited bootloader state without EEPROM',()=>{
    const rom=read('../'+entry.source.replace(/\.hex$/,'.bin'));
    const cores=[new JS(rom,null,clock),new WASM(rom,Uint8Array.from({length:64},(_,i)=>i*67&255),clock)];
    for(const c of cores){c.sp=0x17f;c.data[0x54]=8;c.data[0x60]=0x2b;c.data[0x64]=0xff;}
    const duty=c=>entry.audioChannels===2?c.nextStereoDuty():c.nextDuty();
    let energy=0;
    for(let i=0;i<32768;i++){
      const a=duty(cores[0]);assert.equal(a,duty(cores[1]));energy+=Math.abs((a&255)-128);
    }
    assert.ok(energy>1);assert.deepEqual(cores[0].data,cores[1].data);
    for(const c of cores){assert.equal(c.data[0x54],0);assert.equal(c.data[0x60],0);
      assert.equal(c.data[0x61],0);assert.equal(c.data[0x64],0);
      assert.equal(c.lost+c.workLost,0);assert.ok(c.minSP>=0x100);}
  });
}
