import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const base=new URL('../../ATtiny13A/Music/variants/cancion-del-mariachi/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const rom=read('synth.bin'),ep=read('eeprom.bin');
const score=JSON.parse(read('score.json')),report=JSON.parse(read('build-report.json'));
const raw=readFileSync(new URL(score.source.file,base));
const source=JSON.parse(raw),steps=[1,2,3,4,6,8,16];
const pitch=name=>name==='R'?null:12*(Number(name.at(-1))+1)+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[name[0]]+Number(name.includes('#'));
function notes(track){
  const active=new Map(),result=[];
  for(const e of source.tracks[track].events){
    if(e.type!=='noteOn'&&e.type!=='noteOff')continue;
    const key=`${e.channel}:${e.note}`;
    if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push(e.tick);active.set(key,q);}
    else if(active.get(key)?.length){const start=active.get(key).shift();result.push({pitch:e.note,start:start/20,end:e.tick/20,id:result.length});}
  }
  return result;
}
function stream(){
  const events=[];let unit=0;
  for(const section of report.score.playlist){
    let at=report.labels['section_'+section];
    for(let token;(token=rom[at++])!==255;){events.push({token,unit});if(token<224)unit+=steps[token&7];}
  }
  return {events,units:unit};
}

test('Mariachi preserves the source melody, triplets and exact ornament boundaries through the E4 cadence',()=>{
  assert.equal(createHash('sha256').update(raw).digest('hex'),score.source.sha256);
  assert.equal(source.source.sha256,'d4ecee581603b3cac662fceb0d333289e17a635f4e7f998b0da548b6c85c90b7');
  assert.equal(source.tracks.reduce((n,t)=>n+t.summary.noteOnCount,0),4237);
  const stop=121*24,lead=notes(0),expected=[];let previous;
  for(let unit=0;unit<stop;unit++){
    const active=lead.filter(n=>n.start<=unit&&unit<n.end).sort((a,b)=>b.pitch-a.pitch||b.start-a.start);
    const selected=active[0];
    if(selected?.id!==previous?.id)expected.push({unit,pitch:selected?.pitch??null});
    previous=selected;
  }
  // Explicit final REST releases the cadence at its original NoteOff.
  expected.push({unit:stop,pitch:null});
  const {events,units}=stream(),actual=[];
  for(const {token,unit} of events){
    if(token>=224||token>>3===report.score.hold_index)continue;
    const value={unit,pitch:pitch(report.score.pitches[token>>3])};
    if(value.pitch!==null||actual.at(-1)?.pitch!==null)actual.push(value);
  }
  assert.deepEqual(actual,expected);
  assert.deepEqual(actual.slice(0,9).map(n=>n.pitch),[47,48,45,47,43,45,42,43,40]);
  assert.equal(actual.at(-2).pitch,64);
  assert.equal(score.tempo_bpm,6*score.musicalTempoBpm);
  assert.ok(Math.abs(units/4*60/score.tempo_bpm-58.095238)<.00001);
});

test('Mariachi accompaniment uses real guitar notes at quarter boundaries and measured nylon waveforms',()=>{
  const guitar=notes(1),{events}=stream();
  const commands=events.filter(e=>e.token>=224&&e.token<240);
  for(const {token,unit} of commands){
    assert.equal(unit%24,0);
    const active=guitar.filter(n=>n.start<=unit&&unit<n.end).map(n=>n.pitch);
    assert.ok(active.length>0);
    const chord=report.score.chords[token&15];
    assert.deepEqual(report.score.chord_notes[chord],[Math.max(...active),Math.min(...active)]);
  }
  assert.ok(commands.length>40);
  const bank=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)));
  const profile=bank.instruments['acoustic-guitar-nylon'];
  for(const [i,role] of ['lead','keys','pluck'].entries()){
    assert.equal(report.instrumentAssignments[role].gmProgram,24);
    assert.equal(report.instrumentAssignments[role].envelope.model,'pluck');
    for(const [j,register] of ['low','high'].entries()){
      const decoded=Array.from(ep.subarray(i*16+j*8,i*16+j*8+8)).flatMap(b=>[(b&15)-8,(b>>4)-8]);
      assert.deepEqual(decoded,profile.waves[register]);
    }
  }
  assert.deepEqual(['lead','keys','pluck'].map(r=>report.instrumentAssignments[r].level),[15,8,10]);
  assert.equal(report.releaseChannels.tailSlots,2);
  assert.ok(rom.length<=1024);assert.equal(ep.length,64);
});
