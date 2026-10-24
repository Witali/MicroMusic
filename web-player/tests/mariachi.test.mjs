import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';

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
    else if(active.get(key)?.length){const start=active.get(key).shift(),offset=58*480;result.push({pitch:e.note,start:(start-offset)/80,end:(e.tick-offset)/80,id:result.length});}
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

test('Mariachi starts at the theme without the intro and preserves the selected source melody and triplets',()=>{
  assert.equal(createHash('sha256').update(raw).digest('hex'),score.source.sha256);
  assert.equal(source.source.sha256,'d4ecee581603b3cac662fceb0d333289e17a635f4e7f998b0da548b6c85c90b7');
  assert.equal(source.tracks.reduce((n,t)=>n+t.summary.noteOnCount,0),4237);
  assert.equal(score.source.firstSourceQuarterBeat,58);
  assert.equal(score.source.lastSourceQuarterBeat,121);
  const stop=(121-58)*6,lead=notes(0),expected=[];let previous;
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
  assert.deepEqual(actual[0],{unit:0,pitch:71});
  assert.equal(actual.at(-2).pitch,64);
  assert.equal(score.tempo_bpm,1.5*score.musicalTempoBpm);
  assert.ok(Math.abs(units/4*60/score.tempo_bpm-31.7460317)<.00001);
});

test('Mariachi adds piano, alternating bass and measured percussion while keeping the nylon lead',()=>{
  const guitar=notes(1),{events}=stream();
  const commands=events.filter(e=>e.token>=224&&e.token<240);
  for(const {token,unit} of commands){
    assert.equal(unit%6,0);
    const active=guitar.filter(n=>n.start<=unit&&unit<n.end).map(n=>n.pitch);
    const chord=report.score.chords[token&15];
    const voicing=report.score.chord_notes[chord];
    if(active.length>0)for(const note of voicing)assert.ok(active.some(p=>p%12===note%12),'New voicing belongs to source harmony');
    assert.ok(voicing[0]>voicing[1],'Piano and bass occupy separate registers');
  }
  assert.ok(commands.length>40);
  const bank=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)));
  const profiles=['acoustic-guitar-nylon','acoustic-grand-piano-soft','fretless-bass'];
  for(const [i,role] of ['lead','keys','pluck'].entries()){
    const profile=bank.instruments[profiles[i]];
    assert.equal(report.instrumentAssignments[role].gmProgram,[24,0,35][i]);
    for(const [j,register] of ['low','high'].entries()){
      const decoded=Array.from(ep.subarray(i*16+j*8,i*16+j*8+8)).flatMap(b=>[(b&15)-8,(b>>4)-8]);
      assert.deepEqual(decoded,profile.waves[register]);
    }
  }
  assert.deepEqual(['lead','keys','pluck'].map(r=>report.instrumentAssignments[r].level),[15,7,10]);
  assert.equal(report.instrumentAssignments.percussion.enabled,true);
  assert.equal(report.percussionProfile.attenuationShift,2);
  assert.equal(report.releaseChannels.tailSlots,2);
  assert.ok(rom.length<=1024);assert.equal(ep.length,64);
});

test('Mariachi drums follow musical half beats and restart only when the first phrase is selected',()=>{
  const core=new AVRCore(rom,ep),hits=[];
  while(core.cyc<9600000*2){
    if(!core.inIRQ&&core.pc===report.labels.drum_trigger/2&&!(core.r[20]&128))hits.push({type:core.r[19],cycle:core.cyc});
    core.step();
  }
  assert.deepEqual(hits.slice(0,8).map(h=>h.type),[0,2,4,6,0,2,4,6]);
  for(let i=1;i<hits.length;i++)assert.ok(Math.abs((hits[i].cycle-hits[i-1].cycle)/9600000-60/126/2)<.014);
  for(const index of [0,report.labels.PLAYLIST_LEN-1]){
    const c=new AVRCore(rom,ep,{fastIdle:false});c.pc=report.labels.next_section/2;c.r[4]=index;
    c.r[19]=6;c.r[8]=2;c.r[20]=132;c.r[14]=201;
    let count=0;while(c.pc!==report.labels.read_event/2){c.step();assert.ok(++count<50);}
    assert.equal(c.r[30]|c.r[31]<<8,report.labels.melody_data+rom[report.labels.playlist+index],'The drum reset preserves the phrase offset');
    assert.deepEqual([c.r[19],c.r[8],c.r[20],c.r[14]],index===0?[0,3,0,167]:[6,2,132,201]);
  }
});
