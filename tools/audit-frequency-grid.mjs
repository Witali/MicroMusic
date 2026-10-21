// Check authored pitches against actual ROM tables and execute every DDS step
// through each firmware's real AVR voice loop, including carry and fast tags.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';

const ids=['rhythmic','alicia','turkish-march','children','greensleeves'];
const sampleHz=18750,word=(bytes,a)=>bytes[a]|bytes[a+1]<<8;
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function midi(value){
  if(value===null||value==='R'||value==='HOLD')return null;
  if(Number.isInteger(value))return value;
  const match=/^([A-G])([#b]?)(-?\d+)$/.exec(value);
  assert.ok(match,`Unknown pitch ${value}`);
  const [,letter,accidental,octave]=match;
  return (Number(octave)+1)*12+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[letter]+(accidental==='#'?1:accidental==='b'?-1:0);
}
const results=[];
for(const id of ids){
  const base=`ATtiny13A/Music/variants/${id}/`,rom=fs.readFileSync(base+'synth.bin'),ep=fs.readFileSync(base+'eeprom.bin');
  const report=JSON.parse(fs.readFileSync(base+'build-report.json')),score=report.score,labels=report.labels;
  assert.equal(sha(rom),report.flashSha256);
  const entries=[];
  const pitches=score.dds_pitches??score.pitches.filter(n=>!['R','HOLD'].includes(n));
  pitches.forEach((pitch,i)=>entries.push({table:'melody',pitch:midi(pitch),address:labels.note_steps+i*2}));
  if(score.chords)score.chords.forEach((chord,i)=>score.chord_notes[chord].forEach((pitch,voice)=>{
    entries.push({table:`companion${voice+1}`,pitch:midi(pitch),address:labels.chord_steps+i*4+voice*2});
  }));
  let phaseChecks=0;
  const notes=entries.map(entry=>{
    const storedStep=word(rom,entry.address),step=storedStep&32767;
    const targetHz=entry.pitch===null?0:440*2**((entry.pitch-69)/12),expected=Math.round(targetHz*65536/sampleHz);
    assert.equal(step,expected,`${id}: ROM DDS disagrees with authored MIDI pitch ${entry.pitch}`);
    for(const state of report.releaseChannels.voiceAddresses)for(const phase of [0,1,0x7fff,0xfffe,0xffff]){
      const c=new AVRCore(rom,ep);c.r[26]=state;c.r[27]=c.r[29]=0;
      c.data[state]=0; // A silent oscillator still accumulates its real phase.
      c.data[state+1]=phase&255;c.data[state+2]=phase>>8;
      c.data[state+3]=storedStep&255;c.data[state+4]=storedStep>>8;
      c.pc=labels.voice_loop/2;
      let instructions=0;
      do{c.step();assert.ok(++instructions<100);}while(c.pc!==labels.primary_gain/2);
      assert.equal(word(c.data,state+1),(phase+step)&65535,`${id}: actual AVR phase step, state${state}`);
      assert.equal(c.sp,159);phaseChecks++;
    }
    const actualHz=step*sampleHz/65536,errorHz=actualHz-targetHz;
    const errorCents=targetHz?1200*Math.log2(actualHz/targetHz):0;
    assert.ok(Math.abs(errorHz)<=sampleHz/131072+1e-10,'Closest representable DDS frequency');
    return {...entry,storedStep,step,targetHz,actualHz,errorHz,errorCents};
  });
  const sounding=notes.filter(n=>n.pitch!==null);
  const ranges=[[labels.read_event,labels.render_tone]];
  if(report.engine==='alicia-native')ranges.push([labels.indexed_note,labels.playlist]);
  let decoderInstructions=0;
  for(const [start,end]of ranges){
    let at=start;
    while(at<end){const instruction=word(rom,at);at+=[0x940c,0x940e,0x9000,0x9200].includes(instruction&0xfe0e)?4:2;decoderInstructions++;}
    assert.equal(at,end);
  }
  const result={id,flashSha256:sha(rom),eepromSha256:sha(ep),tableEntries:notes.length,
    decoderBytes:ranges.reduce((sum,[a,b])=>sum+b-a,0),decoderInstructions,
    uniquePitches:new Set(sounding.map(n=>n.pitch)).size,phaseChecks,
    maximumAbsoluteErrorHz:Math.max(...sounding.map(n=>Math.abs(n.errorHz))),
    maximumAbsoluteErrorCents:Math.max(...sounding.map(n=>Math.abs(n.errorCents))),notes};
  results.push(result);
  console.log(`${id}: ${result.uniquePitches} pitches, ${phaseChecks} real AVR phase checks; max ${result.maximumAbsoluteErrorCents.toFixed(3)} cents`);
}
const output={passed:true,cpuHz:9600000,pwmHz:37500,sampleHz,referenceA4Hz:440,ddsBits:16,
  frequencyStepHz:sampleHz/65536,maximumRoundingErrorHz:sampleHz/131072,
  method:'Equal temperament A4=440Hz. ROM words compared to independently calculated nearest DDS increments. Each word executed in every real AVR voice state at five phase/carry boundaries. Full-song timing and PWM queues are audited separately.',results};
fs.writeFileSync('web-player/reports/frequency-grid-verification.json',JSON.stringify(output,null,2)+'\n');
