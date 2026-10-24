import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {deferred,playerApp} from './helpers/player-app.mjs';

const flush=()=>new Promise(resolve=>setImmediate(resolve));
const tiny13=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
const tiny88=JSON.parse(readFileSync(new URL('../firmware-attiny88.json',import.meta.url)));
const init=app=>app.workers.at(-1).messages.find(message=>message.type==='init');
const engine=(app,value)=>app.radios.find(radio=>radio.value===value);
async function chooseDevice(app,value){
  app.get('device-select').value=value;
  await app.get('device-select').onchange();
  await flush();
}

test('music opens on ATtiny13A by default and retains the existing WASM choice',async()=>{
  const app=await playerApp({speech:false});
  assert.equal(app.get('device-select').value,'attiny13a');
  assert.equal(init(app).engine,'wasm');
  assert.equal(engine(app,'wasm').disabled,false);
  assert.equal(app.get('download').download,`attiny13a-${tiny13.defaultId}.hex`);
  assert.match(app.get('rom-details').textContent,/\/ 1024 Б Flash/);
  assert.equal(new URL(app.fetches[0]).pathname.split('/').at(-1),'firmware.json');
});

test('an ATtiny88 link loads the matching real firmware, retains WASM and changes download capacity',async()=>{
  const app=await playerApp({speech:false,device:'attiny88',firmware:'children'}),message=init(app);
  const expected=tiny88.entries.find(entry=>entry.id==='children');
  assert.equal(app.get('device-select').value,'attiny88');
  assert.equal(message.entry.device,'attiny88');assert.equal(message.entry.id,'children');
  assert.equal(message.entry.flashHex,expected.flashHex);assert.notEqual(message.entry.flashHex,tiny13.entries.find(entry=>entry.id==='children').flashHex);
  assert.equal(message.engine,'wasm');assert.equal(engine(app,'wasm').checked,true);
  assert.equal(engine(app,'js').checked,false);assert.equal(engine(app,'wasm').disabled,false);
  assert.equal(new URL(app.fetches[0]).pathname.split('/').at(-1),'firmware-attiny88.json');
  assert.equal(app.get('download').href,expected.source);
  assert.equal(app.get('download').download,'attiny88-children.hex');
  assert.equal(app.get('rom-name').download,'attiny88-children.hex');
  assert.equal(app.get('download-eeprom').href,expected.eepromSource);
  assert.equal(app.get('download-eeprom').download,'attiny88-children-eeprom.hex');
  assert.match(app.get('rom-details').textContent,/\/ 8192 Б Flash/);
  assert.equal(app.get('catalog').children.length,tiny88.entries.length);
});

test('device selection updates the physical pins, timer labels, memory and device-specific fuses',async()=>{
  const app=await playerApp({speech:false,firmware:'children'}),{get}=app;
  assert.equal(get('device-control').hidden,false);
  assert.equal(get('chip-attiny13a').hidden,false);assert.equal(get('chip-attiny88').hidden,true);
  assert.match(get('right-output-label').textContent,/PB1 \/ OC0B.*6/);
  assert.equal(get('fuse-low').textContent,'0x7A');assert.equal(get('fuse-high').textContent,'0xFF');
  assert.equal(get('fuse-extended').hidden,true);
  await chooseDevice(app,'attiny88');
  assert.equal(get('chip-attiny13a').hidden,true);assert.equal(get('chip-attiny88').hidden,false);
  assert.match(get('right-output-label').textContent,/PB2 \/ OC1B.*16/);
  assert.match(get('scope-left-label').textContent,/OCR1B/);
  assert.match(get('machine-memory').textContent,/8/);
  assert.match(get('machine-details').textContent,/512.*SRAM.*64.*EEPROM.*8/);
  assert.equal(get('fuse-low').textContent,'0xEE');assert.equal(get('fuse-high').textContent,'0xDF');
  assert.equal(get('fuse-extended').hidden,false);assert.equal(get('fuse-extended-value').textContent,'0xFF');
  assert.match(get('fuse-clock-value').textContent,/8.*МГц/);
  assert.match(get('fuse-datasheet').href,/doc8008\.pdf/);
  get('catalog').children.find(item=>item.children[0].dataset.firmware==='lumiere-stereo').children[0].onclick();await flush();
  assert.equal(get('stereo-output').hidden,false);
  assert.match(get('right-output-label').textContent,/R.*PB2 \/ OC1B.*16/);
  assert.match(get('left-output-label').textContent,/L.*PB1 \/ OC1A.*15/);
  assert.match(get('scope-left-label').textContent,/OCR1A/);assert.match(get('scope-right-label').textContent,/OCR1B/);
  await chooseDevice(app,'attiny13a');
  assert.equal(get('chip-attiny13a').hidden,false);assert.equal(get('chip-attiny88').hidden,true);
  assert.match(get('right-output-label').textContent,/R.*PB1 \/ OC0B.*6/);
  assert.match(get('left-output-label').textContent,/L.*PB0 \/ OC0A.*5/);
  assert.equal(get('fuse-low').textContent,'0x7A');assert.equal(get('fuse-high').textContent,'0xFF');
  assert.equal(get('fuse-extended').hidden,true);
});

test('switching a playing song keeps its ID, terminates its worker and resets transport and audio session',async()=>{
  const app=await playerApp({speech:false,firmware:'alicia'}),{get}=app;
  await get('play').onclick();app.position(48000*15);
  const previous=app.workers[0],connection=app.worklets[0].messages.findLast(message=>message.type==='connect');
  assert.notEqual(get('elapsed').textContent,'00:00.0');
  await chooseDevice(app,'attiny88');
  assert.equal(previous.terminated,true);assert.equal(app.workers.length,2);
  assert.equal(init(app).entry.id,'alicia');assert.equal(init(app).entry.device,'attiny88');
  assert.equal(app.body.dataset.playing,'false');assert.equal(get('elapsed').textContent,'00:00.0');
  assert.equal(get('play-label').textContent,'Слушать');assert.equal(get('play').disabled,false);
  assert.equal(app.location.searchParams.get('device'),'attiny88');
  assert.equal(app.location.searchParams.get('firmware'),'alicia');
  assert.ok(app.worklets[0].messages.some(message=>message.type==='disconnect'));
  const current=app.worklets[0].messages.findLast(message=>message.type==='connect');
  assert.notEqual(current.session,connection.session);
  previous.onmessage({data:{type:'error',message:'obsolete worker'}});
  assert.equal(get('error').hidden,true);
  await get('play').onclick();
  app.position(48000*40,{session:connection.session});assert.equal(get('elapsed').textContent,'00:00.0');
  app.position(48000);assert.notEqual(get('elapsed').textContent,'00:00.0');
});

test('switching back restores the ATtiny13A firmware, downloads and the user engine choice',async()=>{
  const app=await playerApp({speech:false,firmware:'rhythmic'});
  await chooseDevice(app,'attiny88');const previous=app.workers.at(-1);
  await chooseDevice(app,'attiny13a');
  assert.equal(previous.terminated,true);assert.equal(init(app).entry.id,'rhythmic');
  assert.equal(init(app).entry.flashHex,tiny13.entries.find(entry=>entry.id==='rhythmic').flashHex);
  assert.equal(init(app).engine,'wasm');assert.equal(engine(app,'wasm').disabled,false);
  assert.equal(app.get('download').download,'attiny13a-rhythmic.hex');
  assert.match(app.get('rom-details').textContent,/\/ 1024 Б Flash/);
  assert.notEqual(app.location.searchParams.get('device'),'attiny88');
  engine(app,'js').checked=true;engine(app,'js').onchange();await flush();
  assert.equal(init(app).engine,'js');
  await chooseDevice(app,'attiny88');await chooseDevice(app,'attiny13a');
  assert.equal(init(app).engine,'js');assert.equal(engine(app,'js').checked,true);
});

test('unknown devices use ATtiny13A and speech remains on ATtiny13A even with a Tiny88 URL',async()=>{
  const unknown=await playerApp({speech:false,device:'atmega88a'});
  assert.equal(unknown.get('device-select').value,'attiny13a');
  assert.equal(init(unknown).engine,'wasm');
  assert.equal(new URL(unknown.fetches[0]).pathname.split('/').at(-1),'firmware.json');
  const speech=await playerApp({device:'attiny88',firmware:'hq4-vinni'});
  assert.equal(init(speech).entry.id,'hq4-vinni');assert.equal(init(speech).engine,'wasm');
  assert.equal(speech.get('device-select').value,'attiny13a');
  assert.equal(speech.get('device-control').hidden,true);
  assert.equal(engine(speech,'wasm').disabled,false);
  assert.equal(new URL(speech.fetches[0]).pathname.split('/').at(-1),'hq4-firmware.json');
  assert.notEqual(speech.location.searchParams.get('device'),'attiny88');
});

test('the engine selected on either chip is retained when switching to the other chip',async()=>{
  const app=await playerApp({speech:false});
  await chooseDevice(app,'attiny88');
  engine(app,'js').checked=true;engine(app,'js').onchange();await flush();
  await chooseDevice(app,'attiny13a');assert.equal(init(app).engine,'js');
  await chooseDevice(app,'attiny88');assert.equal(init(app).engine,'js');
  engine(app,'wasm').checked=true;engine(app,'wasm').onchange();await flush();
  assert.equal(init(app).entry.device,'attiny88');assert.equal(init(app).engine,'wasm');
  await chooseDevice(app,'attiny13a');assert.equal(init(app).engine,'wasm');
  assert.equal(engine(app,'wasm').disabled,false);
});

test('a song absent from the new device falls back to that device catalog default',async()=>{
  const onlyDefault=structuredClone(tiny88);onlyDefault.entries=onlyDefault.entries.filter(entry=>entry.id===onlyDefault.defaultId);
  const app=await playerApp({speech:false,firmware:'children',catalogs:{'firmware-attiny88.json':onlyDefault}});
  await chooseDevice(app,'attiny88');
  assert.equal(init(app).entry.id,tiny88.defaultId);assert.equal(app.location.searchParams.get('firmware'),tiny88.defaultId);
  assert.equal(app.get('catalog').children.length,1);
});

test('a slow Tiny88 response cannot overwrite a later selection of ATtiny13A',async()=>{
  const held=deferred();
  const app=await playerApp({speech:false,firmware:'children',fetchHook:({url,response})=>url.pathname.endsWith('firmware-attiny88.json')?held.promise.then(()=>response):undefined});
  app.get('device-select').value='attiny88';const pending=app.get('device-select').onchange();await flush();
  await chooseDevice(app,'attiny13a');
  held.resolve();await pending;await flush();
  assert.equal(app.get('device-select').value,'attiny13a');assert.notEqual(app.location.searchParams.get('device'),'attiny88');
  assert.equal(init(app).entry.flashHex,tiny13.entries.find(entry=>entry.id==='children').flashHex);
  assert.equal(init(app).engine,'wasm');assert.equal(app.get('error').hidden,true);
  assert.ok(app.workers.every(worker=>worker.messages.find(message=>message.type==='init').entry.device!=='attiny88'));
});

test('a failed device catalog leaves the previous runtime and selection usable and reports the load error',async()=>{
  const app=await playerApp({speech:false,firmware:'greensleeves',fetchHook:({url})=>url.pathname.endsWith('firmware-attiny88.json')?{ok:false,status:503}:undefined});
  const previous=app.workers[0];await chooseDevice(app,'attiny88');
  assert.notEqual(previous.terminated,true);assert.equal(app.workers.length,1);
  assert.equal(app.get('device-select').value,'attiny13a');assert.notEqual(app.location.searchParams.get('device'),'attiny88');
  assert.equal(app.get('download').download,'attiny13a-greensleeves.hex');
  assert.equal(app.get('error').hidden,false);assert.match(app.get('error').textContent,/503/);
  assert.equal(app.get('play').disabled,false);await app.get('play').onclick();
  assert.equal(app.body.dataset.playing,'true');
});

test('switching devices cancels autoplay still waiting for AudioWorklet initialization',async()=>{
  const app=await playerApp({speech:false,holdWorklet:true});
  const pending=app.get('play').onclick();await chooseDevice(app,'attiny88');
  app.workletSetup.resolve();await pending;await flush();
  assert.equal(init(app).entry.device,'attiny88');assert.equal(app.body.dataset.playing,'false');
  assert.equal(app.get('elapsed').textContent,'00:00.0');assert.equal(app.get('play').disabled,false);
  assert.ok(app.worklets.every(node=>node.messages.every(message=>message.type!=='playing'||message.value===false)));
});
