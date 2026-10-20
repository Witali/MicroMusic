import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/turkish-march/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const report=JSON.parse(read('build-report.json')),{labels,score}=report;
const arrangement=JSON.parse(read('score.json'));
const voices=report.releaseChannels.voiceAddresses;
const word=(c,a)=>c.data[a]|c.data[a+1]<<8;

test('AVR starts with the recognizable MIDI opening even when Flash storage reorders phrases',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),notes=[];
  const step=c.step.bind(c);
  c.step=()=>{
    if(c.pc===labels.lead_commit/2&&!c.inIRQ)notes.push({step:word(c,voices[0]+3)&32767,cycle:c.cyc});
    step();
  };
  while(notes.length<9&&c.cyc<3*9600000)c.nextDuty();
  const expectedMidi=[65,63,62,63,66,68,66,65,66];
  assert.deepEqual(notes.slice(0,9).map(n=>n.step),expectedMidi.map(n=>Math.round(440*2**((n-69)/12)*65536/18750)));
  assert.ok(notes[0].cycle/9600000>.39&&notes[0].cycle/9600000<.43,'Original one-quarter pickup rest retained');
  assert.equal(labels.first_section,labels.melody_data+score.section_offsets[score.playlist[0]]);
  assert.equal(c.lost+c.workLost,0);
});

test('both Turkish March parts use the build-time piano bank and omit invented voices',()=>{
  const assignments=arrangement.instruments;
  assert.equal(assignments.lead,'acoustic-grand-piano');
  assert.equal(assignments.keys.instrument,'acoustic-grand-piano');
  assert.equal(assignments.keys.level,10);
  assert.equal(assignments.pluck,'off');assert.equal(assignments.percussion,'off');
  const bank=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)));
  const piano=bank.instruments['acoustic-grand-piano'],ep=read('eeprom.bin');
  assert.equal(piano.gmProgram,0);
  for(const offset of [0,16])for(const [register,extra] of [['low',0],['high',8]])for(let i=0;i<16;i++)
    assert.equal(((ep[offset+extra+(i>>1)]>>(i%2?4:0))&15)-8,piano.waves[register][i]);
  assert.ok(ep.subarray(32,48).every(n=>n===0x88),'Unused tonal slot is silent');
  for(const [register,offset] of [['low',48],['high',56]])for(let i=0;i<16;i++)
    assert.equal(((ep[offset+(i>>1)]>>(i%2?4:0))&15)-8,piano.transient.waves[register][i]);
  assert.equal(labels.render_drum,undefined);assert.equal(labels.drum_trigger,undefined);
});

// Independently pair the structured source events: expected on/off boundaries
// do not come from the firmware arranger's selected-note metadata.
function sourceMidi(){
  const data=JSON.parse(readFileSync(new URL('../../ATtiny13A/Music/reference/turkish-march/source-events.json',import.meta.url)));
  assert.equal(data.schema,'micromusic-midi-events');assert.equal(data.version,1);
  const notes=[];
  for(const {index:track,events} of data.tracks){
    const active=new Map();let tick=0;
    for(const event of events){
      tick=event.tick;const {channel,note:pitch,velocity}=event,key=channel*128+pitch;
      if(event.type==='noteOn'&&velocity>0){if(!active.has(key))active.set(key,[]);active.get(key).push([tick,velocity]);}
      if(event.type==='noteOff'||(event.type==='noteOn'&&velocity===0)){
        const starts=active.get(key);if(starts?.length){const [on,level]=starts.shift();if(tick>on)notes.push({track,channel,pitch,on,off:tick,velocity:level});}
      }
    }
    for(const [key,starts] of active)for(const [on,velocity] of starts)
      if(tick>on)notes.push({track,channel:Math.floor(key/128),pitch:key%128,on,off:tick,velocity});
  }
  return {ppqn:data.ppqn,notes:notes.map((note,index)=>({...note,index}))};
}

function decodedCommands(){
  const rom=read('synth.bin'),result=[];let unit=0;
  for(const name of score.playlist){
    let address=labels['section_'+name];
    while(rom[address]!==255){
      const token=rom[address++];result.push({token,unit});
      if(token<224)unit+=score.durations[token&7];
    }
  }
  return result;
}

test('every selected left piano attack and release follows the real source note identity',()=>{
  const {ppqn,notes}=sourceMidi(),expected=[],sourceUnits=arrangement.arrangement.sourceQuarterBeats*4;
  for(let window=0;window<sourceUnits;window+=8){
    const candidates=notes.filter(n=>n.track===2&&n.on<=window*ppqn/4+ppqn/2&&n.off>window*ppqn/4+ppqn/2)
      .sort((a,b)=>a.pitch-b.pitch||b.on-a.on||a.index-b.index);
    if(!candidates.length)continue;
    const n=candidates[0],on=Math.ceil(Math.max(window,n.on*4/ppqn)),off=Math.max(on+1,Math.floor(Math.min(window+8,n.off*4/ppqn)));
    const prior=expected.at(-1);
    if(prior?.sourceIndex===n.index&&prior.offUnit===on)prior.offUnit=off;
    else expected.push({sourceIndex:n.index,pitch:n.pitch,onUnit:on,offUnit:off,sourceOnTicks:n.on,sourceOffTicks:n.off});
  }
  assert.deepEqual(arrangement.left_hand_note_events,expected);
  const companion=decodedCommands().filter(e=>e.token>=224&&e.token<255&&e.unit<sourceUnits);
  const expectedEvents=[{unit:0,token:242}];
  for(const n of expected){
    const chord=score.chords.findIndex(name=>arrangement.chord_notes[name][0]===n.pitch);
    assert.ok(chord>=0);expectedEvents.push({unit:n.onUnit,token:224|chord},{unit:n.offUnit,token:242});
    assert.ok(n.onUnit>=n.sourceOnTicks*4/ppqn,'No attack before the selected MIDI note starts');
    assert.ok(n.offUnit<=n.sourceOffTicks*4/ppqn,'No selected MIDI note held after its source NoteOff');
  }
  expectedEvents.sort((a,b)=>a.unit-b.unit||Number(a.token<240)-Number(b.token<240));
  assert.deepEqual(companion,expectedEvents.filter(e=>e.unit<sourceUnits));
  assert.equal(expected[0].onUnit,10,'The left-hand first note starts at2.5 quarters, not the old2-quarter window boundary');
  const ending=decodedCommands().filter(e=>e.unit>=sourceUnits&&e.token>=224);
  assert.ok(ending.some(e=>e.unit===sourceUnits+4&&e.token===254),'Cadence left hand and all unused companion gates release after one quarter');
});

test('inserting left-hand NoteOff never changes any right-hand source grid cell or repeated attack',()=>{
  const {ppqn,notes}=sourceMidi(),sourceUnits=arrangement.arrangement.sourceQuarterBeats*4;
  // Python's nearest-even rule is the declared MIDI grid quantizer. Some
  // microtimed source events lie exactly halfway between two grid cells.
  const roundEven=x=>{const low=Math.floor(x),fraction=x-low;return fraction===.5?low+(low%2):Math.round(x);};
  const quantized=notes.filter(n=>n.track===1).map(n=>({...n,start:roundEven(n.on*4/ppqn),end:Math.max(roundEven(n.on*4/ppqn)+1,roundEven(n.off*4/ppqn))}));
  const grid=[];let oldIdentity=null;
  for(let unit=0;unit<sourceUnits;unit++){
    const active=quantized.filter(n=>n.start<=unit&&unit<n.end).sort((a,b)=>b.pitch-a.pitch||b.start-a.start);
    const note=active[0];grid.push({pitch:note?.pitch??null,attack:note!==undefined&&oldIdentity!==note.index});oldIdentity=note?.index??null;
  }
  let sounding=null;
  for(const event of decodedCommands()){
    if(event.unit>=sourceUnits||event.token>=224)continue;
    const index=event.token>>3,attack=index!==score.hold_index&&index!==score.rest_index;
    if(index===score.rest_index)sounding=null;
    else if(index!==score.hold_index){
      const name=score.pitches[index],match=/^([A-G]#?)(-?\d+)$/.exec(name);
      sounding=(Number(match[2])+1)*12+['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'].indexOf(match[1]);
    }
    assert.equal(attack,grid[event.unit].attack,`Right-hand attack at grid${event.unit}`);
    for(let unit=event.unit;unit<event.unit+score.durations[event.token&7];unit++)
      assert.equal(sounding,grid[unit].pitch,`Right-hand pitch/rest at grid${unit}`);
  }
});

test('AVR executes every left-hand gate change without resetting either DDS phase',()=>{
  const rom=read('synth.bin'),c=new AVRCore(rom,read('eeprom.bin'));
  const controlCount=decodedCommands().filter(e=>e.token>=224&&e.token<255).length;
  let checked=0,pending=null;
  const step=c.step.bind(c),phase=()=>voices.slice(0,2).map(a=>word(c,a+1));
  c.step=()=>{
    if(!c.inIRQ&&c.pc===labels.read_event/2){
      if(pending){
        assert.deepEqual(phase(),pending.phase,'Companion controls preserve both DDS phases');
        if(pending.token>=240){
          if(pending.token&2)assert.equal(c.data[voices[1]],pending.level&127,'NOTE_OFF removes the left-hand gate and retains bank/release flags');
          assert.equal(word(c,voices[1]+3),pending.frequency,'Release retains DDS pitch');
        }else{
          const address=labels.chord_steps+(pending.token&15)*4;
          assert.equal(word(c,voices[1]+3),rom[address]|rom[address+1]<<8);
          assert.equal(c.data[voices[1]],128|64|16|10,'Piano left hand retriggers at its configured level10');
        }
        checked++;pending=null;
      }
      const token=rom[c.r[30]|c.r[31]<<8];
      if(token>=224&&token<255)pending={token,phase:phase(),level:c.data[voices[1]],frequency:word(c,voices[1]+3)};
    }
    step();
  };
  const seconds=(arrangement.arrangement.sourceQuarterBeats+4)*60/arrangement.tempo_bpm+1;
  while(checked<controlCount&&c.cyc<seconds*9600000)c.nextDuty();
  assert.equal(checked,controlCount,'Whole arrangement, including the final release');
  assert.equal(c.lost+c.workLost,0);
});

test('closing cadence fully decays before the firmware starts the opening again',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
  let starts=0,restartCycle=null,repeatedOpening=false;
  const step=c.step.bind(c);
  c.step=()=>{
    if(!c.inIRQ&&c.pc===labels.read_event/2&&(c.r[30]|c.r[31]<<8)===labels.first_section&&c.r[4]===1){
      starts++;
      if(starts===2){
        assert.deepEqual(voices.map(a=>c.data[a]&143),[0,0,0,0,0],'Every primary and release gate and level is silent at loop boundary');
        restartCycle=c.cyc;
      }
    }
    if(!c.inIRQ&&restartCycle!==null&&c.pc===labels.lead_commit/2){
      assert.equal(word(c,voices[0]+3)&32767,Math.round(440*2**((65-69)/12)*65536/18750));
      assert.equal(c.data[voices[0]],128|64|15,'The opening piano note has a fresh full attack');
      const pickupSeconds=(c.cyc-restartCycle)/9600000;
      assert.ok(pickupSeconds>.39&&pickupSeconds<.43,'The original pickup rest repeats after the ending');
      repeatedOpening=true;
    }
    step();
  };
  const seconds=(arrangement.arrangement.sourceQuarterBeats+5)*60/arrangement.tempo_bpm+1;
  while(!repeatedOpening&&c.cyc<seconds*9600000)c.nextDuty();
  assert.equal(starts,2);assert.ok(repeatedOpening,'Completed cadence and started the recognizable opening again');
  assert.equal(c.lost+c.workLost,0);
});

test('the left-hand pickup is silent and accompaniment frequencies retain actual MIDI registers',()=>{
  const rom=read('synth.bin'),pairs=arrangement.chord_notes;
  assert.deepEqual(pairs.left_None,[null,null]);
  assert.equal(arrangement.left_hand_sampling_pairs[0][0],'left_None');
  const delta=n=>n===null?0:Math.round(440*2**((n-69)/12)*65536/18750);
  for(let i=0;i<score.chords.length;i++){
    const pair=pairs[score.chords[i]],address=labels.chord_steps+i*4;
    assert.equal(rom[address]|rom[address+1]<<8,delta(pair[0]));
    assert.equal(rom[address+2]|rom[address+3]<<8,0,'Second accompaniment slot is off, not an invented fifth');
    assert.equal(pair[1],null);
  }
  const c=new AVRCore(rom,read('eeprom.bin'));let checked=false;
  const step=c.step.bind(c);
  c.step=()=>{
    if(!checked&&!c.inIRQ&&c.pc===labels.read_event/2&&c.cyc>1000){
      // The score begins with NOTE_OFF before its one-quarter lead rest.
      // Initial silence no longer needs an unused zero-frequency chord.
      const pointer=c.r[30]|c.r[31]<<8;
      if(rom[pointer]<224){assert.equal(word(c,voices[1]+3),0);assert.equal(c.data[voices[1]]&143,0);checked=true;}
    }
    step();
  };
  while(!checked&&c.cyc<960000)c.nextDuty();
  assert.ok(checked,'Executed the silent source pickup');
});
