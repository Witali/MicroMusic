import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';

const base=new URL('../../ATtiny13A/Music/variants/alicia/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const sourceBytes=readFileSync(new URL('../../ATtiny13A/Music/reference/alicia/source-score.json',import.meta.url));
const source=JSON.parse(sourceBytes);
const timeline=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/reference/alicia/timeline.json',import.meta.url)));
const arrangement=JSON.parse(read('score.json'));
const report=JSON.parse(read('build-report.json'));
const gridBpm=arrangement.arrangement.encodingGridBpm;
const {labels}=report;
const voices=report.releaseChannels.voiceAddresses;
const stateWord=(c,a)=>c.data[a]|c.data[a+1]<<8;
const fraction=text=>{const [n,d=1]=String(text).split('/').map(Number);return n/d;};
const midi=name=>{
  if(name==='R')return null;
  const [,letter,accidental,octave]=/^([A-G])([#b]?)(-?\d+)$/.exec(name);
  return (Number(octave)+1)*12+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[letter]+(accidental==='#'?1:accidental==='b'?-1:0);
};

test('the complete Alicia source keeps every meter, tempo, octave choice and melody event',()=>{
  assert.equal(arrangement.source_score.sha256,createHash('sha256').update(sourceBytes).digest('hex'));
  const expected=[];let seconds=0;
  for(const [playlistIndex,name] of source.playlist.entries()){
    const pattern=source.patterns[name];
    for(const [barIndex,bar] of pattern.bars.entries()){
      let beats=0;
      for(const token of bar.melody.split(' ')){
        const [pitch,durationText]=token.split(':'),duration=fraction(durationText);
        const note=midi(pitch),transpose=bar.lead_transpose??pattern.lead_transpose??0;
        expected.push({playlistIndex,pattern:name,bar:barIndex,midi:note===null?null:note+transpose,
          start:seconds+beats*60/pattern.tempo_bpm,end:seconds+(beats+duration)*60/pattern.tempo_bpm});
        beats+=duration;
      }
      assert.ok(Math.abs(beats-(bar.beats??pattern.beats_per_bar))<1e-10);
      seconds+=beats*60/pattern.tempo_bpm;
    }
  }
  assert.equal(expected.length,194);assert.equal(expected.filter(e=>e.midi!==null).length,169);
  assert.equal(timeline.bars.length,55);assert.equal(timeline.events.length,expected.length);
  assert.deepEqual([...new Set(timeline.bars.map(b=>b.meter))].sort(),['3/4','4/4']);
  assert.deepEqual([...new Set(timeline.bars.map(b=>b.tempoBpm))].sort((a,b)=>a-b),[58,78,87]);
  for(let i=0;i<expected.length;i++){
    const actual=timeline.events[i],event=expected[i];
    assert.equal(actual.identity,i);assert.equal(actual.midi,event.midi);
    assert.equal(actual.playlistIndex,event.playlistIndex);assert.equal(actual.bar,event.bar);
    assert.ok(Math.abs(fraction(actual.startSeconds)-event.start)<1e-10);
    assert.ok(Math.abs(fraction(actual.endSeconds)-event.end)<1e-10);
    assert.equal(actual.gridStart,Math.round(event.start*gridBpm/15));
    assert.equal(actual.gridEnd,Math.round(event.end*gridBpm/15));
    assert.ok(actual.gridEnd>actual.gridStart,'No short source event disappears');
  }
  assert.ok(Math.abs(seconds-157.6392572944297)<1e-10);
  assert.ok(arrangement.arrangement.maximumQuantizationErrorMs<20);
  assert.equal(timeline.events[0].startSeconds,'0');
});

test('storage blocks preserve every quantized source cell and repeated note identity',()=>{
  const expected=[],actual=[],attacks=[];let previous=null,tied=false;
  for(const event of timeline.events)expected.push(...Array(event.gridEnd-event.gridStart).fill(event.midi));
  for(const name of arrangement.playlist)for(const bar of arrangement.patterns[name]){
    let total=0;
    for(const token of bar.split(' ')){
      const [pitch,text]=token.split(':'),duration=Number(text.replace(/~$/,'')),units=Math.round(duration*4),note=midi(pitch);
      if(note!==null&&!(tied&&previous===note))attacks.push([actual.length,note]);
      actual.push(...Array(units).fill(note));total+=units;
      previous=note;tied=text.endsWith('~');
    }
    assert.equal(total,16);
  }
  assert.deepEqual(actual.slice(0,expected.length),expected);
  assert.ok(actual.slice(expected.length).every(v=>v===null),'Only the closing silence is padded');
  assert.deepEqual(attacks,timeline.events.filter(e=>e.midi!==null).map(e=>[e.gridStart,e.midi]));
  assert.equal(attacks.length,169);
  assert.equal(actual.length,3664);assert.equal(expected.length,3657);
});

test('the real AVR starts at the recognizable piano introduction on source beat zero',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),attacks=[];
  const step=c.step.bind(c);
  c.step=()=>{
    if(!c.inIRQ&&c.pc===labels.lead_commit/2)attacks.push({delta:stateWord(c,voices[0]+3)&32767,cycles:c.cyc});
    step();
  };
  while(attacks.length<12&&c.cyc<11*9600000)c.nextDuty();
  const first=timeline.events.filter(e=>e.midi!==null).slice(0,12);
  assert.deepEqual(first.map(e=>e.midi),[72,67,65,72,70,63,67,65,56,63,62,55]);
  assert.deepEqual(attacks.map(e=>e.delta),first.map(e=>Math.round(440*2**((e.midi-69)/12)*65536/18750)));
  assert.ok(attacks[0].cycles/9600000<.03,'The piano opening is not skipped');
  const anchor=attacks[0].cycles;
  for(let i=0;i<attacks.length;i++)assert.ok(Math.abs((attacks[i].cycles-anchor)/9600000-first[i].gridStart*15/gridBpm)<.016);
  assert.equal(c.lost+c.workLost,0);
});

test('the static piano reduction uses the measured bank and contains no invented accompaniment',()=>{
  assert.equal(arrangement.engine,'instrument-bank');
  assert.deepEqual(arrangement.instruments,{lead:'acoustic-grand-piano-soft',keys:'off',pluck:'off',percussion:'off'});
  assert.equal(arrangement.lead_envelope_model,'piano');assert.equal(arrangement.lead_retrigger,'full');
  assert.equal(arrangement.lead_max_level,14);assert.equal(arrangement.percussion_enabled,false);
  assert.equal(labels.render_drum,undefined);assert.equal(labels.drum_trigger,undefined);
  const bankBytes=readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)),bank=JSON.parse(bankBytes);
  assert.equal(report.instrumentBankSha256,createHash('sha256').update(bankBytes).digest('hex'));
  const profile=bank.instruments['acoustic-grand-piano-soft'],ep=read('eeprom.bin');
  for(const [register,offset] of [['low',0],['high',8]])for(let i=0;i<16;i++)
    assert.equal(((ep[offset+(i>>1)]>>(4*(i%2)))&15)-8,profile.waves[register][i]);
  assert.ok(ep.subarray(16,48).every(v=>v===0x88),'Unused companion banks are silent');
  assert.equal(profile.transient.kind,'piano-attack');
  for(const [register,offset] of [['low',48],['high',56]])for(let i=0;i<16;i++)
    assert.equal(((ep[offset+(i>>1)]>>(4*(i%2)))&15)-8,profile.transient.waves[register][i]);
  assert.ok(report.flashBytes<=1024);assert.equal(report.flashBytes,read('synth.bin').length);
  assert.equal(report.flashSha256,createHash('sha256').update(read('synth.bin')).digest('hex'));
  assert.equal(report.score.compression.verifiedLossless,true);
});

test('high piano notes carry the build-time fast-decay tag and retain their actual pitch',()=>{
  const bank=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)));
  const settings=bank.instruments['acoustic-grand-piano-soft'].envelope.decayMaskByRegister;
  assert.equal(arrangement.dds_fast_decay_roles.lead,settings.thresholdMidi);
  assert.equal(arrangement.lead_decay_mask,settings.lowMask);
  assert.equal(arrangement.lead_fast_decay_mask,settings.highMask);
  const rom=read('synth.bin'),ep=read('eeprom.bin');
  for(const [index,name] of report.score.pitches.filter(n=>n!=='R').entries()){
    const pitch=midi(name),address=labels.note_steps+index*2,word=rom[address]|rom[address+1]<<8;
    const delta=Math.round(440*2**((pitch-69)/12)*65536/18750);
    assert.equal(word&32767,delta);assert.equal(Boolean(word&32768),pitch>=settings.thresholdMidi);
    const c=new AVRCore(rom,ep);c.pc=labels.melodic_event/2;c.r[16]=index<<3;
    c.r[30]=labels.first_section&255;c.r[31]=labels.first_section>>8;c.data[voices[0]+1]=0x34;c.data[voices[0]+2]=0x12;
    while(c.pc!==labels.hold_sample/2)c.step();
    assert.equal(stateWord(c,voices[0]+3),word,'The DDS metadata tag is retained in voice state');
    assert.equal(c.data[voices[0]],128|64|14);
    assert.equal(stateWord(c,voices[0]+1),0x1234);
    if(pitch>=settings.thresholdMidi){
      c.r[24]=0;c.pc=labels.music_tick/2;
      while(c.pc!==labels['.L0a8']/2)c.step();
      assert.equal(c.data[voices[0]]&15,13,'High-register piano starts its faster decay on the next envelope tick');
    }
  }
});

test('the final source rest finishes the piano envelope before the next cycle begins',()=>{
  const last=timeline.events.at(-1);
  assert.equal(last.midi,null);assert.ok(fraction(last.endSeconds)-fraction(last.startSeconds)>4);
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
  const total=report.score.compression.originalCommandBytes+report.score.playlist.length;
  let commands=0,cleanRestart=false;const step=c.step.bind(c);
  c.step=()=>{
    if(!c.inIRQ&&c.pc===labels.read_event/2){
      if(commands===total){assert.deepEqual(voices.map(a=>c.data[a]&143),[0,0,0,0,0]);cleanRestart=true;}
      commands++;
    }
    step();
  };
  while(!cleanRestart&&c.cyc<160*9600000)c.nextDuty();
  assert.ok(cleanRestart,'The whole source melody ends and restarts with zero voice levels');
  assert.equal(c.lost+c.workLost,0);
});
