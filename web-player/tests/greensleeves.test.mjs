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
  assert.deepEqual(actual,expected);
  assert.deepEqual(actual.slice(0,5).map(n=>n.pitch),[64,67,69,71,72]);
  assert.equal(position,192);assert.equal(position%12,0,'Closing bar plus pickup loop in 6/8');
  assert.equal(actual.filter(n=>n.pitch!==null).length,71);
  assert.equal(score.meter,'6/8');assert.equal(score.pickup_beats,.5);
  assert.equal(rom.length,846);assert.ok(rom.length<=1024);
});

test('6/8 percussion keeps both dotted-quarter beats and the pickup phase across repeated loops',()=>{
  const c=new AVRCore(rom,ep);
  while(c.pc!==labels.idle/2)c.step();
  c.sreg&=127;
  const hits=[];
  for(let unit=0;unit<192*3;unit++){
    c.pc=labels.grid_step/2;
    while(c.pc!==labels['.L0ba']/2){
      if(c.pc===labels.drum_trigger/2)hits.push({unit,phase:c.r[29]});
      c.step();
    }
  }
  assert.deepEqual(hits.map(h=>h.unit),Array.from({length:96},(_,i)=>2+i*6));
  assert.deepEqual(hits.map(h=>h.phase),Array.from({length:96},(_,i)=>i%2?6:0));
});
