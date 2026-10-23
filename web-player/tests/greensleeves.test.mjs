import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';

const base=new URL('../../ATtiny13A/Music/variants/greensleeves/',import.meta.url);
const reference=new URL('../../ATtiny13A/Music/reference/greensleeves/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const rom=read('synth.bin'),ep=read('eeprom.bin');
const report=JSON.parse(read('build-report.json')),score=JSON.parse(read('score.json'));
const {labels}=report;
const voices=report.releaseChannels.voiceAddresses;
const units=[1,2,3,4,6,8,16];

test('Greensleeves retains the complete written melody and familiar opening from the Z80 example',()=>{
  for(const [name,hash] of Object.entries(score.provenance.sha256))
    assert.equal(createHash('sha256').update(readFileSync(new URL(name,reference))).digest('hex'),hash);
  const source=readFileSync(new URL('greensleeves.ly',reference),'utf8')
    .split('Soprano =')[1].split('Alto =')[0].split('\\key g \\major')[1].split('\\bar')[0];
  const expected=[];let length=8,position=0;
  for(const match of source.matchAll(/(?<![a-z])([a-g](?:is|es)?|[rs])([',]*)(\d+)?(\.)?/g)){
    const [,note,octave,duration,dot]=match;length=duration?Number(duration):length;
    const count=16/length*(dot?1.5:1);
    const pitch=(note==='r'||note==='s')?null:48+{c:0,d:2,e:4,f:5,g:7,a:9,b:11}[note[0]]
      +Number(note.endsWith('is'))-Number(note.endsWith('es'))
      +12*([...octave].filter(x=>x==="'").length-[...octave].filter(x=>x===',').length);
    if(note!=='s')expected.push({pitch,start:position,units:count});
    position+=count;
  }
  const midiPitch=name=>{const [,letter,accidental,octave]=name.match(/^([A-G])([#b]?)(-?\d+)$/);
    return (Number(octave)+1)*12+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[letter]+(accidental==='#'?1:accidental==='b'?-1:0);};
  const actual=[];position=0;
  for(const section of report.score.playlist){
    let address=labels[`section_${section}`];
    for(;;){const token=rom[address++];if(token===255)break;if(token>=224)continue;
      const index=token>>3,count=units[token&7];
      if(index===report.score.hold_index)actual.at(-1).units+=count;
      else actual.push({pitch:index===report.score.rest_index?null:midiPitch(report.score.pitches[index]),start:position,units:count});
      position+=count;
    }
  }
  assert.deepEqual(actual,expected.concat({pitch:null,start:192,units:1}));
  assert.deepEqual(actual.slice(0,5).map(n=>n.pitch),[64,67,69,71,72]);
  assert.equal(position,193);assert.equal((position-1)%12,0,'Written closing bar plus pickup remain in 6/8; loop gap is outside the meter');
  assert.equal(actual.filter(n=>n.pitch!==null).length,71);
  assert.equal(score.meter,'6/8');assert.equal(score.pickup_beats,.5);
  assert.equal(score.title,'05 · Greensleeves');assert.equal(score.loop_silence_beats,.25);
  assert.equal(rom.length,report.flashBytes);assert.ok(rom.length<=1024);
});

test('selected Alto and Bass notes receive their real written note-offs and no harmony restarts them in rests',()=>{
  const lily=readFileSync(new URL('greensleeves.ly',reference),'utf8');
  function part(name,next){
    const text=lily.split(name+' =')[1].split(next)[0].split('\\key g \\major')[1].split('\\bar')[0];
    const events=[];let length=8,position=0;
    for(const match of text.matchAll(/(?<![a-z])([a-g](?:is|es)?|[rs])([',]*)(\d+)?(\.)?/g)){
      const [,note,octave,duration,dot]=match;length=duration?Number(duration):length;
      const count=16/length*(dot?1.5:1),pitch=(note==='r'||note==='s')?null:48+{c:0,d:2,e:4,f:5,g:7,a:9,b:11}[note[0]]
        +Number(note.endsWith('is'))-Number(note.endsWith('es'))+12*([...octave].filter(x=>x==="'").length-[...octave].filter(x=>x===',').length);
      events.push({pitch,start:position,end:position+count});position+=count;
    }
    return events;
  }
  const written={keys:part('Alto','Tenor ='),pluck:part('Bass','\\score')};
  const points=[0];for(let start=2;start<192;start+=12)points.push(start,Math.min(start+6,191));
  const stream=[];let unit=0;
  for(const section of report.score.playlist){
    let address=labels['section_'+section];
    for(;;){const token=rom[address++];if(token===255)break;stream.push({token,unit});if(token<224)unit+=units[token&7];}
  }
  const chords=stream.filter(e=>e.token>=224&&e.token<240);
  assert.deepEqual(chords.map(e=>e.unit),points,'Only selected source onsets generate harmony commands');
  for(const [role,index,mask] of [['keys',0,2],['pluck',1,4]]){
    const expected=points.map(point=>{const note=written[role].find(e=>e.start<=point&&point<e.end);return {pitch:note.pitch,start:point,end:note.end};});
    assert.equal(expected.length,33);
    assert.deepEqual(score.adaptation.selected_accompaniment[role].map(({pitch,start,end})=>({pitch,start,end})),expected);
    assert.deepEqual(chords.map(e=>({pitch:score.chord_notes[report.score.chords[e.token&15]][index],start:e.unit})),expected.map(({pitch,start})=>({pitch,start})));
    const offs=stream.filter(e=>e.token>=240&&Boolean(e.token&mask));
    assert.deepEqual(offs.map(e=>e.unit),expected.map(e=>e.end),'Every selected note ends at its own source boundary');
    for(let i=0;i<expected.length;i++)assert.ok(expected[i].end<=(expected[i+1]?.start??192));
  }
  assert.ok(stream.some(e=>e.unit===192&&e.token===247),'All three voices receive final Note Off before the separate gap');
  assert.equal(unit,193);
});

test('all three envelopes are silent before the first note of the next loop',()=>{
  const c=new AVRCore(rom,ep);let zeroAtRestart=false,commands=0;
  const totalCommands=report.score.compression.originalCommandBytes+report.score.playlist.length;
  const step=c.step.bind(c);
  c.step=()=>{
    if(!c.inIRQ&&c.pc===labels.read_event/2){
      if(commands===totalCommands){
        assert.deepEqual(voices.map(a=>c.data[a]&143),[0,0,0,0,0],'A new cycle begins after all primary and release envelopes have finished');
        zeroAtRestart=true;
      }
      commands++;
    }
    step();
  };
  while(!zeroAtRestart&&c.cyc<50*9600000)c.nextDuty();
  assert.ok(zeroAtRestart,'Ran through a complete cycle and its 250-ms closing silence');
  assert.equal(c.lost+c.workLost,0);
});

test('the actual Z80 example assigns flute, violin, clarinet and cello, with no percussion',()=>{
  const source=JSON.parse(readFileSync(new URL('greensleeves-4voices-events.json',reference)));
  assert.equal(source.schema,'micromusic-midi-events');assert.equal(source.version,1);
  const programs=source.tracks.flatMap(track=>track.events.filter(e=>e.type==='programChange').map(e=>[e.channel,e.program]));
  assert.deepEqual(programs,[[0,73],[1,40],[2,71],[3,42]]);
  assert.deepEqual(score.instruments,{lead:{instrument:'flute',level:15},keys:{instrument:'violin',level:12},pluck:{instrument:'cello',level:10},percussion:'off'});
  assert.equal(score.percussion_enabled,false);
  assert.equal(labels.drum_trigger,undefined);assert.equal(labels.render_drum,undefined);
});

test('three instrument banks and independent Alto/Bass frequencies match the build-time assignments',()=>{
  const bankBytes=readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)),bank=JSON.parse(bankBytes);
  assert.equal(report.instrumentBankSha256,createHash('sha256').update(bankBytes).digest('hex'));
  assert.equal(score.engine,'instrument-bank');
  for(const [role,offset] of [['lead',0],['keys',16],['pluck',32]]){
    const instrument=bank.instruments[score.instruments[role].instrument];
    const model=role==='lead'?'lead_envelope_model':role==='keys'?'accompaniment_envelope_model':'pluck_envelope_model';
    assert.equal(score[model],instrument.envelope.model);
    assert.equal(score[`${role}_attack_step`],instrument.envelope.attackStep);
    assert.equal(score[`${role}_release_step`],instrument.envelope.releaseStep);
    assert.equal(score[`${role}_max_level`],score.instruments[role].level);
    for(const [register,extra] of [['low',0],['high',8]])for(let i=0;i<16;i++)
      assert.equal(((ep[offset+extra+(i>>1)]>>(i%2?4:0))&15)-8,instrument.waves[register][i]);
  }
  assert.equal(score.lead_envelope_model,'sustain');
  assert.equal(score.lead_release_model,'linear');
  assert.equal(report.articulation.attack,'sustain');
  assert.ok(ep.subarray(48).every(v=>v===0x88));
  const delta=n=>Math.round(440*2**((n-69)/12)*65536/18750);
  for(let chord=0;chord<report.score.chords.length;chord++){
    const pitches=score.chord_notes[report.score.chords[chord]],address=labels.chord_steps+chord*4;
    assert.equal(rom[address]|rom[address+1]<<8,delta(pitches[0]));
    assert.equal(rom[address+2]|rom[address+3]<<8,delta(pitches[1]));
  }
});

test('sustained accompaniment retains oscillator phases and attacks softly to its configured levels',()=>{
  const c=new AVRCore(rom,ep);c.pc=labels.chord_event/2;c.r[16]=224;
  c.data[voices[1]]=128|16|12;c.data[voices[2]]=128|32|10;
  c.data[voices[1]+1]=57;c.data[voices[1]+2]=48;c.data[voices[2]+1]=160;c.data[voices[2]+2]=91;
  while(c.pc!==labels.read_event/2)c.step();
  assert.equal(c.data[voices[1]+1]|c.data[voices[1]+2]<<8,12345);assert.equal(c.data[voices[2]+1]|c.data[voices[2]+2]<<8,23456);
  assert.equal(c.data[voices[1]],128|16|6);assert.equal(c.data[voices[2]],128|32|5);
  const caps=[score.lead_max_level,score.keys_max_level,score.pluck_max_level];
  for(const a of voices)c.data[a]=0;
  for(let i=0;i<3;i++)c.data[voices[i]]=128|i*16;
  for(let tick=0;tick<8;tick++){
    c.pc=labels.music_tick/2;
    while(c.pc!==labels['.L0a8']/2)c.step();
    for(let voice=0;voice<3;voice++)assert.equal(c.data[voices[voice]],128|voice*16|Math.min(caps[voice],(tick+1)*4));
    assert.equal(c.r[29],0);
  }
  // In particular, flute must use the bank's linear sustain release rather
  // than the historical violin-lead release that skipped levels above8.
  for(let voice=0;voice<3;voice++)c.data[voices[voice]]=voice*16|caps[voice];
  for(let tick=1;tick<=16;tick++){
    c.pc=labels.music_tick/2;
    while(c.pc!==labels['.L0a8']/2)c.step();
    for(let voice=0;voice<3;voice++)assert.equal(c.data[voices[voice]],voice*16|Math.max(0,caps[voice]-tick));
  }
});
