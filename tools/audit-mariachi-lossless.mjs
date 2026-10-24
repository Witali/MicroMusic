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
   if(on.tick>=58*480&&on.tick<121*480)notes.push({pitch:on.note,on:on.tick-58*480,off:e.tick-58*480,order:on.order,velocity:on.velocity,offVelocity:e.velocity});
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
assert.deepEqual(expected.map(groups=>groups.reduce((sum,g)=>sum+g.pitches.length,0)),[117,910]);
const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
const notes=[[],[]],current=[null,null],queue=Array(14).fill(128);
let finished=false,firstCycle=null,restartCycle=null,previousPwm=128,nextPwm=null,minQueued=16;
let underruns=0,mixChecks=0,pwmChecks=0,maxActive=0,maxElapsed=0,renderStart=null,renderIRQs=0;
let burstStart=null,burstIRQs=0,maxBurst=0,maxDepth=[0,0],lastProgress=0,loopQuiet=false;
let minMix=127,maxMix=-128,maxPitchError=0;
let phaseBefore=null,phaseChecks=0;
const states=()=>meta.voiceAddresses.map(a=>({phase:core.data[a]|core.data[a+1]<<8,step:core.data[a+2]|core.data[a+3]<<8}));
const run=core.step.bind(core);
core.step=()=>{
 if(!finished&&!core.inIRQ){
  if(core.pc===pc.audio_step){burstStart=core.cyc;burstIRQs=core.irqCount;}
  if(core.pc===pc.render_sample){renderStart=core.cyc;renderIRQs=core.irqCount;phaseBefore=states();}
  if(core.pc===pc.restart_song){
   assert.deepEqual([core.r[4],core.r[5]],[0,0],'Both guitars decay before the repeat');loopQuiet=true;
  }
  if(core.pc===pc.next_symbol){
   const part=core.r[19];if(current[part]){current[part].offCycle=core.cyc;current[part]=null;}
  }
  if(core.pc===pc.chord_loaded){
   const part=core.r[19],pitches=[];
   for(const s of states().slice(part?2:0,part?8:2))if(s.step){
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
   const part=core.r[19];maxDepth[part]=Math.max(maxDepth[part],core.r[24]);
   assert.ok(core.r[24]<=(part?5:2),'Pending grammar symbols remain in their SRAM partition');
  }
  if(core.pc===pc.write_pwm){
   const voice=states();
   for(let i=0;i<8;i++){
    assert.equal(voice[i].step,phaseBefore[i].step);
    assert.equal(voice[i].phase,(phaseBefore[i].phase+phaseBefore[i].step)&65535,'Each oscillator advances independently');
    phaseChecks++;
   }
   const values=voice.map(({phase,step})=>{
    const index=phase>>12,b=ep[(step>=1024?8:0)+(index>>1)];return ((index&1?b>>4:b)&15)-8;
   });
   const expectedMix=Math.floor(values.slice(0,2).reduce((a,b)=>a+b,0)*(core.r[4]&15)/8)
    +Math.floor(values.slice(2).reduce((a,b)=>a+b,0)*(core.r[5]&15)/8);
   const mix=core.r[17]&128?core.r[17]-256:core.r[17];assert.equal(mix,expectedMix||0,'Every chord tone contributes exactly');
   assert.ok(mix>=-120&&mix<=120);minMix=Math.min(minMix,mix);maxMix=Math.max(maxMix,mix);
   nextPwm=mix+128;mixChecks++;
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
while(!finished&&core.cyc<9600000*34){
 core.nextDuty();
 const progress=Math.floor(core.cyc/(9600000*8));if(progress>lastProgress){if(log)console.log(`Verified ${progress*8} seconds`);lastProgress=progress;}
}
assert.ok(finished,'One full song and repeat must execute');
assert.equal(underruns,0);assert.equal(core.lost+core.workLost,0);
assert.ok(core.minSP>=151,'Hardware stack must stay above pending symbols');
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
assert.equal(totalNotes,1027);assert.ok(maxOn<25&&maxOff<25);
const report={passed:true,engine:meta.engine,sourceSha256:hash(sourceRaw),flashSha256:hash(rom),eepromSha256:hash(ep),
 flashBytes:rom.length,codeBytes:meta.codeBytes,tableBytes:meta.tableBytes,allSourceNotes:totalNotes,
 allSourceNoteGatesVerified:true,sourceParts:2,sourceNotesByPart:[117,910],chordAttacksByPart:notes.map(g=>g.length),
 oscillators:8,maximumSimultaneousSourceNotes:7,firstSongSeconds:30,loopSeconds:(restartCycle-firstCycle)/9600000,
 maximumOnsetErrorMs:maxOn,maximumGateEndErrorMs:maxOff,maximumGateDurationErrorMs:maxDuration,
 maximumPitchQuantizationErrorCents:maxPitchError,maxRenderActiveCycles:maxActive,maxRenderElapsedCycles:maxElapsed,
 maxControlAndRenderActiveCycles:maxBurst,maxStackBytes:159-core.minSP,phaseStateBytes:32,pendingSymbolBytes:7,
 pwmRingBytes:16,sramUsedWorstCase:55+159-core.minSP,maxPendingSymbolsByPart:maxDepth,
 independentPhaseChecks:phaseChecks,mixChecks,pwmPairChecks:pwmChecks,minQueuedPwmBytes:minQueued,ringUnderruns:underruns,
 lostTimerEvents:core.lost,lostWorkEvents:core.workLost,isrCycles:core.maxIRQ,mixRange:[minMix,maxMix],
 bothPartsSilentBeforeRestart:loopQuiet,emulationOnly:true};
if(writeReport)fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');
if(log)console.log(JSON.stringify(report,null,2));
return report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)audit(process.argv[2]);
