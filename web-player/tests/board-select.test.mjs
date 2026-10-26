import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {playerApp,deferred} from './helpers/player-app.mjs';

const catalog=name=>JSON.parse(readFileSync(new URL('../'+name,import.meta.url)));
const eight=catalog('firmware-attiny88.json');
const sixteen=catalog('firmware-attiny88-16mhz.json');
const board='mh-et-live-16mhz';
const init=app=>app.workers.at(-1).messages.find(message=>message.type==='init');
const change=async(app,id,value)=>{app.get(id).value=value;await app.get(id).onchange();};
const flush=()=>new Promise(setImmediate);

test('board selection is shown only for music on ATtiny88 and defaults to the existing 8-MHz images',async()=>{
  const app=await playerApp({speech:false});
  assert.equal(app.get('board-control').hidden,true);
  await change(app,'device-select','attiny88');
  assert.equal(app.get('board-control').hidden,false);
  assert.equal(app.get('board-select').value,'bare-8mhz');
  assert.equal(init(app).entry.cpuHz,8000000);
  assert.equal(init(app).entry.firmwareEngine,'UM88');
  assert.equal(init(app).entry.synthesisHz,7812.5);
  assert.equal(init(app).entry.flashHex,eight.entries.find(e=>e.id===eight.defaultId).flashHex);
  assert.equal(app.get('board-upload').hidden,true);
  assert.equal(app.location.searchParams.has('board'),false);
});

test('a 16-MHz board link loads the actual USB firmware, clock, board pins and one-file download',async()=>{
  const app=await playerApp({speech:false,device:'attiny88',board,firmware:'children'});
  const expected=sixteen.entries.find(e=>e.id==='children'),message=init(app);
  assert.equal(app.get('board-select').value,board);
  assert.equal(message.engine,'wasm');assert.equal(message.entry.cpuHz,16000000);
  assert.equal(message.entry.flashHex,expected.flashHex);
  assert.notEqual(message.entry.flashHex,eight.entries.find(e=>e.id==='children').flashHex);
  assert.equal(message.entry.eepromHex,null);
  assert.equal(message.entry.firmwareEngine,'UM88');
  assert.equal(message.entry.synthesisHz,15625);
  assert.match(message.entry.source,/universal\/songs-micronucleus/);
  assert.match(app.get('machine-details').textContent,/16 МГц/);
  assert.match(app.get('tiny88-clock').textContent,/16 MHz.*MH-ET LIVE/);
  assert.match(app.get('right-output-label').textContent,/PB2.*D10/);
  assert.match(app.get('left-output-label').textContent,/PB1.*D9/);
  assert.equal(app.get('fuse-low').textContent,'—');
  assert.match(app.get('fuse-high-note').textContent,/сохранить фьюзы платы/);
  assert.match(app.get('fuse-clock-value').textContent,/Внешний генератор.*16 МГц/);
  assert.match(app.get('rom-details').textContent,/6012 Б приложения.*тембры во Flash.*62,5/);
  assert.equal(app.get('download').href,expected.source);
  assert.equal(app.get('download').download,'attiny88-mh-et-live-16mhz-children.hex');
  assert.equal(app.get('download-eeprom').hidden,true);
  assert.equal(app.get('board-upload').hidden,false);
  assert.equal(app.get('upload-command').textContent,'micronucleus --run attiny88-mh-et-live-16mhz-children.hex');
  assert.equal(new URL(app.fetches[0]).pathname.split('/').at(-1),'firmware-attiny88-16mhz.json');
  assert.equal(app.location.searchParams.get('board'),board);
});

test('changing frequency resets a playing transport, keeps its song and engine, and restores ISP metadata on return',async()=>{
  const app=await playerApp({speech:false,device:'attiny88',firmware:'alicia'});
  const js=app.radios.find(radio=>radio.value==='js');js.checked=true;await js.onchange();
  await app.get('play').onclick();app.position(48000*10);
  const previous=app.workers.at(-1);
  await change(app,'board-select',board);
  assert.equal(previous.terminated,true);assert.equal(init(app).entry.id,'alicia');
  assert.equal(init(app).engine,'js');assert.equal(init(app).entry.cpuHz,16000000);
  assert.equal(app.body.dataset.playing,'false');assert.equal(app.get('elapsed').textContent,'00:00.0');
  assert.equal(app.get('play').disabled,false);
  await change(app,'device-select','attiny13a');
  assert.equal(app.get('board-control').hidden,true);assert.equal(app.location.searchParams.has('board'),false);
  await change(app,'device-select','attiny88');
  assert.equal(app.get('board-select').value,board);assert.equal(init(app).entry.cpuHz,16000000);
  await change(app,'board-select','bare-8mhz');
  assert.equal(init(app).entry.cpuHz,8000000);assert.equal(init(app).entry.id,'alicia');
  assert.equal(init(app).entry.firmwareEngine,'UM88');
  assert.equal(app.get('download').download,'attiny88-alicia.hex');
  assert.equal(app.get('download-eeprom').hidden,true);
  assert.match(app.get('rom-details').textContent,/EEPROM не требуется/);
  assert.equal(app.get('fuse-low').textContent,'0xEE');assert.equal(app.get('board-upload').hidden,true);
  assert.equal(app.location.searchParams.has('board'),false);
});

test('a delayed board response cannot replace a newer 8-MHz selection',async()=>{
  const held=deferred();
  const app=await playerApp({speech:false,device:'attiny88',fetchHook:({url,response})=>
    url.pathname.endsWith('firmware-attiny88-16mhz.json')?held.promise.then(()=>response):undefined});
  app.get('board-select').value=board;const pending=app.get('board-select').onchange();await flush();
  await change(app,'board-select','bare-8mhz');
  held.resolve();await pending;await flush();
  assert.equal(app.get('board-select').value,'bare-8mhz');assert.equal(init(app).entry.cpuHz,8000000);
  assert.equal(app.location.searchParams.has('board'),false);
  assert.equal(app.get('error').hidden,true);
});

test('failed or mismatched board catalogs leave the working firmware and selection intact',async()=>{
  for(const mismatch of [false,true]){
    const app=await playerApp({speech:false,device:'attiny88',firmware:'greensleeves',fetchHook:({url})=>{
      if(url.pathname.endsWith('firmware-attiny88-16mhz.json'))return mismatch
        ?{ok:true,json:async()=>structuredClone(eight)}:{ok:false,status:503};
    }});
    const previous=app.workers.at(-1);await change(app,'board-select',board);
    assert.equal(previous.terminated,undefined);assert.equal(app.workers.at(-1),previous);
    assert.equal(app.get('board-select').value,'bare-8mhz');
    assert.equal(app.location.searchParams.has('board'),false);
    assert.equal(app.get('error').hidden,false);
    assert.match(app.get('error').textContent,mismatch?/Частота/:/503/);
    await app.get('play').onclick();assert.equal(app.body.dataset.playing,'true');
  }
});

test('unknown boards fall back to 8 MHz and speech never acquires the music board profile',async()=>{
  const unknown=await playerApp({speech:false,device:'attiny88',board:'unknown-board'});
  assert.equal(unknown.get('board-select').value,'bare-8mhz');assert.equal(init(unknown).entry.cpuHz,8000000);
  assert.equal(unknown.location.searchParams.has('board'),false);
  const speech=await playerApp({device:'attiny88',board,firmware:'hq4-vinni'});
  assert.equal(speech.get('device-select').value,'attiny13a');assert.equal(speech.get('board-control').hidden,true);
  assert.equal(init(speech).entry.board,undefined);assert.equal(init(speech).entry.id,'hq4-vinni');
  assert.match(speech.get('machine-details').textContent,/9,6 МГц/);
  assert.equal(speech.location.searchParams.has('board'),false);
});
