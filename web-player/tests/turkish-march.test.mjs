import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
const base=new URL('../../ATtiny13A/Music/variants/turkish-march/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const {labels,score}=JSON.parse(read('build-report.json'));

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
