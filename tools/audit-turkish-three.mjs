// Whole-loop command, source-voicing, phase, envelope and physical FIFO audit.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';
const root=fileURLToPath(new URL('../',import.meta.url)),hash=b=>createHash('sha256').update(b).digest('hex');
export function audit(input=path.join(root,'ATtiny13A/Music/variants/turkish-march'),{writeReport=true,log=true}={}){
 const folder=path.resolve(input),read=n=>fs.readFileSync(path.join(folder,n));
 const meta=JSON.parse(read('build-report.json')),score=JSON.parse(read('score.json')),rom=read('synth.bin'),ep=read('eeprom.bin');
 const raw=fs.readFileSync(path.join(root,'ATtiny13A/Music/reference/turkish-march/source-events.json')),source=JSON.parse(raw);
 assert.equal(hash(raw),score.source_midi.sha256);assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
 const sourceNotes=[];
 for(const {index,events} of source.tracks){
  const active=new Map();for(const e of events){
   const key=e.channel*128+e.note;
   if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push(e);active.set(key,q);}
   else if(e.type==='noteOff'||(e.type==='noteOn'&&!e.velocity)){
    const on=active.get(key)?.shift();if(on)sourceNotes.push({track:index,pitch:e.note,on:on.tick,off:e.tick});
   }
  }
 }
 let extra=0;
 for(const n of score.left_hand_note_events){
  assert.ok(sourceNotes.some(s=>s.track===2&&s.pitch===n.pitch&&s.on===n.sourceOnTicks&&s.off===n.sourceOffTicks));
  assert.ok(n.onUnit*source.ppqn/4>=n.sourceOnTicks);assert.ok(n.offUnit*source.ppqn/4<=n.sourceOffTicks);
  if(n.secondPitch!==null){assert.ok(sourceNotes.some(s=>s.track===2&&s.pitch===n.secondPitch&&s.on===n.sourceOnTicks&&s.off===n.sourceOffTicks));extra++;}
 }
 assert.equal(extra,score.arrangement.restoredSecondChordNotes);
 const expected=[];let unit=0;
 for(const name of meta.score.playlist){let address=meta.labels['section_'+name];for(;;){const byte=rom[address++];expected.push({byte,unit});if(byte===255)break;if(byte<224)unit+=meta.score.durations[byte&7];}}
 const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
 const voices=meta.channels.voiceAddresses,word=a=>core.data[a]|core.data[a+1]<<8;
 const phases=()=>voices.map(a=>word(a+1));
 const caps=['lead','keys','pluck'].map(role=>score[role+'_max_level']);
 const expectedEnvelope=(value,index)=>{
  const amp=value&15,flags=value&240;if(!amp)return value;
  if(value&128){let mask=amp<7?15:amp<10?7:3;if(core.data[voices[index]+4]&128)mask>>=2;return flags|Math.max(0,amp-Number(!(core.r[24]&mask)));}
  return flags|Math.max(0,amp-(value&64?2:1));
 };
 let finished=false,commands=[],envelopes=null,pending=null,phaseBefore=null,renderStart=null,renderIRQs=0,burstStart=null,burstIRQs=0;
 let mix=0,mixes=0,pwmPairs=0,envChecks=0,initializerChecks=0,minMix=127,maxMix=-128,maxRender=0,maxActive=0,maxBurst=0;
 let previous=128,nextPwm=null,minQueued=16,underruns=0;const queue=Array(14).fill(128),run=core.step.bind(core);
 core.step=()=>{
  if(!finished&&!core.inIRQ){
   if(core.pc===pc.audio_step){burstStart=core.cyc;burstIRQs=core.irqCount;}
   if(core.pc===pc.music_tick)envelopes=voices.map(a=>core.data[a]);
   if(core.pc===pc['.L0a8']&&envelopes){for(let i=0;i<3;i++){assert.equal(core.data[voices[i]],expectedEnvelope(envelopes[i],i));envChecks++;}envelopes=null;}
   if(core.pc===pc.read_event){
    if(commands.length===expected.length){assert.ok(voices.every(a=>!(core.data[a]&143)),'All real parts release before restart');finished=true;}
    else commands.push({byte:rom[core.r[30]|core.r[31]<<8],cycles:core.cyc});
   }
   if(core.pc===pc.initialize_voice){const a=core.r[26],z=core.r[30]|core.r[31]<<8;pending={a,phase:word(a+1),step:(rom[z]|rom[z+1]<<8),level:core.r[25]};}
   if(core.pc===pc.voice_initialized_return){
    assert.equal(word(pending.a+1),pending.phase);assert.equal(word(pending.a+3),pending.step);
    assert.equal(core.data[pending.a],pending.step?pending.level:0);initializerChecks++;pending=null;
   }
   if(core.pc===pc.render_sample){phaseBefore=phases();mix=0;renderStart=core.cyc;renderIRQs=core.irqCount;mixes++;}
   if(core.pc===pc.primary_gain)mix+=core.r[17]&128?core.r[17]-256:core.r[17];
   if(core.pc===pc.write_pwm){
    assert.equal(core.r[21],mix&255);assert.ok(mix>=-128&&mix<=127);nextPwm=mix+128;minMix=Math.min(minMix,mix);maxMix=Math.max(maxMix,mix);
    for(let i=0;i<3;i++)assert.equal(word(voices[i]+1),(phaseBefore[i]+(word(voices[i]+3)&32767))&65535);
   }
   if(core.pc===pc.ring_published){const a=128|((core.r[22]-2)&15),mid=(previous+nextPwm)>>1;assert.equal(core.data[a],mid);assert.equal(core.data[a+1],nextPwm);queue.push(mid,nextPwm);previous=nextPwm;pwmPairs++;}
  }
  if(!finished&&core.inIRQ&&core.pc===pc.ring_read){minQueued=Math.min(minQueued,queue.length);if(!queue.length)underruns++;assert.equal(core.data[core.r[28]],queue.shift());}
  run();
  if(!core.inIRQ&&core.pc===pc.idle){
   if(renderStart!==null){maxRender=Math.max(maxRender,core.cyc-renderStart);maxActive=Math.max(maxActive,core.cyc-renderStart-15*(core.irqCount-renderIRQs));renderStart=null;}
   if(burstStart!==null){maxBurst=Math.max(maxBurst,core.cyc-burstStart-15*(core.irqCount-burstIRQs));burstStart=null;}
  }
 };
 const seconds=(score.arrangement.sourceQuarterBeats+4)*60/score.tempo_bpm;
 while(!finished&&core.cyc<(seconds+1)*9600000)core.nextDuty();
 assert.ok(finished);assert.equal(core.lost+core.workLost+underruns,0);assert.equal(mixes,pwmPairs);assert.ok(maxRender<512);assert.ok(core.minSP>=144);
 assert.deepEqual(commands.map(c=>c.byte),expected.map(e=>e.byte));const anchor=commands[0].cycles;
 const timingError=Math.max(...commands.map((c,i)=>Math.abs((c.cycles-anchor)/9600000-expected[i].unit/4*60/score.tempo_bpm)*1000));assert.ok(timingError<25);
 const leadNotes=expected.filter(e=>e.byte<224&&(e.byte>>3)!==meta.score.rest_index&&(e.byte>>3)!==meta.score.hold_index).length;
 const report={engine:'turkish-three',image:'turkish-march',flashBytes:rom.length,flashSha256:hash(rom),eepromSha256:hash(ep),sourceSha256:hash(raw),
  sourceBars:score.arrangement.sourceBars2_4,musicSeconds:seconds,sourceQuarterBeats:score.arrangement.sourceQuarterBeats,
  notesByPart:[leadNotes,score.left_hand_note_events.length+1,extra],playedNotes:leadNotes+score.left_hand_note_events.length+1+extra,
  restoredSecondChordNotes:extra,allSourcePolyphonyRetained:false,sourceSelectedVoicingsVerified:true,
  commands:commands.length,maximumTimingErrorMs:timingError,mixChecks:mixes,pwmPairChecks:pwmPairs,initializerChecks,envelopeChecks:envChecks,
  maxRenderElapsedCycles:maxRender,maxRenderActiveCycles:maxActive,maxControlAndRenderActiveCycles:maxBurst,
  maxStackBytes:159-core.minSP,voiceRamBytes:15,pwmRingBytes:16,sramUsedWorstCase:31+159-core.minSP,isrCycles:core.maxIRQ,
  lostTimerEvents:core.lost,lostWorkEvents:core.workLost,ringUnderruns:underruns,minQueuedPwmBytes:minQueued,mixRange:[minMix,maxMix],
  semanticComparison:{exactCommandBytes:expected.length,maximumTimingErrorMs:timingError,allThreeVoicesSilentBeforeRestart:true}};
 if(writeReport)fs.writeFileSync(path.join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');if(log)console.log(JSON.stringify(report,null,2));return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))audit(process.argv[2]);
