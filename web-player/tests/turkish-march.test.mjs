import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/turkish-march/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const report=JSON.parse(read('build-report.json')),{labels,score}=report;
const arrangement=JSON.parse(read('score.json'));

test('AVR starts with the recognizable MIDI opening even when Flash storage reorders phrases',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),notes=[];
  const step=c.step.bind(c);
  c.step=()=>{
    if(c.pc===labels.lead_commit/2&&!c.inIRQ)notes.push({step:c.r[4]|c.r[5]<<8,cycle:c.cyc});
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
  assert.ok(ep.subarray(32).every(n=>n===0x88),'Unused tonal slot and reserved EEPROM are silent');
  assert.equal(labels.render_drum,undefined);assert.equal(labels.drum_trigger,undefined);
});

test('the left-hand pickup is silent and accompaniment frequencies retain actual MIDI registers',()=>{
  const rom=read('synth.bin'),pairs=arrangement.chord_notes;
  assert.deepEqual(pairs.left_None,[null,null]);
  assert.equal(arrangement.chord_overrides.intro[0][0],'left_None');
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
      // The score begins with a left_None chord before its one-quarter lead
      // rest. After that chord has executed, the silent DDS must stay zero.
      const pointer=c.r[30]|c.r[31]<<8;
      if(rom[pointer]<224){assert.equal(c.r[8]|c.r[9]<<8,0);assert.equal(c.r[19],0);checked=true;}
    }
    step();
  };
  while(!checked&&c.cyc<960000)c.nextDuty();
  assert.ok(checked,'Executed the silent source pickup');
});
