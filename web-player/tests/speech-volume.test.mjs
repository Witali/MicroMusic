import {test} from 'node:test';
import assert from 'node:assert/strict';
import {playerApp} from './helpers/player-app.mjs';
import {speechSignals} from '../lib/speech-waveform.js';

const flush=()=>new Promise(setImmediate);

for(const native of [false,true])test(`${native?'native PWM':'filtered firmware'} waveform ignores speaker volume, including mute`,()=>{
  const raw=Float32Array.of(0,.5,-.25,.75,-1,0,.25);
  const expected=speechSignals(raw,8000,{native,cutoff:4000,volume:1});
  assert.ok(expected.output.some(value=>value!==0));
  for(const volume of [0,.2,.65])assert.deepEqual(speechSignals(raw,8000,{native,cutoff:4000,volume}),expected);
  if(!native)assert.notDeepEqual(speechSignals(raw,8000,{cutoff:12000}).output,expected.output,'RC filter must still affect the waveform');
});

// Record the actual canvas signal path, keeping the media clock fixed.
function scopeDrawing(app){
  const canvas=app.get('wave');let signal;
  const drawing={setTransform(){},fillRect(){},setLineDash(){},
    beginPath(){this.path=[];},moveTo(x,y){this.path.push([x,y]);},lineTo(x,y){this.path.push([x,y]);},
    stroke(){if(this.strokeStyle==='#c9ef86')signal=this.path;}};
  canvas.clientWidth=320;canvas.clientHeight=160;canvas.getContext=()=>drawing;
  return ()=>{app.redraw();return signal;};
}

const examples=[
  {firmware:'hq4-otvechaesh-tiny'},
  {device:'attiny88',firmware:'lpx-bread-quality'},
  {device:'atmega328p',firmware:'lpx-nano-bread-compact'},
  {device:'atmega328p',firmware:'speex-nano-bread-nb215'},
  {device:'atmega328p',firmware:'speex-nano-bread-wb98'},
  {device:'atmega328p',firmware:'lpx-nano-dialogue-quality'},
  {device:'atmega328p',firmware:'speex-nano-dialogue-wb395'},
];

for(const options of examples)test(`${options.firmware}: volume changes listening without changing full-phrase or live drawing`,async()=>{
  const app=await playerApp(options);await flush();
  assert.equal(app.location.searchParams.get('firmware'),options.firmware);
  assert.ok(+app.get('wave').dataset.samples>0);
  app.preview.currentTime=.75;
  const snapshot=scopeDrawing(app);
  // Before playback both views use the retained firmware waveform. This also
  // covers native live playback; its media position stays at zero in this model.
  for(const view of ['phrase','live']){
    app.get('signal-view').value=view;app.get('signal-view').onchange();
    const signals=app.get('signal-point-control').hidden?['output']:['input','output'];
    for(const signal of signals){
      app.get('signal-point').value=signal;app.get('signal-point').onchange();
      const before=snapshot();assert.ok(before.some(([,y])=>y!==80));
      const messageCount=app.workers.at(-1)?.messages.length;
      for(const volume of [0,.2,.65,1]){
        app.get('volume').value=String(volume);app.get('volume').oninput();
        assert.deepEqual(snapshot(),before,`${view}/${signal} at volume ${volume}`);
        assert.equal(app.preview.volume,volume);assert.equal(app.original.volume,volume);
        assert.equal(app.workers.at(-1)?.messages.length,messageCount,'volume must not change renderer controls');
      }
    }
  }
  await app.get('play').onclick();
  const workers=app.workers.length,contexts=app.contexts.length;
  app.get('volume').value='0';app.get('volume').oninput();
  assert.equal(app.body.dataset.playing,'true');assert.equal(app.workers.length,workers);assert.equal(app.contexts.length,contexts);
  if(app.preview.src){
    const before=snapshot();app.get('volume').value='1';app.get('volume').oninput();
    assert.deepEqual(snapshot(),before);assert.equal(app.preview.paused,false);
  }else{
    const gain=app.contexts[0].gains[0];assert.equal(gain.gain.value,0);
    assert.equal(app.worklets[0].destination,gain);assert.equal(gain.destination,app.contexts[0].destination);
    assert.ok(app.workers[0].messages.filter(message=>message.controls).every(message=>message.controls.volume===1));
    // Active emulator live scopes come from the worker rather than the saved WAV.
    const worker=app.workers[0],state={registers:new Uint8Array(32),pc:0,cycles:123,irqs:1,maxISR:10,lost:0};
    worker.onmessage({data:{type:'state',state,inputScopes:[Float32Array.of(.5,-.25)],outputScopes:[Float32Array.of(.3,-.1)],averages:[128],headroom:1}});
    const before=snapshot();app.get('volume').value='.4';app.get('volume').oninput();
    assert.deepEqual(snapshot(),before);assert.equal(gain.gain.value,.4);
  }
  app.pagehide();
});

test('speaker gain starts at the selected volume and survives firmware and device switches',async()=>{
  const app=await playerApp();app.get('volume').value='.25';app.get('volume').oninput();
  await app.get('play').onclick();
  const context=app.contexts[0],gain=context.gains[0];
  assert.equal(gain.gain.value,.25);
  app.get('reset').onclick();await flush();await app.get('play').onclick();
  assert.equal(app.contexts.length,1);assert.equal(context.gains.length,1);assert.equal(gain.gain.value,.25);
  app.get('device-select').value='atmega328p';await app.get('device-select').onchange();
  await app.get('play').onclick();assert.equal(app.preview.volume,.25);
  app.get('volume').value='.1';app.get('volume').oninput();assert.equal(gain.gain.value,.1);
  app.get('device-select').value='attiny13a';await app.get('device-select').onchange();await flush();
  await app.get('play').onclick();assert.equal(gain.gain.value,.1);assert.equal(app.contexts.length,1);
  assert.ok(app.workers.every(worker=>worker.messages.filter(message=>message.controls).every(message=>message.controls.volume===1)));
  app.pagehide();
});
