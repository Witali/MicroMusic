import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/greensleeves/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const score=JSON.parse(read('score.json')),report=JSON.parse(read('build-report.json'));
const codec=JSON.parse(read('compiled-score.json')),verified=JSON.parse(read('verification.json'));
const rom=read('synth.bin'),ep=read('eeprom.bin'),hash=b=>createHash('sha256').update(b).digest('hex');

test('Greensleeves retains every pitch and NoteOn/Off in all four source parts',()=>{
 const source=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/reference/greensleeves/greensleeves-4voices-events.json',import.meta.url)));
 const expected=[];
 for(const track of source.tracks){
  const active=new Map(),notes=[];
  for(const e of track.events){
   const key=e.channel*128+e.note;
   if(e.type==='noteOn'&&e.velocity){assert.ok(!active.has(key));active.set(key,e);}
   else if(e.type==='noteOff'||(e.type==='noteOn'&&!e.velocity)){
    const on=active.get(key);assert.ok(on);active.delete(key);
    notes.push({pitch:e.note,on:on.tick*4/source.ppqn,off:e.tick*4/source.ppqn,velocity:on.velocity});
   }
  }
  assert.equal(active.size,0);expected.push(notes.sort((a,b)=>a.on-b.on));
 }
 assert.deepEqual(score.parts.map(p=>p.notes.map(({pitch,on,off,velocity})=>({pitch,on,off,velocity}))),expected);
 assert.deepEqual(expected.map(p=>p.length),[70,52,58,55]);assert.equal(expected.flat().length,235);
 assert.equal(score.endUnit,192);assert.equal(score.meter,'6/8');assert.equal(score.pickup_beats,.5);assert.equal(score.loop_silence_beats,.25);
});

test('compact Flash grammar expands to every original independent event',()=>{
 const decoded=[];
 for(let at=report.labels.song_stream;rom[at]!==255;at++){
  const pending=[rom[at]];
  while(pending.length){const code=pending.pop();if(code<192)decoded.push(code);else{const a=report.labels.song_rules+2*(code-192);pending.push(rom[a+1],rom[a]);}}
 }
 assert.deepEqual(decoded,codec.commands);assert.equal(hash(Buffer.from(decoded)),codec.decodedCommandsSha256);
 const notes=score.parts.map(()=>[]),active=score.parts.map(()=>null);let unit=0;
 for(const code of decoded){
  if(code>=128){unit+=code-127;continue;}
  const part=code>>5,index=code&31;
  if(index){assert.equal(active[part],null);active[part]={pitch:codec.pitches[index-1],on:unit};}
  else{assert.ok(active[part]);notes[part].push({...active[part],off:unit});active[part]=null;}
 }
 assert.deepEqual(notes,score.parts.map(p=>p.notes.map(({pitch,on,off})=>({pitch,on,off}))));assert.equal(unit,193);
});

test('four measured instrument banks include the restored clarinet',()=>{
 const raw=readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)),bank=JSON.parse(raw);
 assert.equal(hash(raw),report.instrumentBankSha256);
 assert.deepEqual(score.parts.map(p=>p.instrument),['flute','violin','clarinet','cello']);
 assert.deepEqual(Object.values(report.instrumentAssignments).map(p=>p.gmProgram),[73,40,71,42]);
 for(let part=0;part<4;part++)for(const [register,offset] of [['low',0],['high',8]])for(let i=0;i<16;i++)
  assert.equal(((ep[16*part+offset+(i>>1)]>>(i%2?4:0))&15)-8,bank.instruments[score.parts[part].instrument].waves[register][i]);
 assert.equal(report.labels.render_drum,undefined);
});

test('pinned full-loop audit verifies every source note, physical PWM and bounds',()=>{
 assert.equal(hash(rom),verified.flashSha256);assert.equal(hash(ep),verified.eepromSha256);
 assert.equal(report.flashBytes,812);assert.equal(rom.length,812);assert.equal(ep.length,64);
 assert.equal(verified.allSourceNotesRetained,true);assert.equal(verified.playedNotes,235);assert.equal(verified.firstPassEvents,470);
 assert.equal(verified.musicSeconds,48);assert.ok(verified.loopSeconds>48.25&&verified.loopSeconds<48.28);
 assert.equal(verified.mixChecks,verified.pwmPairChecks);assert.ok(verified.mixChecks>900000);
 assert.equal(verified.ringUnderruns+verified.lostTimerEvents+verified.lostWorkEvents,0);
 assert.ok(verified.sramUsedWorstCase<=64);assert.ok(verified.maxRenderElapsedCycles<512);assert.ok(verified.maxTimingErrorMs<20);
 assert.deepEqual(verified.pwmRange,[0,237]);
 const level=JSON.parse(read('preview-level.json'));assert.equal(level.flashSha256,hash(rom));assert.equal(level.wavSha256,hash(read('preview.wav')));assert.equal(level.seconds,49);assert.equal(level.normalized,true);
});

test('the four instruments attack independently in the actual AVR',()=>{
 const c=new AVRCore(rom,ep);while(c.cyc<.3*9600000)c.nextDuty();
 assert.deepEqual(report.voices.voiceAddresses.map(a=>c.data[a]&15),[15,12,11,10]);
 assert.equal(c.lost+c.workLost,0);assert.equal(c.maxIRQ,15);
});


test('normalization covers every waveform/envelope combination in every loop',()=>{
 let minimum=0,maximum=0;
 for(let part=0;part<4;part++){
  const samples=[...ep.subarray(16*part,16*(part+1))].flatMap(b=>[(b&15)-8,(b>>4)-8]);
  const values=samples.flatMap(value=>Array.from({length:score.parts[part].level+1},(_,level)=>Math.floor(value*level/8)));
  minimum+=Math.min(...values);maximum+=Math.max(...values);
 }
 const norm=report.outputNormalization;
 assert.deepEqual([minimum,maximum],[-33,30]);assert.equal(norm.minimum,minimum);assert.equal(norm.maximum,maximum);
 assert.equal(norm.gain,128/33);assert.equal(norm.table.length,64);assert.equal(norm.table[-minimum],128);
 for(let mix=minimum;mix<=maximum;mix++){
  const output=Math.round(128+mix*norm.gain);assert.ok(output>=0&&output<=255);
  assert.equal(rom[report.labels.output_gain+mix-minimum],output);
 }
 assert.equal(norm.observedMinimum,-33);assert.equal(norm.observedMaximum,28);
});
