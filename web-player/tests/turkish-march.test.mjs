import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/turkish-march/',import.meta.url),read=n=>readFileSync(new URL(n,base));
const report=JSON.parse(read('build-report.json')),score=JSON.parse(read('score.json'));
const rom=read('synth.bin'),ep=read('eeprom.bin'),hash=b=>createHash('sha256').update(b).digest('hex');
function commands(){const out=[];let unit=0;for(const name of report.score.playlist){let at=report.labels['section_'+name];for(;;){const byte=rom[at++];if(byte===255)break;out.push({byte,unit});if(byte<224)unit+=report.score.durations[byte&7];}}return out;}
function sourceNotes(){
 const source=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/reference/turkish-march/source-events.json',import.meta.url))),notes=[];
 for(const {index:track,events} of source.tracks){const active=new Map();for(const e of events){const key=e.channel*128+e.note;
  if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push(e);active.set(key,q);}
  else if(e.type==='noteOff'||(e.type==='noteOn'&&!e.velocity)){const on=active.get(key)?.shift();if(on)notes.push({track,pitch:e.note,on:on.tick,off:e.tick});}
 }}return {notes,ppqn:source.ppqn};
}
const midiName=name=>{const [,note,octave]=/^([A-G]#?)(-?\d+)$/.exec(name);return(Number(octave)+1)*12+['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'].indexOf(note);};

test('expanded Turkish March retains the recognizable opening and original pickup',()=>{
 const c=new AVRCore(rom,ep),notes=[],run=c.step.bind(c);
 c.step=()=>{if(!c.inIRQ&&c.pc===report.labels.lead_commit/2)notes.push({pitch:c.data[99]|c.data[100]<<8,cycle:c.cyc});run();};
 while(notes.length<9&&c.cyc<3*9600000)c.nextDuty();
 assert.deepEqual(notes.slice(0,9).map(n=>n.pitch&32767),[65,63,62,63,66,68,66,65,66].map(n=>Math.round(440*2**((n-69)/12)*65536/18750)));
 assert.ok(notes[0].cycle/9600000>.39&&notes[0].cycle/9600000<.43);assert.equal(c.lost+c.workLost,0);
});

test('every right-hand source grid cell and repeated selected attack survives the extension',()=>{
 const {notes,ppqn}=sourceNotes(),even=x=>{const f=Math.floor(x);return x-f===.5?f+(f%2):Math.round(x);};
 const source=notes.filter(n=>n.track===1).map((n,id)=>({...n,id,on:even(n.on*4/ppqn),off:Math.max(even(n.on*4/ppqn)+1,even(n.off*4/ppqn))}));
 const end=score.arrangement.sourceQuarterBeats*4,expected=[];let prior=null;
 for(let unit=0;unit<end;unit++){const n=source.filter(n=>n.on<=unit&&unit<n.off).sort((a,b)=>b.pitch-a.pitch||b.on-a.on)[0];expected.push({pitch:n?.pitch??null,attack:Boolean(n)&&n.id!==prior});prior=n?.id??null;}
 let pitch=null;
 for(const e of commands()){if(e.unit>=end||e.byte>=224)continue;const index=e.byte>>3;
  if(index===report.score.rest_index)pitch=null;else if(index!==report.score.hold_index)pitch=midiName(report.score.pitches[index]);
  assert.equal(index!==report.score.rest_index&&index!==report.score.hold_index,expected[e.unit].attack);
  for(let unit=e.unit;unit<e.unit+report.score.durations[e.byte&7];unit++)assert.equal(pitch,expected[unit].pitch);
 }
 assert.equal(score.arrangement.sourceBars2_4,74);assert.equal(score.arrangement.sourceQuarterBeats,148);
});

test('restored inner piano tones share genuine source attacks and NoteOffs with the selected bass',()=>{
 const {notes,ppqn}=sourceNotes();let restored=0;
 for(const n of score.left_hand_note_events){
  const bass=notes.find(s=>s.track===2&&s.pitch===n.pitch&&s.on===n.sourceOnTicks&&s.off===n.sourceOffTicks);assert.ok(bass);
  assert.ok(n.onUnit*ppqn/4>=bass.on);assert.ok(n.offUnit*ppqn/4<=bass.off);
  const choices=notes.filter(s=>s.track===2&&s.on===bass.on&&s.off===bass.off&&s.pitch>bass.pitch).sort((a,b)=>a.pitch-b.pitch);
  assert.equal(n.secondPitch,choices[0]?.pitch??null);if(n.secondPitch!==null)restored++;
 }
 assert.equal(restored,37);assert.equal(score.arrangement.restoredSecondChordNotes,37);
 assert.equal(report.channels.tonalVoices,3);assert.equal(report.channels.tailSlots,0);
 const inner=score.instruments.pluck;assert.equal(inner.instrument,'acoustic-grand-piano');assert.equal(inner.level,9);
});

test('all three voices use measured piano waves and the common attack bank',()=>{
 const bank=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url))).instruments['acoustic-grand-piano'];
 for(const offset of [0,16,32])for(const [register,extra] of [['low',0],['high',8]])for(let i=0;i<16;i++)assert.equal(((ep[offset+extra+(i>>1)]>>(i%2?4:0))&15)-8,bank.waves[register][i]);
 for(const [register,offset] of [['low',48],['high',56]])for(let i=0;i<16;i++)assert.equal(((ep[offset+(i>>1)]>>(i%2?4:0))&15)-8,bank.transient.waves[register][i]);
 assert.equal(report.labels.capture_ram_tail,undefined);assert.equal(report.labels.render_drum,undefined);
});

test('full-cycle AVR audit pins every command, restored note, PWM pair and memory bound',()=>{
 const verified=JSON.parse(read('verification.json'));assert.equal(hash(rom),verified.flashSha256);assert.equal(hash(ep),verified.eepromSha256);
 assert.equal(rom.length,1016);assert.ok(verified.musicSeconds>60.39&&verified.musicSeconds<60.40);
 assert.equal(verified.restoredSecondChordNotes,37);assert.equal(verified.sourceSelectedVoicingsVerified,true);
 assert.equal(verified.mixChecks,verified.pwmPairChecks);assert.ok(verified.mixChecks>1100000);
 assert.equal(verified.ringUnderruns+verified.lostTimerEvents+verified.lostWorkEvents,0);assert.ok(verified.sramUsedWorstCase<=64);assert.ok(verified.maxRenderElapsedCycles<512);assert.ok(verified.maximumTimingErrorMs<25);
 const level=JSON.parse(read('preview-level.json'));assert.equal(level.normalized,true);assert.equal(level.seconds,61);assert.equal(level.flashSha256,hash(rom));assert.equal(level.wavSha256,hash(read('preview.wav')));
});
