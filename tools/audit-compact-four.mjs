// Independently pair retained source events and inspect every AVR command/PWM pair.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-reference.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const hash=b=>createHash('sha256').update(b).digest('hex');
export function audit(input=path.join(root,'ATtiny13A/Music/variants/greensleeves'),{writeReport=true,log=true}={}){
 const folder=path.resolve(input),read=n=>fs.readFileSync(path.join(folder,n));
 const score=JSON.parse(read('score.json')),meta=JSON.parse(read('build-report.json'));
 const rom=read('synth.bin'),ep=read('eeprom.bin');
 const sourcePath=path.resolve(root,'ATtiny13A/Music/variants/greensleeves',score.provenance.file);
 const raw=fs.readFileSync(sourcePath),source=JSON.parse(raw),sourceParts=[];
 assert.equal(hash(raw),score.provenance.sha256);assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
 for(const {index,events} of source.tracks){
  const active=new Map(),notes=[];
  for(const e of events){
   const key=e.channel*128+e.note;
   if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push(e);active.set(key,q);}
   else if(e.type==='noteOff'||(e.type==='noteOn'&&!e.velocity)){
    const on=active.get(key)?.shift();assert.ok(on);
    notes.push({pitch:e.note,on:on.tick*4/source.ppqn,off:e.tick*4/source.ppqn,velocity:on.velocity});
   }
  }
  assert.ok([...active.values()].every(q=>!q.length));
  sourceParts[index]=notes.sort((a,b)=>a.on-b.on);
 }
 assert.deepEqual(score.parts.map(p=>p.notes.map(({pitch,on,off,velocity})=>({pitch,on,off,velocity}))),sourceParts);
 const fullBounds=score.parts.map((part,index)=>{
  const samples=[...ep.subarray(index*16,(index+1)*16)].flatMap(b=>[(b&15)-8,(b>>4)-8]);
  return [Math.floor(Math.min(...samples)*part.level/8),Math.floor(Math.max(...samples)*part.level/8)];
 });
 assert.equal(meta.outputNormalization.minimum,fullBounds.reduce((sum,pair)=>sum+Math.min(0,pair[0]),0));
 assert.equal(meta.outputNormalization.maximum,fullBounds.reduce((sum,pair)=>sum+Math.max(0,pair[1]),0));
 const expected=[];
 for(let part=0;part<4;part++)for(const n of sourceParts[part]){
  expected.push({unit:n.on,part,pitch:n.pitch,on:true});expected.push({unit:n.off,part,pitch:null,on:false});
 }
 expected.sort((a,b)=>a.unit-b.unit||Number(a.on)-Number(b.on)||a.part-b.part);
 const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
 const addresses=meta.voices.voiceAddresses,word=a=>core.data[a]|core.data[a+1]<<8;
 const states=()=>addresses.map(a=>({level:core.data[a],phase:word(a+1),step:word(a+3)}));
 const queue=Array(14).fill(128);let finished=false,unit=0,eventIndex=0,firstCycle=null,restartCycle=null;
 let phaseBefore=null,pending=null,renderStart=null,renderIRQs=0,maxRender=0,maxActive=0,maxBurst=0,burstStart=null,burstIRQs=0;
 let checks=0,pwmChecks=0,nextPwm=null,previousPwm=128,minQueued=16,underruns=0,minMix=127,maxMix=-128,minPwm=255,maxPwm=0,maxPending=0;
 const actual=[],run=core.step.bind(core);
 core.step=()=>{
  if(!finished&&!core.inIRQ){
   maxPending=Math.max(maxPending,core.r[5]);
   if(core.pc===pc.audio_step){burstStart=core.cyc;burstIRQs=core.irqCount;}
   if(core.pc===pc.render_sample){phaseBefore=states();renderStart=core.cyc;renderIRQs=core.irqCount;}
   if(core.pc===pc.event_leaf){
    const code=core.r[21];
    if(code>=128)unit+=code-127;
    else{
     const part=code>>5,index=code&31,pitch=index?Math.round(69+12*Math.log2((rom[meta.labels.pitch_steps+2*(index-1)]|rom[meta.labels.pitch_steps+2*(index-1)+1]<<8)*18750/65536/440)):null;
     const e=expected[eventIndex++];assert.deepEqual({unit,part,pitch,on:Boolean(index)},e);
     if(firstCycle===null)firstCycle=core.cyc;
     actual.push({...e,cycle:core.cyc});pending={part,index,pitch,phase:word(addresses[part]+1)};
    }
   }
   if(core.pc===pc.note_committed){
    const a=addresses[pending.part];assert.equal(word(a+1),pending.phase,'Note On preserves phase');
    assert.equal(word(a+3),Math.round(440*2**((pending.pitch-69)/12)*65536/18750));assert.equal(core.data[a],129);pending=null;
   }
   if(core.pc===pc.note_released){assert.equal(core.data[addresses[pending.part]]&128,0);pending=null;}
   if(core.pc===pc.restart_song){
    assert.equal(eventIndex,expected.length);assert.ok(states().every(s=>!(s.level&143)),'All parts release before repeat');
    restartCycle=core.cyc;finished=true;
   }
   if(core.pc===pc.master_gain){
    const current=states();let mix=0;
    for(let part=0;part<4;part++){
     const state=current[part],old=phaseBefore[part];assert.equal(state.phase,(old.phase+old.step)&65535);assert.equal(state.step,old.step);
     const index=state.phase>>12,b=ep[part*16+(state.step>=1024?8:0)+(index>>1)],value=((index&1?b>>4:b)&15)-8;
     mix+=Math.floor(value*(state.level&15)/8);
    }
    assert.equal(core.r[22],mix&255);minMix=Math.min(minMix,mix);maxMix=Math.max(maxMix,mix);
    nextPwm=Math.round(128+mix*meta.outputNormalization.gain);assert.ok(nextPwm>=0&&nextPwm<=255,'Linear gain has no wrapping or clipping');
    if(meta.outputNormalization.implementation==='linear-flash-table')assert.equal(rom[meta.labels.output_gain+mix-meta.outputNormalization.minimum],nextPwm);
    minPwm=Math.min(minPwm,nextPwm);maxPwm=Math.max(maxPwm,nextPwm);checks++;
   }
   if(core.pc===pc.ring_published){
    const address=96|((core.r[30]-2)&15),mid=(previousPwm+nextPwm)>>1;
    assert.equal(core.data[address],mid);assert.equal(core.data[address+1],nextPwm);queue.push(mid,nextPwm);previousPwm=nextPwm;pwmChecks++;
   }
  }
  if(!finished&&core.inIRQ&&core.pc===pc.ring_read){minQueued=Math.min(minQueued,queue.length);if(!queue.length)underruns++;assert.equal(core.data[core.r[28]],queue.shift());}
  run();
  if(!core.inIRQ&&core.pc===pc.idle){
   if(renderStart!==null){maxRender=Math.max(maxRender,core.cyc-renderStart);maxActive=Math.max(maxActive,core.cyc-renderStart-15*(core.irqCount-renderIRQs));renderStart=null;}
   if(burstStart!==null){maxBurst=Math.max(maxBurst,core.cyc-burstStart-15*(core.irqCount-burstIRQs));burstStart=null;}
  }
 };
 const seconds=score.endUnit/4*60/score.tempo_bpm;
 while(!finished&&core.cyc<(seconds+2)*9600000)core.nextDuty();
 assert.ok(finished);assert.equal(underruns+core.lost+core.workLost,0);assert.equal(checks,pwmChecks);assert.ok(maxRender<512);assert.ok(maxPending<=8);assert.ok(core.minSP>=140);
 const timingErrors=actual.map(e=>Math.abs((e.cycle-firstCycle)/9600000-e.unit/4*60/score.tempo_bpm)*1000);
 assert.ok(Math.max(...timingErrors)<20);
 const result={engine:'compact-four',flashSha256:meta.flashSha256,eepromSha256:meta.eepromSha256,sourceSha256:score.provenance.sha256,
  allSourceNotesRetained:true,sourceNotes:expected.length/2,playedNotes:expected.length/2,notesByPart:sourceParts.map(p=>p.length),
  musicSeconds:seconds,loopSeconds:(restartCycle-firstCycle)/9600000,firstPassEvents:eventIndex,maxTimingErrorMs:Math.max(...timingErrors),
  mixChecks:checks,pwmPairChecks:pwmChecks,mixRange:[minMix,maxMix],pwmRange:[minPwm,maxPwm],ringUnderruns:underruns,minQueuedPwmBytes:minQueued,
  maxRenderElapsedCycles:maxRender,maxRenderActiveCycles:maxActive,maxControlAndRenderActiveCycles:maxBurst,maxPendingSymbols:maxPending,
  maxStackBytes:159-core.minSP,sramUsedWorstCase:16+20+8+159-core.minSP,isrCycles:core.maxIRQ,lostTimerEvents:core.lost,lostWorkEvents:core.workLost};
 if(writeReport)fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(result,null,2)+'\n');
 if(log)console.log(JSON.stringify(result,null,2));return result;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))audit(process.argv[2]);
