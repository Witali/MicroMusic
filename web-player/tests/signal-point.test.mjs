import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {Worker,MessageChannel} from 'node:worker_threads';
import {SignalPoint} from '../lib/signal-point.js';
import {PhysicalAudioRenderer} from '../lib/renderer-physical.js';
import {Renderer as DeviceRenderer} from '../lib/renderer-device.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';
import {createRenderer} from '../lib/engines.js';
import {playerApp} from './helpers/player-app.mjs';

const catalog=name=>JSON.parse(readFileSync(new URL('../'+name,import.meta.url))).entries;
const music=catalog('firmware.json'),speech=catalog('hq4-firmware.json'),tiny88=catalog('firmware-attiny88.json');

test('signal point defaults to unchanged output and applies one smoothed input gain per stereo frame',()=>{
  const selector=new SignalPoint(48000,.65),raw=Float32Array.of(1,-1,.5,-.5),output=Float32Array.of(.1,-.1,.2,-.2);
  assert.equal(selector.select(output,raw,2),output);
  const initial=selector.gain,selected=selector.select(output,raw,2,{signal:'input',volume:.3});
  const s=Math.exp(-1/(48000*.015)),first=.3+(initial-.3)*s,second=.3+(first-.3)*s;
  assert.deepEqual(selected,Float32Array.of(first,-first,.5*second,-.5*second));
  assert.equal(selector.select(output,null,2,{signal:'output',volume:.3}),output);
  assert.throws(()=>selector.select(output,null,2,{signal:'input'}),/OCR input/);
});

test('physical register input reads OCR, independently of disconnected physical pins',()=>{
  let frames=0;const reads=[];
  const core={capturePhysical(count,rate,channels){frames+=count;return new Float32Array(count*channels).fill(-1);},
    readIO(address){reads.push(address);return address===IO.OCR0A?192:64;}};
  const renderer=new PhysicalAudioRenderer({pwmHz:37500,audioChannels:2},48000,{signal:'input'},core);
  renderer.render(4);
  assert.deepEqual(renderer.registerSamples,Float32Array.of(.5,-.5,.5,-.5,.5,-.5,.5,-.5));
  assert.ok(renderer.core.rawSamples.every(x=>x===-1));
  assert.deepEqual(reads,[IO.OCR0A,IO.OCR0B,IO.OCR0A,IO.OCR0B,IO.OCR0A,IO.OCR0B,IO.OCR0A,IO.OCR0B]);
  renderer.setAudioControls({signal:'output'});renderer.render(3);
  assert.equal(renderer.registerSamples,null);assert.equal(frames,7);assert.equal(reads.length,8);
});

for(const channels of [1,2])test(`physical ${channels}-channel OCR taps preserve actual firmware, pin samples and warmed filters`,()=>{
  const entry=music.find(e=>(e.audioChannels||1)===channels),a=new DeviceRenderer(entry,48000),b=new DeviceRenderer(entry,48000);
  for(const signal of ['output','input','input','output']){
    a.setAudioControls({signal,volume:.65,cutoff:9000});b.setAudioControls({volume:.65,cutoff:9000});
    assert.deepEqual(a.render(1024),b.render(1024));
    assert.deepEqual(a.core.rawSamples,b.core.rawSamples);
    assert.deepEqual(a.core.state(),b.core.state());assert.deepEqual(a.core.data,b.core.data);
    if(signal==='input')assert.ok(a.registerSamples.every(x=>Number.isInteger(x*128+128)&&x>=-1&&x<1));
  }
});

for(const options of [{speech:true},{speech:false},{speech:false,device:'attiny88'}])
test(`shared ${JSON.stringify(options)}: selector controls sound and scope without recreating CPU/audio`,async()=>{
  const app=await playerApp(options),worker=app.workers.at(-1),select=app.get('signal-point');
  assert.equal(select.value,'output');assert.equal(app.get('scope-zero').textContent,'0');
  assert.equal(worker.messages[0].controls.signal,'output');
  await app.get('play').onclick();
  const workers=app.workers.length,contexts=app.contexts.length;
  for(const signal of ['input','output','input']){
    select.value=signal;select.onchange();
    assert.equal(worker.messages.at(-1).type,'controls');assert.equal(worker.messages.at(-1).controls.signal,signal);
    assert.equal(app.get('wave').dataset.signal,signal);assert.equal(app.get('wave-right').dataset.signal,signal);
    assert.equal(app.get('scope-zero').textContent,signal==='input'?'128':'0');
    assert.match(app.get('wave').getAttribute('aria-label'),signal==='input'?/OCR/:/после фильтра/);
  }
  assert.equal(app.workers.length,workers);assert.equal(app.contexts.length,contexts);assert.ok(!worker.terminated);
});

function message(target,type){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{target.off('message',receive);reject(Error(type+' timed out'));},15000);
  function receive(data){if(data.type!==type&&data.type!=='error')return;clearTimeout(timer);target.off('message',receive);data.type==='error'?reject(Error(data.message)):resolve(data);}
  target.on('message',receive);
});}

const cases=[
  ['ATtiny13A mono',music.find(e=>e.audioChannels!==2),'js'],
  ['ATtiny13A stereo',music.find(e=>e.audioChannels===2),'wasm'],
  ['ATtiny13A speech',speech[0],'wasm'],
  ['ATtiny13A translated',music[0],'transpiled'],
  ['ATtiny13A physical',music.find(e=>e.audioChannels===2),'device'],
  ['ATtiny88 mono',tiny88.find(e=>e.audioChannels!==2),'wasm'],
  ['ATtiny88 stereo',tiny88.find(e=>e.audioChannels===2),'js'],
];
for(const [name,entry,engine] of cases)test(name+': actual Worker switches both PCM and per-channel scopes, retaining continuous CPU/filter state',async t=>{
  const worker=new Worker(new URL('./helpers/browser-worker-node.mjs',import.meta.url));t.after(()=>worker.terminate());
  const ports=new MessageChannel();t.after(()=>ports.port1.close());
  const controls={volume:.5,cutoff:6000},ready=message(worker,'ready');
  worker.postMessage({type:'init',entry,engine,sampleRate:48000,controls});
  worker.postMessage({type:'audio-port',port:ports.port2,sampleRate:48000},[ports.port2]);await ready;
  const expected=await createRenderer(entry,48000,controls,engine),channels=expected.channels||1;
  for(const signal of ['output','input','input','output']){
    const applied=message(worker,'controls-applied');worker.postMessage({type:'controls',controls:{signal}});await applied;
    expected.setAudioControls({...controls,signal});
    const output=expected.render(1024),input=expected.physicalAudio?expected.registerSamples:expected.core.rawSamples;
    const state=message(worker,'state'),samples=message(ports.port1,'samples');ports.port1.postMessage({type:'need',frames:1024});
    const [actual,pcm]=await Promise.all([state,samples]);
    assert.deepEqual(pcm.samples,signal==='input'?Float32Array.from(input,x=>x*.5):output);
    assert.deepEqual(actual.state,expected.core.state());
    for(let ch=0;ch<channels;ch++)for(let i=0;i<512;i++){
      assert.equal(actual.outputScopes[ch][i],output[i*2*channels+ch]);
      if(input)assert.equal(actual.inputScopes[ch][i],input[i*2*channels+ch]);
    }
  }
});
