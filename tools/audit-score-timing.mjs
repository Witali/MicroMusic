// Trace a complete playlist through real AVR code, independently decode its score.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';
const id=process.argv[2]||'natural-hat',folder=`ATtiny13A/Music/variants/${id}`;
const rom=fs.readFileSync(`${folder}/synth.bin`),ep=fs.readFileSync(`${folder}/eeprom.bin`);
const {labels}=JSON.parse(fs.readFileSync(`${folder}/build-report.json`));
const score=JSON.parse(fs.readFileSync(`${folder}/score.json`));
const beats=[.25,.5,.75,1,1.5,2,4],tickCycles=512*256,hz=9600000;
const durations=[...rom.subarray(labels.durations,labels.durations+7)];
const expected=[];let totalBeats=0,totalTicks=0;
for(let p=0;p<score.playlist.length;p++){
  const section=score.playlist[p];let address=labels[`section_${section}`];
  for(;;){
    const token=rom[address++];
    expected.push({playlist:p,section,token,beat:totalBeats,tick:1+totalTicks});
    if(token===255)break;
    if(token<224){totalBeats+=beats[token&7];totalTicks+=durations[token&7];}
  }
}
const c=new AVRCore(rom,ep),events=[],drums=[],envelopeErrors=[],leadAttack=[];
const entry=labels.read_event/2,music=labels.music_tick/2,after=labels['.L0a8']/2,beatEvent=labels['.L0ba']/2;
let finished=false,firstCycle=null,tick=0,oldEnv,previousPitch=null,pendingNote=null;
let repeatedNotes=0,repeatedNotesWithoutLevelChange=0,leadBefore=0;
let firstAttackCycle=null,firstHalfCycle=null,firstPeakCycle=null;
const envModel=(value,phase,mask)=>{
  let level=value&15;if(!level)return value;
  if(value&128){if(level<10)mask=2*mask+1;if(level<7)mask=2*mask+1;return value-Number((phase&mask)===0);}
  return Math.max(0,value-(mask===3?2:1));
};
const leadModel=(value,phase)=>{
  if(value&128)return value===143||!(phase&3)?value:value+1;
  if(!value)return 0;value--;if(value&8)value--;return value;
};
const step=c.step.bind(c);
c.step=()=>{
  if(!c.inIRQ){
    if(c.pc===music){tick++;oldEnv=[c.r[1],c.r[19],c.r[20]];}
    if(c.pc===after&&oldEnv){
      const actual=[c.r[1],c.r[19],c.r[20]],predicted=[leadModel(oldEnv[0],c.r[24]),envModel(oldEnv[1],c.r[24],3),envModel(oldEnv[2],c.r[24],1)];
      if(actual.some((v,i)=>v!==predicted[i]))envelopeErrors.push({tick,actual,predicted});
      if(firstAttackCycle!==null&&firstPeakCycle===null){
        leadAttack.push({tick,cycles:c.cyc,level:c.r[1]&15});
        if((c.r[1]&15)>=8&&firstHalfCycle===null)firstHalfCycle=c.cyc;
        if((c.r[1]&15)===15)firstPeakCycle=c.cyc;
      }
      oldEnv=null;
    }
    if(c.pc===beatEvent&&c.r[25]===0&&c.r[21]===0)drums.push({tick,cycles:c.cyc,type:c.r[29]});
    if(c.pc===entry&&!finished){
      const token=rom[c.r[30]|c.r[31]<<8],e=expected[events.length];assert.ok(e,'Unexpected score event');assert.equal(token,e.token);
      if(firstCycle===null)firstCycle=c.cyc;
      const timingMs=(c.cyc-firstCycle)/hz*1000;
      const row={...e,cycles:c.cyc,timeMs:timingMs,quantizedScheduleErrorUs:((c.cyc-firstCycle)-(e.tick-1)*tickCycles)/hz*1e6,
        idealTimeMs:e.beat*60/score.tempo_bpm*1000,driftFromScoreMs:timingMs-e.beat*60/score.tempo_bpm*1000};
      if(token<224){
        const pitch=token>>3;row.pitch=pitch;row.leadBefore=c.r[1];
        if(pitch!==13&&pitch===previousPitch){repeatedNotes++;row.repeated=true;}
        previousPitch=pitch===13?null:pitch;pendingNote=row;leadBefore=c.r[1];
      }
      events.push(row);if(events.length===expected.length)finished=true;
    }
    if(c.pc===labels.note_rest/2-1&&pendingNote&&pendingNote.pitch!==13){
      pendingNote.leadAfter=c.r[1];
      if(pendingNote.repeated&&leadBefore===c.r[1])repeatedNotesWithoutLevelChange++;
      if(firstAttackCycle===null)firstAttackCycle=c.cyc;
      pendingNote=null;
    }
  }
  step();
};
while(!finished&&c.cyc<(totalTicks+10)*tickCycles)c.nextDuty();
assert.ok(finished,'Playlist did not complete');assert.equal(c.lost+c.workLost,0);assert.equal(envelopeErrors.length,0);
const notes=events.filter(e=>e.token<224),chords=events.filter(e=>e.token>=224&&e.token<240);
const durationMs=durations.map(t=>t*tickCycles/hz*1000);
const drumRows=drums.map((d,i)=>({...d,timeMs:(d.cycles-firstCycle)/hz*1000,idealTimeMs:(i+1)*.5*60/score.tempo_bpm*1000}));
const report={image:id,flashSha256:createHash('sha256').update(rom).digest('hex'),coreSha256:createHash('sha256').update(fs.readFileSync('web-player/lib/avr-core.js')).digest('hex'),cpuHz:hz,tempoBpm:score.tempo_bpm,tickCycles,tickMs:tickCycles/hz*1000,
  fullPlaylist:{beats:totalBeats,idealSeconds:totalBeats*60/score.tempo_bpm,quantizedSeconds:totalTicks*tickCycles/hz,
    events:events.length,noteOrRestEvents:notes.length,noteEvents:notes.filter(e=>e.pitch!==13).length,restEvents:notes.filter(e=>e.pitch===13).length,chords:chords.length,drumHits:drums.length,missingEvents:0,
    finalDriftMs:events.at(-1).driftFromScoreMs,maxQuantizedScheduleErrorUs:Math.max(...events.map(e=>Math.abs(e.quantizedScheduleErrorUs)))},
  durations:beats.map((b,i)=>({beats:b,ticks:durations[i],actualMs:durationMs[i],idealMs:b*60/score.tempo_bpm*1000,errorMs:durationMs[i]-b*60/score.tempo_bpm*1000})),
  drumClock:{ticksPerHit:27,actualHalfBeatMs:27*tickCycles/hz*1000,idealHalfBeatMs:30000/score.tempo_bpm,
    driftPerEightHitsMs:8*27*tickCycles/hz*1000-4*60/score.tempo_bpm*1000,
    firstHitRelativeMs:drumRows[0].timeMs,lastHitRelativeMs:drumRows.at(-1).timeMs,
    lastHitErrorAgainstScoreGridMs:drumRows.at(-1).timeMs-drumRows.at(-1).idealTimeMs},
  envelopes:{ticksChecked:tick,modelMismatches:envelopeErrors.length,
    leadAttack50PercentMs:(firstHalfCycle-firstAttackCycle)/hz*1000,leadAttack100PercentMs:(firstPeakCycle-firstAttackCycle)/hz*1000,
    repeatedNotes,repeatedNotesWithoutLevelChange,drumLevels:[1,.5,.5,.25],drumAgeStepMs:2*tickCycles/hz*1000,
    note:'Matches existing envelope code; this is not proof that every articulation matches the musical score or FluidR3.'},
  output:id==='smooth-pwm'?{readySampleBytes:3,readyPoints:2,midpointValues:1,register:'R18',sramOutputAddresses:[97,98],pwmWritePeriodCycles:256,newMixPeriodCycles:512}:
    {readySampleBytes:1,readySamples:1,register:'R18',pwmWritePeriodCycles:256,newMixPeriodCycles:512},
  lostTimerEvents:c.lost,lostWorkEvents:c.workLost,maxIsrCycles:c.maxIRQ,events,drums:drumRows,firstLeadAttack:leadAttack};
fs.mkdirSync('web-player/reports',{recursive:true});
fs.writeFileSync(`web-player/reports/${id}-score-audit.json`,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,events:undefined,drums:undefined,firstLeadAttack:undefined},null,2));
