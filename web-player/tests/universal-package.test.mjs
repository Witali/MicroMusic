import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {universalPackageEntry} from '../lib/universal-package.js';
import {createRenderer} from '../lib/engines.js';
import {deferred,playerApp} from './helpers/player-app.mjs';
const text=readFileSync(new URL('../../ATtiny88/Music/universal/examples/mono-study/generated/player-package.json',import.meta.url),'utf8');
const original=JSON.parse(text);
const init=app=>app.workers.at(-1).messages.find(m=>m.type==='init');
const eventFor=value=>({target:{files:[{name:'player-package.json',size:value.length,text:async()=>value}],value:'selected'}});

test('verified mono package identifies its actual clock, image and optional EEPROM',async()=>{
 const entry=await universalPackageEntry(text);
 assert.equal(entry.device,'attiny88');assert.equal(entry.voices,5);assert.equal(entry.audioChannels,1);
 assert.equal(entry.cpuHz,8000000);assert.equal(entry.synthesisHz,7812.5);
 assert.equal(entry.eepromBytes,0);assert.equal(entry.eepromRequired,false);assert.equal(entry.eepromHex,undefined);
 assert.equal(entry.flashSha256,original.verification.flashSha256);
 assert.equal(entry.verification.allPwmFramesMatch,true);assert.ok(original.notices.length>=2);
});
for(const [label,mutate,pattern] of [
 ['score changed',p=>p.score.commands[0]^=1,/score SHA/],
 ['audit missing',p=>delete p.verification,/audit/],
 ['lost IRQ',p=>p.verification.lostInterrupts=1,/real-time/],
 ['underrun',p=>p.verification.fifoUnderruns=1,/real-time/],
 ['stale firmware',p=>p.build.flashSha256='0'.repeat(64),/SHA/],
 ['clock mismatch',p=>p.build.cpuHz=12000000,/Clock/],
 ['incomplete output audit',p=>p.verification.allPwmFramesMatch=false,/audit/],
 ['clipping',p=>p.verification.clippedChannelSamples=1,/clipping/],
 ['stereo input',p=>p.score.channels=2,/mono/],
])test('package rejects '+label,async()=>{
 const pkg=structuredClone(original);mutate(pkg);await assert.rejects(universalPackageEntry(pkg),pattern);
});
test('JS and WASM execute the same imported mono package without EEPROM',async()=>{
 const entry=await universalPackageEntry(text);
 const js=await createRenderer(entry,48000,{},'js'),wasm=await createRenderer(entry,48000,{},'wasm');
 let energy=0;
 for(let block=0;block<6;block++){
  const a=js.render(8192),b=wasm.render(8192);assert.equal(a.length,8192);
  for(let i=0;i<a.length;i++){assert.ok(Math.abs(a[i]-b[i])<1e-6);energy+=a[i]*a[i];}
 }
 assert.ok(energy>1);assert.equal(js.core.lost,0);assert.equal(wasm.core.lost,0);
});
test('imported description exposes arrangement omissions and unsupported events',async()=>{
 const pkg=structuredClone(original);
 pkg.arrangementReport.ignoredEvents={CC10:2};pkg.arrangementReport.omittedNotes=[{note:60}];
 const entry=await universalPackageEntry(pkg);
 assert.match(entry.description,/неподдержанных событий: 2/);assert.match(entry.description,/исключено нот: 1/);
});
test('app imports the UM88 package, resets playback and offers its actual HEX',async()=>{
 const app=await playerApp({speech:false,device:'attiny88'}),previous=app.workers.at(-1);
 await app.get('package-file').onchange(eventFor(text));
 assert.equal(previous.terminated,true);assert.equal(init(app).entry.kind,'universal');
 assert.equal(init(app).entry.audioChannels,1);assert.equal(app.get('stereo-output').hidden,true);
 assert.equal(app.get('download-eeprom').hidden,true);
 assert.match(app.get('rom-details').textContent,/EEPROM не требуется/);
 assert.match(app.get('download').href,/^data:text\/plain/);
 assert.equal(app.get('error').hidden,true);assert.match(app.get('selected-title').textContent,/mono study/);
});
test('app preserves current playback after an invalid import',async()=>{
 const app=await playerApp({speech:false,device:'attiny88'}),previous=app.workers.at(-1);
 const broken=structuredClone(original);broken.verification.passed=false;
 await app.get('package-file').onchange(eventFor(JSON.stringify(broken)));
 assert.equal(previous.terminated,undefined);assert.equal(app.workers.at(-1),previous);
 assert.equal(app.get('error').hidden,false);
});
test('12 MHz mono package updates clock labels without inventing board fuses',async()=>{
 const pkg=readFileSync(new URL('../../ATtiny88/Music/universal/examples/mono-study/profiles/12mhz/player-package.json',import.meta.url),'utf8');
 const entry=await universalPackageEntry(pkg);assert.equal(entry.cpuHz,12000000);assert.equal(entry.synthesisHz,11718.75);
 const app=await playerApp({speech:false,device:'attiny88'});
 await app.get('package-file').onchange(eventFor(pkg));
 assert.match(app.get('machine-details').textContent,/12 МГц/);
 assert.match(app.get('tiny88-clock').textContent,/12 MHz/);
 assert.equal(app.get('fuse-low').textContent,'—');
 assert.match(app.get('fuse-clock-note').textContent,/конфигурацией платы/);
});
test('switching chips while the file is being read discards the stale import',async()=>{
 const app=await playerApp({speech:false,device:'attiny88'}),pending=deferred(),event=eventFor(text);
 event.target.files[0].text=()=>pending.promise;
 const importing=app.get('package-file').onchange(event);
 app.get('device-select').value='attiny13a';await app.get('device-select').onchange();
 pending.resolve(text);await importing;
 assert.equal(app.get('device-select').value,'attiny13a');
 assert.equal(init(app).entry.device??'attiny13a','attiny13a');assert.notEqual(init(app).entry.kind,'universal');
});
