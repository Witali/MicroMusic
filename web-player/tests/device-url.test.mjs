import {test} from 'node:test';
import assert from 'node:assert/strict';
import {playerApp} from './helpers/player-app.mjs';
const flush=()=>new Promise(setImmediate);
test('every selected speech controller has an explicit URL and restores on reopening',async()=>{
  for(const prefix of ['/','/MicroMusic/']){
    const app=await playerApp({prefix,device:'atmega328p',firmware:'lpx-nano-vinni-quality'});await flush();
    for(const device of ['attiny88','attiny13a','atmega328p']){
      app.get('device-select').value=device;await app.get('device-select').onchange();await flush();
      assert.equal(app.location.searchParams.get('device'),device);
      const firmware=app.location.searchParams.get('firmware'),board=app.location.searchParams.get('board');
      const reopened=await playerApp({prefix,device,firmware,board});await flush();
      assert.equal(reopened.get('device-select').value,device);
      assert.equal(reopened.location.searchParams.get('firmware'),firmware);
      assert.equal(reopened.location.searchParams.get('board'),board);
    }
  }
});
test('an explicit controller wins over a stale firmware ID from another controller',async()=>{
  for(const [device,firmware,expected] of [
    ['attiny88','speex-nano-vinni-wb98','lpx-vinni-compact'],
    ['attiny13a','lpx-nano-vinni-quality','hq4-vinni'],
    ['atmega328p','hq4-vinni','lpx-nano-vinni-compact']
  ]){
    const app=await playerApp({device,firmware});await flush();
    assert.equal(app.get('device-select').value,device);
    assert.equal(app.location.searchParams.get('device'),device);
    assert.equal(app.location.searchParams.get('firmware'),expected);
    if(device==='attiny88')assert.ok(app.get('speech-profile-select').children.every(o=>!o.value.startsWith('speex-')));
  }
});
