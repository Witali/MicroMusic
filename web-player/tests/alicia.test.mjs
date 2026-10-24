import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {AVRCore} from '../lib/avr-reference.js';
import {AVRCore as WasmCore} from '../lib/avr-core.js';
import {sameCPU} from './helpers/avr-test-state.mjs';
import {audit} from '../../tools/audit-alicia-native.mjs';

const base=new URL('../../ATtiny13A/Music/variants/alicia/',import.meta.url);
const read=n=>readFileSync(new URL(n,base)),rom=read('synth.bin'),ep=read('eeprom.bin');
const report=JSON.parse(read('build-report.json')),score=JSON.parse(read('score.json')),{labels}=report;
const sourceBytes=readFileSync(new URL('../../ATtiny13A/Music/reference/alicia/source-score.json',import.meta.url));
const source=JSON.parse(sourceBytes),voices=report.releaseChannels.voiceAddresses;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const fraction=text=>{const[n,d=1]=String(text).split('/').map(Number);return n/d;};
const midi=name=>{if(name==='R')return null;const[,n,a,o]=/^([A-G])([#b]?)(-?\d+)$/.exec(name);return(Number(o)+1)*12+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[n]+(a==='#'?1:a==='b'?-1:0);};
const delta=n=>Math.round(440*2**((n-69)/12)*65536/18750);
const word=(array,a)=>array[a]|array[a+1]<<8;
function sourceEvents(){
  const events=[],bars=[];let seconds=0;
  for(const name of source.playlist){const pattern=source.patterns[name];for(const bar of pattern.bars){let beat=0;
    for(const token of bar.melody.split(' ')){const[pitch,length]=token.split(':'),note=midi(pitch),duration=fraction(length);
      events.push({pitch:note===null?null:note+(bar.lead_transpose??pattern.lead_transpose??0),instrument:bar.lead_instrument??pattern.lead_instrument??1,start:seconds+beat*60/pattern.tempo_bpm,end:seconds+(beat+duration)*60/pattern.tempo_bpm});beat+=duration;}
    assert.equal(beat,bar.beats??pattern.beats_per_bar);bars.push({meter:pattern.beats_per_bar,tempo:pattern.tempo_bpm});seconds+=beat*60/pattern.tempo_bpm;
  }}return{events,bars,seconds};
}
function decoded(){
  const events=[],chords=[],raw=[];let tempo=78,instrument=0,seconds=0;
  for(const name of report.score.playlist){let address=labels['section_'+name];for(;;){const token=rom[address++];if(token===255)break;raw.push(token);
    if(token<192){const index=token>>3,duration=report.score.durations[token&7]*60/tempo/12;
      if(index===report.score.hold_index){assert.ok(events.at(-1)?.pitch!==null);events.at(-1).end+=duration;}
      else events.push({pitch:index===report.score.rest_index?null:midi(report.score.pitches[index]),instrument,start:seconds,end:seconds+duration});seconds+=duration;
    }else if(token<248){const a=labels.chord_descriptors+(token-192)*2,first=rom[a],second=rom[a+1];
      const bassBase=256-labels.BASS_BASE_NEGATIVE;
      chords.push({start:seconds,durationUnits:(second>>4)*6,piano:word(rom,labels.note_steps+(first&15)*2),inner:word(rom,labels.note_steps+(first>>4)*2),bass:word(rom,labels.note_steps+(bassBase+(second&15))*2)});
    }else if(token<251)tempo=[78,58,87][token-248];else if(token<253)instrument=token-251;
  }}return{events,chords,raw,seconds};
}

test('the native source preserves every original meter, tempo, octave and melody identity',()=>{
  assert.deepEqual(score.native_score,source);assert.equal(score.engine,'alicia-native');assert.equal(report.engine,'alicia-native');
  assert.equal(hash(sourceBytes),score.source_score.sha256);assert.equal(report.sourceScoreSha256,hash(sourceBytes));
  const{events,bars,seconds}=sourceEvents();assert.equal(events.length,194);assert.equal(events.filter(e=>e.pitch!==null).length,169);assert.equal(bars.length,55);
  assert.deepEqual([...new Set(bars.map(b=>b.meter))].sort(),[3,4]);assert.deepEqual([...new Set(bars.map(b=>b.tempo))].sort((a,b)=>a-b),[58,78,87]);
  assert.ok(Math.abs(seconds-157.6392572944297)<1e-10);assert.equal(events[0].start,0);
  assert.equal(score.native_units_per_quarter,12);assert.equal(score.arrangement.sourceNoteOns,169);
});

test('ROM phrases retain every exact native note duration, repeated attack and tempo change',()=>{
  const actual=decoded(),expected=sourceEvents();assert.equal(hash(Uint8Array.from(actual.raw)),report.score.compression.originalStreamSha256);
  assert.equal(actual.raw.length,report.score.compression.originalCommandBytes);assert.equal(report.score.compression.verifiedLossless,true);
  const notes=actual.events.filter(e=>e.pitch!==null),original=expected.events.filter(e=>e.pitch!==null);assert.equal(notes.length,169);
  for(let i=0;i<169;i++){assert.equal(notes[i].pitch,original[i].pitch);assert.equal(notes[i].instrument,original[i].instrument);
    assert.ok(Math.abs(notes[i].start-original[i].start)<1e-10,`Attack ${i}`);assert.ok(Math.abs(notes[i].end-original[i].end)<1e-10,`Note Off ${i}`);}
  assert.deepEqual(notes.slice(0,12).map(e=>e.pitch),[72,67,65,72,70,63,67,65,56,63,62,55]);
  assert.ok(Math.abs(actual.seconds-expected.seconds)<1e-10);assert.equal(actual.events.at(-1).pitch,null);
  assert.ok(actual.events.at(-1).end-actual.events.at(-1).start>1,'Source closing rest remains, even when stored in several REST tokens');
});

test('native harmony retains every chord bass and inner tone and restores repeated piano motion',()=>{
  const chords={Cm:[36,[55,60]],Fm:[41,[56,60]],Bb:[46,[58,62]],Eb:[39,[55,58]],C7b9:[36,[58,61]],Gsus4:[43,[55,60]],G7:[43,[55,59]],Abmaj7:[44,[56,60]],Ab:[44,[56,60]],Am7b5:[45,[57,60]],Bb7:[46,[56,62]],'G7/B':[47,[55,59]],'Bb/D':[38,[58,62]],'Cm/Eb':[39,[55,60]],Dm7b5:[38,[53,56]],G7b9:[43,[53,56]],Ddim7:[38,[53,56]],'Cm/G':[43,[55,60]],Fm7:[41,[56,60]],'Fm/Ab':[44,[56,60]],F5:[41,[53,60]],Cmadd9:[36,[55,62]]};
  const expected=[];let seconds=0;
  for(const name of source.playlist){const p=source.patterns[name];for(const bar of p.bars){let beat=0;for(const[chord,duration]of bar.chords){const[bass,[piano,inner]]=chords[chord];expected.push({start:seconds+beat*60/p.tempo_bpm,durationUnits:duration*12,piano:delta(piano),inner:delta(inner),bass:delta(bass)});beat+=duration;}seconds+=(bar.beats??p.beats_per_bar)*60/p.tempo_bpm;}}
  const actual=decoded().chords;assert.equal(actual.length,71);for(let i=0;i<71;i++){assert.ok(Math.abs(actual[i].start-expected[i].start)<1e-10);assert.deepEqual({...actual[i],start:0},{...expected[i],start:0});}
  assert.equal(score.arrangement.companionNoteOns,488);assert.equal(score.arrangement.pianoNoteOns,346);
  assert.match(score.arrangement.reduction,/third chord tone remains omitted/);
  assert.deepEqual(report.pianoArpeggio,score.arrangement.accompaniment);
  assert.equal(report.pianoArpeggio.pianoStepQuarterBeats,.5);
  assert.equal(report.pianoArpeggio.pianoTonesPerChord,2);
});

test('four actual voice assignments share measured piano, violin and cello EEPROM banks',()=>{
  const bankBytes=readFileSync(new URL('../../ATtiny13A/Music/instruments/bank.json',import.meta.url)),bank=JSON.parse(bankBytes);
  assert.equal(report.instrumentBankSha256,hash(bankBytes));assert.equal(report.flashSha256,hash(rom));assert.equal(report.eepromSha256,hash(ep));assert.equal(rom.length,report.flashBytes);assert.ok(rom.length<=1024);
  for(const[id,offset]of[['acoustic-grand-piano-soft',0],['violin',16],['cello',32]])for(const[register,extra]of[['low',0],['high',8]])for(let i=0;i<16;i++)
    assert.equal(((ep[offset+extra+(i>>1)]>>(4*(i&1)))&15)-8,bank.instruments[id].waves[register][i]);
  for(const[register,offset]of[['low',48],['high',56]])for(let i=0;i<16;i++)assert.equal(((ep[offset+(i>>1)]>>(4*(i&1)))&15)-8,bank.instruments['acoustic-grand-piano-soft'].transient.waves[register][i]);
  assert.equal(report.activePrimaryVoices,4);assert.equal(report.primaryVoiceAssignments.length,4);
  assert.deepEqual(report.primaryVoiceAssignments[0].instruments,['acoustic-grand-piano-soft','violin']);
  assert.deepEqual(voices,[97,102,107,112,117,122]);assert.equal(report.releaseChannels.voiceStateBytes,30);assert.equal(report.releaseChannels.tailSlots,2);
  assert.equal(score.percussion_enabled,false);assert.equal(labels.render_drum,undefined);
});

test('actual AVR attacks begin at source beat zero and every retrigger preserves phase',()=>{
  const c=new AVRCore(rom,ep),attacks=[];let before=null,checks=0;const step=c.step.bind(c);
  c.step=()=>{if(!c.inIRQ){if(c.pc===labels.initialize_voice/2){const a=c.r[26];before={a,phase:Array.from(c.data.subarray(a+1,a+3))};}
    if(c.pc===labels.voice_initialized/2){assert.deepEqual(Array.from(c.data.subarray(before.a+1,before.a+3)),before.phase);checks++;}
    if(c.pc===labels.lead_commit/2)attacks.push({step:word(c.data,100),env:c.data[97],cycles:c.cyc});}step();};
  while(attacks.length<12&&c.cyc<10*9600000)c.nextDuty();
  assert.deepEqual(attacks.map(a=>a.step),sourceEvents().events.filter(e=>e.pitch!==null).slice(0,12).map(e=>delta(e.pitch)));
  assert.ok(attacks[0].cycles<9600,'Opening is initialized before the first millisecond');assert.ok(checks>=24);
  assert.ok(attacks.every(a=>a.env===206));assert.equal(c.lost+c.workLost,0);
});

test('bowed primaries rise0/4/8/12 and both release slots retain their full release lengths',()=>{
  const c=new AVRCore(rom,ep);for(const[a,env]of[[97,144],[102,197],[107,160],[112,144],[117,15],[122,79]])c.data[a]=env;
  for(let tick=1;tick<=16;tick++){
    c.pc=labels.music_tick/2;while(c.pc!==labels['.L0a8']/2)c.step();
    for(const a of[97,107,112])assert.equal(c.data[a]&15,Math.min(12,tick*4));
    assert.equal(c.data[117]&15,Math.max(0,15-tick));assert.equal(c.data[122]&15,Math.max(0,15-tick*2));
  }
});

test('native Horner mixing exactly scales all signed nibble/envelope pairs in every register and bank',()=>{
  const synthetic=Uint8Array.from({length:64},(_,i)=>(2*(i%8))|((2*(i%8)+1)<<4));
  for(const bank of[0,16,32])for(const high of[false,true])for(let amp=0;amp<16;amp++)for(let phase=0;phase<16;phase++){
    const c=new AVRCore(rom,synthetic);c.r[25]=128|bank|amp;c.r[16]=high?4:3;c.r[17]=phase<<4;c.r[26]=102;
    c.pc=labels.render_tone/2;c.pushPC(0);do{c.step();}while(c.pc!==0);
    assert.equal(c.r[17],Math.floor((phase-8)*amp/4)&255,`${bank}/${high}/${phase}/${amp}`);assert.equal(c.sp,159);
  }
});

test('upgraded native arpeggio preserves independent JS and WASM PWM and CPU state',()=>{
  const js=new AVRCore(rom,ep),wasm=new WasmCore(rom,ep);
  for(let sample=0;sample<8*37500;sample++)assert.equal(wasm.nextDuty(),js.nextDuty(),`PWM ${sample}`);
  sameCPU(wasm,js);assert.equal(wasm.lost+wasm.workLost,0);
});

test('downloadable player includes the current CPU and strict HEX loader',()=>{
  const require=createRequire(import.meta.url),{AVRCore:Standalone}=require(fileURLToPath(new URL('avr_core.js',base)));
  const standalone=Standalone.fromHex(read('synth.hex').toString(),read('eeprom.hex').toString()),wasm=new WasmCore(rom,ep);
  for(let sample=0;sample<2*37500;sample++)assert.equal(standalone.nextDuty(),wasm.nextDuty(),`Standalone PWM ${sample}`);
  sameCPU(standalone,wasm);assert.ok(read('player.html').includes(read('avr_core.js')));
  for(const [path,expected] of Object.entries(report.standaloneCoreSources.sha256))
    assert.equal(hash(readFileSync(new URL('../../'+path,import.meta.url),'utf8').replace(/\r\n/g,'\n')),expected,path);
  assert.equal(report.standaloneCoreSourceSha256,report.standaloneCoreSources.sha256['web-player/lib/avr-reference.js']);
  assert.equal(report.standaloneHexParserSourceSha256,report.standaloneCoreSources.sha256['web-player/lib/hex.js']);
  assert.throws(()=>Standalone.fromHex(read('synth.hex').toString().replace(':100000',':100001'),read('eeprom.hex').toString()),/checksum/);
});

test('the complete native cycle verifies timing, six envelopes, source Note Off, FIFO and silence before restart',()=>{
  const result=audit(fileURLToPath(base),{writeReport:false,log:false});
  assert.equal(result.sourceNotes,169);assert.equal(result.sourceCompanionNotes,488);assert.equal(result.pianoArpeggioNotes,346);assert.ok(result.maximumMelodyTimingErrorMs<15);
  assert.ok(result.allSixVoicesSilentBeforeLoop);assert.ok(result.minQueued>0);assert.ok(result.maxRenderCycles<=512);assert.equal(result.lost,0);
});
