import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';

const folder=new URL('../../ATtiny13A/Music/variants/children/',import.meta.url);
const read=name=>fs.readFileSync(new URL(name,folder));
const report=JSON.parse(read('build-report.json')),{labels}=report;
const rom=read('synth.bin'),ep=read('eeprom.bin');
function tick(c){
 c.pc=labels.music_tick/2;
 let steps=0;
 do{c.step();assert.ok(++steps<300);}while(c.pc!==labels['.L0a8']/2);
}

test('Children has four main voices, two independent tails, and distinct measured GM0/35/50 banks',()=>{
 assert.equal(report.engine,'children-native');assert.equal(report.activePrimaryVoices,4);
 assert.equal(report.releaseChannels.tailSlots,2);
 assert.deepEqual(report.releaseChannels.voiceAddresses,[97,102,107,112,117,122]);
 assert.ok(rom.length<=1024);assert.equal(rom.length,report.flashBytes);assert.equal(ep.length,64);
 assert.deepEqual(report.primaryVoiceAssignments.map(v=>v.program),[0,0,35,50]);
 assert.deepEqual(report.primaryVoiceAssignments.map(v=>v.eeprom),[0,0,16,32]);
 assert.notDeepEqual(ep.subarray(0,16),ep.subarray(16,32));
 assert.notDeepEqual(ep.subarray(16,32),ep.subarray(32,48));
 assert.equal(report.native.metadata.sourceLeadNotes,256);assert.equal(report.native.metadata.sourceBassNotes,345);
 assert.equal(report.native.metadata.totalUnits,1728);
 assert.equal(report.score.compression.verifiedLossless,true);
 assert.match(report.native.metadata.limitation,/not an exact copy/);
});

test('Children measured strings attack/release masks and both tails reach zero without underflow',()=>{
 const c=new AVRCore(rom,ep,{fastIdle:false});
 c.data[112]=128|32;c.r[24]=0;
 const attack=Array.from({length:16},()=>{tick(c);return c.data[112]&15;});
 assert.deepEqual(attack,[0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,7]);
 for(const address of [112,117,122])c.data[address]=32|7;
 c.r[24]=0;
 for(let clock=1;clock<=64;clock++){
  tick(c);
  for(const address of [112,117,122])assert.equal(c.data[address]&15,Math.max(0,7-Math.floor(clock/8)));
 }
 c.data[97]=128|64|15;c.data[101]=128;c.r[24]=0;
 for(let i=0;i<6;i++)tick(c);
 assert.equal(c.data[97]&15,9,'High-register piano retains its fast measured first decay');
 c.data[97]=64|3;tick(c);assert.equal(c.data[97]&15,1);tick(c);assert.equal(c.data[97]&15,0);
});

test('Children fixed-cost signed amplitude renderer matches all256 nibble/level products',()=>{
 for(let wave=-8;wave<=7;wave++)for(let level=0;level<=15;level++){
  const c=new AVRCore(rom,ep,{fastIdle:false});
  c.eeprom.fill(((wave+8)<<4)|(wave+8));
  c.r[25]=128|64|level;c.r[26]=102;c.r[16]=0;c.r[17]=0x50;
  c.pushPC(0);c.pc=labels.render_tone/2;
  let steps=0;do{c.step();assert.ok(++steps<40);}while(c.pc!==0);
  const expected=Math.floor(wave*level/4)&255;
  assert.equal(c.r[17],expected,`wave${wave} level${level}`);
 }
});
