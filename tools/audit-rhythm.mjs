// A whole-song oracle for the shared beat grid and independent envelope equations.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';
const id=process.argv[2]||'rhythmic',folder=`ATtiny13A/Music/variants/${id}`;
const rom=fs.readFileSync(`${folder}/synth.bin`),ep=fs.readFileSync(`${folder}/eeprom.bin`);
const meta=JSON.parse(fs.readFileSync(`${folder}/build-report.json`)),{labels,timing}=meta;
const {rest_index:rest,hold_index:hold}=meta.score;
const score=JSON.parse(fs.readFileSync(`${folder}/score.json`));
const drumGridUnits=score.percussion_grid_units??2,drumFirstUnit=score.percussion_first_unit??0;
const percussionEnabled=score.percussion_enabled!==false;
const models=[score.lead_envelope_model??'bowed',score.accompaniment_envelope_model??'piano',score.pluck_envelope_model??'pluck'];
const caps=[score.lead_max_level??15,score.keys_max_level??15,score.pluck_max_level??15];
const attacks=['lead','keys','pluck'].map(role=>score[`${role}_attack_step`]??4);
const releases=['lead','keys','pluck'].map(role=>score[`${role}_release_step`]??1);
const fullRetrigger=score.lead_retrigger==='full';
const units=[1,2,3,4,6,8,16],ticks=[],expected=[];let totalUnits=0;
for(let p=0;p<meta.score.playlist.length;p++){
  const section=meta.score.playlist[p];let address=labels[`section_${section}`];
  for(;;){const token=rom[address++];expected.push({playlist:p,section,token,unit:totalUnits});if(token===255)break;if(token<224)totalUnits+=units[token&7];}
}
let phase=timing.initialHighPhase<<8;
for(let tick=1;ticks.length<=totalUnits;tick++){
  phase+=timing.phaseStep;if(phase>=65536){phase-=65536;ticks.push(tick);}
}
const c=new AVRCore(rom,ep),events=[],drums=[];let index=0,envTick=0,prior=null,anchor=null,oldLead=null;
let envelopeChecks=0,realNoteOns=0,holdNotes=0,repeated=0,repeatedArticulated=0,prevPitch=null,pending=null;
let firstAttack=null,halfAttack=null,fullAttack=null,maxStepErrorUs=0;
const env=(v,t,mask)=>{let level=v&15;if(!level)return v;if(v&128){if(level<10)mask=mask*2+1;if(level<7)mask=mask*2+1;return v-Number((t&mask)===0);}return Math.max(0,v-(mask===3?2:1));};
const lead=v=>{if(v&128)return Math.min(143,v+4);if(!v)return 0;v--;if(v&8)v--;return v;};
const envelope=(v,voice,t)=>{
  const model=models[voice];
  if(model==='constant')return v;
  if(model==='off')return 0;
  if(model==='piano')return env(v,t,3);
  if(model==='pluck')return env(v,t,1);
  assert.ok(model==='bowed'||model==='sustain');
  if(v&128)return Math.min(128+caps[voice],v+attacks[voice]);
  return voice===0&&model==='bowed'?lead(v):Math.max(0,v-releases[voice]);
};
const originalStep=c.step.bind(c);
c.step=()=>{
  if(!c.inIRQ){
    if(c.pc===labels.music_tick/2){envTick++;prior=[c.r[1],c.r[19],c.r[20]];}
    if(c.pc===labels['.L0a8']/2&&prior){
      assert.deepEqual([c.r[1],c.r[19],c.r[20]],prior.map((value,voice)=>envelope(value,voice,c.r[24])),`Envelope tick ${envTick}`);
      envelopeChecks++;prior=null;
      if(firstAttack!==null&&fullAttack===null){if((c.r[1]&15)>=Math.ceil(caps[0]/2)&&halfAttack===null)halfAttack=c.cyc;if((c.r[1]&15)===caps[0])fullAttack=c.cyc;}
    }
    if(c.pc===labels.drum_trigger/2)drums.push({unit:drumFirstUnit+drums.length*drumGridUnits,cycles:c.cyc,type:c.r[29]>>1,tick:envTick});
    if(c.pc===labels.read_event/2&&index<expected.length){
      const e=expected[index++],token=rom[c.r[30]|c.r[31]<<8];assert.equal(token,e.token);
      assert.equal(envTick,ticks[e.unit],`Grid position ${e.unit}`);
      if(anchor===null)anchor=c.cyc;
      const timeMs=(c.cyc-anchor)/9600,idealMs=e.unit/4*60000/score.tempo_bpm;
      const errorUs=((c.cyc-anchor)-(ticks[e.unit]-ticks[0])*131072)/9.6;maxStepErrorUs=Math.max(maxStepErrorUs,Math.abs(errorUs));
      events.push({...e,timeMs,idealMs,errorMs:timeMs-idealMs,tick:envTick});
      if(index===expected.length)pending=null;
      if(token<224){
        const pitch=token>>3;pending={pitch,level:c.r[1],phase:c.r[2]|c.r[3]<<8,step:c.r[4]|c.r[5]<<8};
        if(pitch===hold)holdNotes++;
        else if(pitch===rest){prevPitch=null;pending=null;}
        else {realNoteOns++;pending.repeated=pitch===prevPitch;if(pending.repeated)repeated++;prevPitch=pitch;}
      }
    }
    if(c.pc===labels.lead_commit/2&&pending){
      assert.equal(c.r[16],128|(fullRetrigger?caps[0]:(pending.level&15)>>1),'Instrument retrigger level');
      assert.equal(c.r[2]|c.r[3]<<8,pending.phase,'No DDS phase reset');
      if(pending.repeated){assert.notEqual(c.r[16],pending.level,'Repeated note articulated');repeatedArticulated++;}
      if(firstAttack===null)firstAttack=c.cyc;
      if(fullRetrigger&&fullAttack===null){halfAttack=fullAttack=c.cyc;}
      pending=null;
    }
    if(c.pc===labels.hold_sample/2&&pending?.pitch===hold){
      assert.equal(c.r[1],pending.level,'Tie envelope unchanged');assert.equal(c.r[4]|c.r[5]<<8,pending.step,'Tie frequency unchanged');pending=null;
    }
  }
  originalStep();
};
while(index<expected.length&&c.cyc<(ticks.at(-1)+10)*131072)c.nextDuty();
assert.equal(index,expected.length);assert.equal(c.lost+c.workLost,0);assert.equal(repeated,repeatedArticulated);
const semanticHash=createHash('sha256').update(Uint8Array.from(events.filter(e=>e.token!==255).map(e=>e.token))).digest('hex');
assert.equal(semanticHash,meta.score.compression.originalStreamSha256,'Runtime commands equal the unpacked source score');
for(const drum of drums)assert.equal(drum.tick,ticks[drum.unit],'Drums on the identical sixteenth grid');
if(!percussionEnabled)assert.equal(drums.length,0,'Disabled percussion remains silent');
const maxTimingErrorMs=Math.max(...events.map(e=>Math.abs(e.errorMs)));
assert.ok(maxTimingErrorMs<25,`${maxTimingErrorMs} ms whole-song deviation`);
assert.ok(maxStepErrorUs<50);assert.ok((fullAttack-firstAttack)/9600<60);
const report={image:id,flashSha256:createHash('sha256').update(rom).digest('hex'),flashBytes:rom.length,
  fullPlaylist:{commands:index,beats:totalUnits/4,idealSeconds:totalUnits/4*60/score.tempo_bpm,actualSeconds:events.at(-1).timeMs/1000,
    maximumTimingErrorMs:maxTimingErrorMs,finalTimingErrorMs:events.at(-1).errorMs,maximumExecutionErrorAgainstGridUs:maxStepErrorUs,missingEvents:0},
  compression:{...meta.score.compression,runtimeStreamSha256:semanticHash},
  grid:{phaseStep:timing.phaseStep,targetBpm:score.tempo_bpm,actualBpm:timing.actualTempoBpm,drumHitsIncludingBothEndpoints:drums.length,drumGridMismatches:0},
  articulation:{realNoteOns,holdNotes,repeatedNotes:repeated,repeatedNotesArticulated:repeatedArticulated,phaseResets:0,
    firstAttack50PercentMs:(halfAttack-firstAttack)/9600,firstAttack100PercentMs:(fullAttack-firstAttack)/9600},
  envelopes:{models,ticksChecked:envelopeChecks,mismatches:0},isrCycles:c.maxIRQ,lostTimerEvents:c.lost,lostWorkEvents:c.workLost};
const reportPath=`web-player/reports/${id}-verification.json`;
if(fs.existsSync(reportPath)){
  const previous=JSON.parse(fs.readFileSync(reportPath));
  if(previous.flashSha256===report.flashSha256&&previous.browser)report.browser=previous.browser;
}
fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
fs.mkdirSync('build/rhythm',{recursive:true});fs.writeFileSync(`build/rhythm/${id}-trace.json`,JSON.stringify({events,drums}));
console.log(JSON.stringify(report,null,2));
