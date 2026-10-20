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
const units=[1,2,3,4,6,8,16],ticks=[],expected=[];let totalUnits=0;
for(let p=0;p<score.playlist.length;p++){
  const section=score.playlist[p];let address=labels[`section_${section}`];
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
const originalStep=c.step.bind(c);
c.step=()=>{
  if(!c.inIRQ){
    if(c.pc===labels.music_tick/2){envTick++;prior=[c.r[1],c.r[19],c.r[20]];}
    if(c.pc===labels['.L0a8']/2&&prior){
      assert.deepEqual([c.r[1],c.r[19],c.r[20]],[lead(prior[0]),env(prior[1],c.r[24],3),env(prior[2],c.r[24],1)],`Envelope tick ${envTick}`);
      envelopeChecks++;prior=null;
      if(firstAttack!==null&&fullAttack===null){if((c.r[1]&15)>=8&&halfAttack===null)halfAttack=c.cyc;if((c.r[1]&15)===15)fullAttack=c.cyc;}
    }
    if(c.pc===labels.drum_trigger/2)drums.push({unit:(drums.length)*2,cycles:c.cyc,type:c.r[29]>>1,tick:envTick});
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
      assert.equal(c.r[16],128|((pending.level&15)>>1),'Soft retrigger level');
      assert.equal(c.r[2]|c.r[3]<<8,pending.phase,'No DDS phase reset');
      if(pending.repeated){assert.notEqual(c.r[16],pending.level,'Repeated note articulated');repeatedArticulated++;}
      if(firstAttack===null)firstAttack=c.cyc;
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
for(const drum of drums)assert.equal(drum.tick,ticks[drum.unit],'Drums on the identical sixteenth grid');
const maxTimingErrorMs=Math.max(...events.map(e=>Math.abs(e.errorMs)));
assert.ok(maxTimingErrorMs<25,`${maxTimingErrorMs} ms whole-song deviation`);
assert.ok(maxStepErrorUs<50);assert.ok((fullAttack-firstAttack)/9600<60);
const report={image:id,flashSha256:createHash('sha256').update(rom).digest('hex'),flashBytes:rom.length,
  fullPlaylist:{commands:index,beats:totalUnits/4,idealSeconds:totalUnits/4*60/score.tempo_bpm,actualSeconds:events.at(-1).timeMs/1000,
    maximumTimingErrorMs:maxTimingErrorMs,finalTimingErrorMs:events.at(-1).errorMs,maximumExecutionErrorAgainstGridUs:maxStepErrorUs,missingEvents:0},
  grid:{phaseStep:timing.phaseStep,targetBpm:score.tempo_bpm,actualBpm:timing.actualTempoBpm,drumHitsIncludingBothEndpoints:drums.length,drumGridMismatches:0},
  articulation:{realNoteOns,holdNotes,repeatedNotes:repeated,repeatedNotesArticulated:repeatedArticulated,phaseResets:0,
    firstAttack50PercentMs:(halfAttack-firstAttack)/9600,firstAttack100PercentMs:(fullAttack-firstAttack)/9600},
  envelopes:{ticksChecked:envelopeChecks,mismatches:0},isrCycles:c.maxIRQ,lostTimerEvents:c.lost,lostWorkEvents:c.workLost};
fs.writeFileSync(`web-player/reports/${id}-verification.json`,JSON.stringify(report,null,2)+'\n');
fs.mkdirSync('build/rhythm',{recursive:true});fs.writeFileSync(`build/rhythm/${id}-trace.json`,JSON.stringify({events,drums}));
console.log(JSON.stringify(report,null,2));
