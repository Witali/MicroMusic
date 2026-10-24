// Independent raw-source/AVR comparison for every chord, gate, oscillator and PWM.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {AVRCore} from '../web-player/lib/avr-core.js';
const root=fileURLToPath(new URL('../',import.meta.url));
export function audit(input=path.join(root,'build/mariachi-lossless'),{writeReport=true,log=true}={}){
const folder=path.resolve(input);
const meta=JSON.parse(fs.readFileSync(path.join(folder,'build-report.json')));
const rom=fs.readFileSync(path.join(folder,'synth.bin')),ep=fs.readFileSync(path.join(folder,'eeprom.bin'));
const sourceRaw=fs.readFileSync(path.join(root,'ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json'));
const source=JSON.parse(sourceRaw),hash=b=>createHash('sha256').update(b).digest('hex');
const firstTick=Math.round(meta.sourceSelection.firstBeat*480),lastTick=Math.round(meta.sourceSelection.lastBeat*480);
assert.equal(hash(sourceRaw),meta.sourceSha256);assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
assert.ok(rom.length<=1024,'Complete Flash must fit');
const expected=[];
for(const track of source.tracks){
 const active=new Map(),notes=[];let order=0;
 for(const e of track.events){
  if(e.type!=='noteOn'&&e.type!=='noteOff')continue;
  const key=`${e.channel}:${e.note}`;
  if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push({...e,order:order++});active.set(key,q);}
  else{
   assert.ok(active.get(key)?.length);const on=active.get(key).shift();
   if(on.tick>=firstTick&&on.tick<lastTick)notes.push({pitch:on.note,on:on.tick-firstTick,off:e.tick-firstTick,order:on.order,velocity:on.velocity,offVelocity:e.velocity});
  }
 }
 assert.ok([...active.values()].every(q=>!q.length));
 const groups=[];
 for(const n of notes.sort((a,b)=>a.on-b.on||a.order-b.order)){
  let group=groups.at(-1);if(!group||group.on!==n.on){group={on:n.on,off:n.off,pitches:[],velocity:n.velocity,offVelocity:n.offVelocity};groups.push(group);}
  assert.equal(group.off,n.off);group.pitches.push(n.pitch);
 }
 expected.push(groups);
}
const counts=parts=>parts.map(groups=>groups.reduce((sum,g)=>sum+g.pitches.length,0));
const peakPolyphony=parts=>{
 const events=parts.flatMap(groups=>groups.flatMap(g=>[[g.on,g.pitches.length],[g.off,-g.pitches.length]]));
 let active=0,peak=0;for(const [,delta] of events.sort((a,b)=>a[0]-b[0]||a[1]-b[1])){active+=delta;peak=Math.max(peak,active);}return peak;
};
const sourceCounts=counts(expected),sourcePeak=peakPolyphony(expected);
assert.deepEqual(sourceCounts,meta.arrangement?.sourceNotesByPart??[117,910]);
if(meta.arrangement){
 assert.equal(meta.arrangement.policy,'sparse-source-voicings-v1');
 const arranged=JSON.parse(fs.readFileSync(path.join(folder,'arrangement.json')));
 assert.equal(arranged.sourceSha256,hash(sourceRaw));
 const groups=arranged.parts.map(part=>part.groups.map(g=>({...g,offVelocity:part.offVelocity})));
 assert.deepEqual(groups[0],expected[0],'Every original lead chord and gate is retained');
 let previous=-Infinity;
 for(const g of groups[1]){
  assert.equal(g.on%960,0);assert.equal(g.off,Math.min(g.on+480,lastTick-firstTick));assert.ok(g.on>previous);previous=g.on;
  assert.equal(g.velocity,80);assert.equal(g.offVelocity,64);
  const sourceChord=expected[1].find(s=>s.on<=g.on&&g.on<s.off)??expected[1].findLast(s=>s.on<=g.on);
  assert.ok(sourceChord);assert.ok(g.pitches.every(p=>sourceChord.pitches.includes(p)),'Backing pitches belong to the source chord');
  if(g.on%1920===0)assert.deepEqual(g.pitches,[Math.min(...sourceChord.pitches)]);
  else{assert.ok(g.pitches.length<=3);assert.equal(new Set(g.pitches.map(p=>p%12)).size,g.pitches.length);}
 }
 expected[1]=groups[1];
}
const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
const waveOffsets=meta.partWaveOffsets??[0,0],gainShifts=meta.partGainShifts??[0,0];
const leadVoices=meta.partVoiceCounts?.[0]??2,normalization=meta.outputNormalization;
const drums=meta.percussionProfile,voiceCount=meta.voiceAddresses.length;
const decoderPart=()=>meta.decoderPartSelectors?meta.decoderPartSelectors.indexOf(core.r[19]):core.r[19];
const notes=[[],[]],current=[null,null],queue=Array(14).fill(128);
let finished=false,firstCycle=null,restartCycle=null,previousPwm=128,nextPwm=null,minQueued=16;
let underruns=0,mixChecks=0,pwmChecks=0,maxActive=0,maxElapsed=0,renderStart=null,renderIRQs=0;
let burstStart=null,burstIRQs=0,maxBurst=0,maxDepth=[0,0],lastProgress=0,loopQuiet=false;
let minMix=127,maxMix=-128,maxPitchError=0;
let minPwm=255,maxPwm=0,normalizationChecks=0;
let phaseBefore=null,phaseChecks=0;
let drumValue=0,drumBefore=null,drumChecks=0,drumEnvelopeBefore=null,drumEnvelopeChecks=0;
const drumAttacks=[];
const states=()=>meta.voiceAddresses.map(a=>({phase:core.data[a]|core.data[a+1]<<8,step:core.data[a+2]|core.data[a+3]<<8}));
const run=core.step.bind(core);
core.step=()=>{
 if(!finished&&!core.inIRQ){
  if(core.pc===pc.audio_step){burstStart=core.cyc;burstIRQs=core.irqCount;}
  if(core.pc===pc.render_sample){renderStart=core.cyc;renderIRQs=core.irqCount;phaseBefore=states();}
  if(core.pc===pc.restart_song){
   assert.deepEqual([core.r[4],core.r[5]],[0,0],'Both guitars decay before the repeat');loopQuiet=true;
   if(drums)assert.equal(core.r[6]&4,0,'The last drum hit decays before repeat');
  }
  if(drums&&core.pc===pc.music_tick)drumEnvelopeBefore={stage:core.r[6],clock:core.r[14]};
  if(drums&&core.pc===pc.drum_envelope_done){
   const expected=drumEnvelopeBefore.stage-Number(!((drumEnvelopeBefore.clock+1)&1)&&!!(drumEnvelopeBefore.stage&4));
   assert.equal(core.r[6],expected,'Original two-tick four-stage drum decay');drumEnvelopeChecks++;
  }
  if(drums&&core.pc===pc.drum_trigger){
   assert.equal(core.r[6]&15,!loopQuiet&&drumAttacks.length%2?15:7,'Alternating kick and hat, restarting on kick');
   assert.equal(core.data[32+54],1,'Half-beat countdown expires');
   drumAttacks.push({cycle:core.cyc,kind:core.r[6]&8?'hat':'kick'});
  }
  if(core.pc===pc.next_symbol){
   const part=decoderPart();if(current[part]){current[part].offCycle=core.cyc;current[part]=null;}
  }
  if(core.pc===pc.chord_loaded){
   const part=decoderPart(),pitches=[];
   for(const s of states().slice(part?leadVoices:0,part?voiceCount:leadVoices))if(s.step){
    const frequency=s.step*18750/65536,pitch=Math.round(69+12*Math.log2(frequency/440));pitches.push(pitch);
    maxPitchError=Math.max(maxPitchError,Math.abs(1200*Math.log2(frequency/(440*2**((pitch-69)/12)))));
   }
   if(notes[part].length===expected[part].length){
    assert.equal(part,0);assert.ok(loopQuiet);restartCycle=core.cyc;finished=true;
   }else{
    firstCycle??=core.cyc;const note={pitches,onCycle:core.cyc,offCycle:null};
    notes[part].push(note);current[part]=note;
   }
  }
  if(core.pc===pc.part_return||core.pc===pc.classify_symbol){
   const part=decoderPart();maxDepth[part]=Math.max(maxDepth[part],core.r[24]);
   assert.ok(core.r[24]<=meta.pendingSymbolAddresses[part].length,'Pending grammar symbols remain in their SRAM partition');
  }
  if(drums&&core.pc===pc.render_drum){
   const stage=core.r[6],phase=core.r[22],high=core.r[7];let low=phase,hi=high,value=0;
   if(stage&4){
    if(stage&8){
     let state=((high<<8)|phase);state=((state<<1)&65535)^((state&32768)?45:0);
     low=state&255;hi=state>>8;value=(((low>>1)&63)-(low&63))>>2;
    }else{low=(phase+1)&255;value=((low&128?255-low:low)-61)>>2;}
    value>>=Number(!(stage&1))+Number(!(stage&2));value=(value+4)>>3;
   }
   drumValue=value;drumBefore={low,hi};
  }
  if(drums&&core.pc===pc.drum_mixed){
   assert.equal(core.r[17],drumValue&255,'Exact old kick/hat generator with rounded quiet gain');
   assert.equal(core.r[22],drumBefore.low);assert.equal(core.r[7],drumBefore.hi);drumChecks++;
  }
  if(core.pc===(normalization?pc.master_gain:pc.write_pwm)){
   const voice=states();
   for(let i=0;i<voiceCount;i++){
    assert.equal(voice[i].step,phaseBefore[i].step);
    assert.equal(voice[i].phase,(phaseBefore[i].phase+phaseBefore[i].step)&65535,'Each oscillator advances independently');
    phaseChecks++;
   }
   const values=voice.map(({phase,step},i)=>{
    const index=phase>>12,b=ep[waveOffsets[i<leadVoices?0:1]+(step>=1024?8:0)+(index>>1)];return ((index&1?b>>4:b)&15)-8;
   });
   const expectedMix=(Math.floor(values.slice(0,leadVoices).reduce((a,b)=>a+b,0)*(core.r[4]&15)/8)>>gainShifts[0])
    +(Math.floor(values.slice(leadVoices).reduce((a,b)=>a+b,0)*(core.r[5]&15)/8)>>gainShifts[1])+(drums?drumValue:0);
   const mix=core.r[17]&128?core.r[17]-256:core.r[17];assert.equal(mix,expectedMix||0,'Every chord tone contributes exactly');
   assert.ok(mix>=-120&&mix<=120);minMix=Math.min(minMix,mix);maxMix=Math.max(maxMix,mix);
   if(normalization){
    assert.ok(mix>=normalization.minimum&&mix<=normalization.maximum,'Calibration covers every mixed sample');
    nextPwm=Math.round(128+mix*normalization.gain);
    if(normalization.implementation==='linear-flash-table')
      assert.equal(rom[meta.labels.output_gain+mix-normalization.minimum],nextPwm,'Linear normalized PWM table');
   }else nextPwm=mix+128;
   minPwm=Math.min(minPwm,nextPwm);maxPwm=Math.max(maxPwm,nextPwm);mixChecks++;
  }
  if(normalization&&core.pc===pc.write_pwm){
   const actual=normalization.implementation==='constant-shifts'?(core.r[17]+128)&255:core.r[17];
   assert.equal(actual,nextPwm,'Master gain reaches physical PWM without overflow');normalizationChecks++;
  }
  if(core.pc===pc.ring_published){
   const address=96|((core.r[30]-2)&15),mid=(previousPwm+nextPwm)>>1;
   assert.equal(core.data[address],mid);assert.equal(core.data[address+1],nextPwm);
   queue.push(mid,nextPwm);previousPwm=nextPwm;pwmChecks++;
  }
 }
 if(!finished&&core.inIRQ&&core.pc===pc.ring_read){
  // During control decoding Z is Flash, so the FIFO oracle, rather than Z,
  // supplies the queue occupancy; the saved producer pointer is in r22.
  minQueued=Math.min(minQueued,queue.length);if(!queue.length)underruns++;
  assert.equal(core.data[core.r[28]],queue.shift(),'No lost/reordered physical PWM values');
 }
 run();
 if(!core.inIRQ&&core.pc===pc.idle){
  if(renderStart!==null){const elapsed=core.cyc-renderStart;maxElapsed=Math.max(maxElapsed,elapsed);maxActive=Math.max(maxActive,elapsed-15*(core.irqCount-renderIRQs));renderStart=null;}
  if(burstStart!==null){maxBurst=Math.max(maxBurst,core.cyc-burstStart-15*(core.irqCount-burstIRQs));burstStart=null;}
 }
};
const musicSeconds=Math.max(...expected.flatMap(g=>g.map(n=>n.off)))/480*.476190;
while(!finished&&core.cyc<9600000*(musicSeconds+4)){
 core.nextDuty();
 const progress=Math.floor(core.cyc/(9600000*8));if(progress>lastProgress){if(log)console.log(`Verified ${progress*8} seconds`);lastProgress=progress;}
}
assert.ok(finished,'One full song and repeat must execute');
assert.equal(underruns,0);assert.equal(core.lost+core.workLost,0);
assert.ok(core.minSP>=(drums?150:151),'Hardware stack writes must stay above pending symbols');
let maxOn=0,maxOff=0,maxDuration=0,totalNotes=0;
for(let part=0;part<2;part++){
 assert.equal(notes[part].length,expected[part].length);
 for(let i=0;i<expected[part].length;i++){
  const a=notes[part][i],e=expected[part][i];assert.deepEqual(a.pitches,e.pitches,'Exact ordered source chord');assert.notEqual(a.offCycle,null);
  totalNotes+=e.pitches.length;
  const onset=e.on/480*.476190,off=e.off/480*.476190;
  maxOn=Math.max(maxOn,Math.abs((a.onCycle-firstCycle)/9600000-onset)*1000);
  maxOff=Math.max(maxOff,Math.abs((a.offCycle-firstCycle)/9600000-off)*1000);
  maxDuration=Math.max(maxDuration,Math.abs((a.offCycle-a.onCycle)/9600000-(off-onset))*1000);
 }
}
assert.equal(totalNotes,meta.arrangement?meta.playedNotes:1027);assert.ok(maxOn<25&&maxOff<25);
const report={passed:true,engine:meta.engine,sourceSha256:hash(sourceRaw),flashSha256:hash(rom),eepromSha256:hash(ep),
 flashBytes:rom.length,codeBytes:meta.codeBytes,tableBytes:meta.tableBytes,allSourceNotes:sourceCounts.reduce((a,b)=>a+b,0),
 allSourceNoteGatesVerified:!meta.arrangement,sourceParts:2,sourceNotesByPart:sourceCounts,chordAttacksByPart:notes.map(g=>g.length),
 oscillators:voiceCount,maximumSimultaneousSourceNotes:sourcePeak,maximumSimultaneousPlayedNotes:peakPolyphony(expected),
 partWaveOffsets:waveOffsets,partGainShifts:gainShifts,
 firstSongSeconds:musicSeconds,loopSeconds:(restartCycle-firstCycle)/9600000,
 maximumOnsetErrorMs:maxOn,maximumGateEndErrorMs:maxOff,maximumGateDurationErrorMs:maxDuration,
 maximumPitchQuantizationErrorCents:maxPitchError,maxRenderActiveCycles:maxActive,maxRenderElapsedCycles:maxElapsed,
 maxControlAndRenderActiveCycles:maxBurst,maxStackBytes:159-core.minSP,phaseStateBytes:4*voiceCount,pendingSymbolBytes:7,
 pwmRingBytes:16,sramUsedWorstCase:16+4*voiceCount+7+159-core.minSP,maxPendingSymbolsByPart:maxDepth,
 independentPhaseChecks:phaseChecks,mixChecks,pwmPairChecks:pwmChecks,minQueuedPwmBytes:minQueued,ringUnderruns:underruns,
 lostTimerEvents:core.lost,lostWorkEvents:core.workLost,isrCycles:core.maxIRQ,mixRange:[minMix,maxMix],
 bothPartsSilentBeforeRestart:loopQuiet,emulationOnly:true};
if(normalization){
 assert.equal(normalizationChecks,mixChecks);assert.ok(minPwm===0||maxPwm===255,'A peak reaches full PWM scale');
 assert.equal(normalization.table[-normalization.minimum],128,'Digital silence retains midpoint 128');
 Object.assign(report,{pwmRange:[minPwm,maxPwm],normalizationChecks,masterGain:normalization.gain,
  normalizationGainDb:normalization.gainDb,normalizationLinear:true,normalizationClippedSamples:0});
}
if(drums){
 assert.equal(drumChecks,mixChecks);assert.ok(drumEnvelopeChecks>0);
 // The trace stops at the next lead attack, after that repeat's first kick.
 const firstLoop=drumAttacks.filter(h=>h.cycle<restartCycle-9600000*.5);
 const count=Math.ceil(musicSeconds/(.476190*.5));assert.equal(firstLoop.length,count);
 let maxError=0;
 for(let n=0;n<firstLoop.length;n++)maxError=Math.max(maxError,Math.abs((firstLoop[n].cycle-firstLoop[0].cycle)/9600000-n*.476190*.5)*1000);
 assert.ok(maxError<25);assert.equal(drumAttacks.at(-1).kind,'kick');
 Object.assign(report,{drumChecks,drumEnvelopeChecks,drumAttacks:firstLoop.length,
  drumAttacksByType:{kick:firstLoop.filter(h=>h.kind==='kick').length,hat:firstLoop.filter(h=>h.kind==='hat').length},
  maximumDrumOnsetErrorMs:maxError,drumGeneratorMatchesRetainedKit:true,drumGainRounded:true,
  independentDrumVoices:1,normalizationIncludesDrums:true});
}
if(meta.arrangement)Object.assign(report,{arrangementPolicy:meta.arrangement.policy,playedNotes:totalNotes,
 arrangedNoteGatesVerified:true,leadSourceNoteGatesVerified:true,
 arrangedNotesByPart:expected.map(groups=>groups.reduce((sum,g)=>sum+g.pitches.length,0))});
if(writeReport)fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');
if(log)console.log(JSON.stringify(report,null,2));
return report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)audit(process.argv[2]);
