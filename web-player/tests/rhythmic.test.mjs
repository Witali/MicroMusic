import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-reference.js';
const base=new URL('../../ATtiny13A/Music/variants/rhythmic/',import.meta.url);
const read=n=>readFileSync(new URL(n,base));
const report=JSON.parse(read('build-report.json')),{labels,score}=report;
const voices=report.channels.voiceAddresses;

for(const image of ['rhythmic','lumiere-stereo'])test(`${image}: NoteOff masks release all piano tones as one part`,()=>{
  const folder=new URL(`../../ATtiny13A/Music/variants/${image}/`,import.meta.url);
  const rom=readFileSync(new URL('synth.bin',folder)),ep=readFileSync(new URL('eeprom.bin',folder));
  const labels=JSON.parse(readFileSync(new URL('build-report.json',folder))).labels;
  for(let mask=1;mask<=14;mask++){
    const c=new AVRCore(rom,ep);for(const a of [96,101,106,111,116])c.data[a]=143;
    c.pc=labels.note_off/2;c.r[16]=240|mask;
    while(c.pc!==labels.read_event/2)c.step();
    for(const [a,bit] of [[96,0],[101,1],[106,1],[111,1],[116,2]])
      assert.equal(!!(c.data[a]&128),!(mask&(1<<bit)),`mask ${mask}, state ${a}`);
    assert.equal(c.r[20],mask&8?132:0);
  }
});

test('the pinned complete-song trace includes every lead attack and four-tone harmony',()=>{
  const audit=JSON.parse(readFileSync(new URL('../reports/rhythmic-release-verification.json',import.meta.url)));
  assert.equal(audit.flashSha256,createHash('sha256').update(read('synth.bin')).digest('hex'));
  assert.deepEqual([audit.completeSong.leadNotes,audit.completeSong.pianoNotes,audit.completeSong.guitarNotes],[309,348,116]);
  assert.equal(audit.completeSong.missingAttacks,0);assert.equal(audit.completeSong.idealSeconds,222);
  assert.equal(audit.pwm.fifoUnderruns,0);assert.equal(audit.timing.lostTimerEvents,0);
  assert.equal(score.chords.length,6);assert.notDeepEqual(score.chord_notes['F#'],score.chord_notes['F#m']);
});

test('packed Lumiere preserves its original opening and first-section entry point',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),notes=[];
  const step=c.step.bind(c),a=voices[0];
  c.step=()=>{if(c.pc===labels.lead_commit/2&&!c.inIRQ)notes.push((c.data[a+3]|c.data[a+4]<<8)&32767);step();};
  while(notes.length<8&&c.cyc<4*9600000)c.nextDuty();
  assert.deepEqual(notes.slice(0,8),[59,66,74,67,71,55,66,73].map(n=>Math.round(440*2**((n-69)/12)*65536/18750)));
  assert.equal(labels.first_section,labels.melody_data+score.section_offsets[score.playlist[0]]);
});

test('the tone routine exactly scales every sustain and piano attack sample at all envelope levels',()=>{
  const rom=read('synth.bin'),ep=read('eeprom.bin');
  for(const offset of [0,16,32])for(const high of [false,true])for(let level=0;level<16;level++)for(let phase=0;phase<16;phase++){
    const c=new AVRCore(rom,ep);c.pc=labels.render_tone/2;c.r[26]=101+offset/16*5;
    c.r[25]=128|offset|level;c.r[16]=high?4:3;c.r[17]=phase<<4;c.pushPC(0);
    do{c.step();}while(c.pc!==0);
    const bank=offset===16&&level>=14?48:offset;
    const packed=ep[bank+(high?8:0)+(phase>>1)],q=((phase&1)?packed>>4:packed&15)-8;
    assert.equal(c.r[17],Math.floor(q*(offset===16?level>>1:level)/4)&255,`${offset}/${high}/${level}/${phase}`);
    assert.equal(c.r[29],0);assert.equal(c.sp,159);
  }
});

test('actual percussion noise visits all 65535 nonzero states before repeating',()=>{
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin')),seen=new Set();c.r[14]=167;
  const start=labels['.L298']/2,end=labels['.L2a0']/2+1;
  let expected=167;
  for(let i=0;i<65535;i++){
    c.pc=start;while(c.pc!==end)c.step();
    expected=((expected<<1)&65535)^((expected&32768)?45:0);
    const state=c.r[14]|c.r[5]<<8;
    assert.equal(state,expected);assert.ok(state!==0&&!seen.has(state));seen.add(state);
  }
  assert.equal(expected,167);assert.equal(seen.size,65535);
});

test('bass drum keeps its waveform on both sixteenths of the same eighth-note hit',()=>{
  let nonzero=false;
  for(let age=0;age<4;age++)for(const point of [0,1,32,64,127,255]){
    const outputs=[];
    for(const gridPhase of [0,1]){
      const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
      c.pc=labels.render_drum/2;c.r[19]=gridPhase;c.r[20]=age;c.r[15]=point;c.r[14]=167;
      while(c.pc!==labels.write_pwm/2)c.step();
      outputs.push([c.r[14],c.r[17],c.r[21]]);nonzero||=c.r[21]!==0;
      assert.equal(c.r[29],0,'The percussion renderer preserves the zero pointer high byte');
    }
    assert.deepEqual(outputs[0],outputs[1]);
  }
  assert.ok(nonzero,'The exercised renderer actually adds audible percussion');
});

test('every packed playlist and note-off command executes above the PWM ring and below the stack',t=>{
  const rom=read('synth.bin'),c=new AVRCore(rom,read('eeprom.bin')),sections=new Set(),tokens=new Set(),expectedTokens=new Set();
  for(const name of score.playlist){let a=labels['section_'+name];do{expectedTokens.add(rom[a]);}while(rom[a++]!==255);}
  const entry=labels.audio_step/2,done=labels.idle/2;let maximum=0;
  for(let n=0;n<950;n++){
    while(c.pc!==entry||c.inIRQ)c.step();
    // Force a real fractional-grid carry and expired note on an envelope tick.
    // Ring pointers and all five voice states retain their hardware values.
    c.r[15]=255;c.r[2]=255;c.r[3]=255;c.r[1]=1;
    const before=c.cyc;
    do{
      if(c.pc===labels.read_event/2&&!c.inIRQ)tokens.add(rom[c.r[30]|c.r[31]<<8]);
      c.step();
    }while(c.pc!==done||c.inIRQ);
    maximum=Math.max(maximum,c.cyc-before);sections.add(c.r[4]);
  }
  for(let n=0;n<score.playlist.length;n++)assert.ok(sections.has(n),`Playlist position ${n}`);
  assert.deepEqual(tokens,expectedTokens);
  assert.ok(c.minSP>=144,'The hardware stack stays above the voice states and PWM ring');
  assert.equal(c.maxIRQ,15);assert.equal(c.lost+c.workLost,0);assert.ok(rom.length<=1024);
  t.diagnostic(JSON.stringify({maximumBurstCyclesIncludingIrq:maximum,maxStackBytes:159-c.minSP,distinctCommandBytes:tokens.size}));
});
