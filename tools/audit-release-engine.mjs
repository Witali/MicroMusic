import fs from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore} from '../web-player/lib/avr-core.js';

const name=process.argv[2]??'rhythmic';
const folder=`ATtiny13A/Music/variants/${name}`;
const meta=JSON.parse(fs.readFileSync(folder+'/build-report.json')),{labels}=meta;
const voices=meta.releaseChannels.voiceAddresses;
const score=JSON.parse(fs.readFileSync(folder+'/score.json'));
const rom=fs.readFileSync(folder+'/synth.bin'),ep=fs.readFileSync(folder+'/eeprom.bin');
const c=new AVRCore(rom,ep),commands=[],tails=[];
const p=Object.fromEntries(Object.entries(labels).map(([k,v])=>[k,v/2]));
let entry=null,maxElapsed=0,maxActive=0,maxStack=0,tailCopies=0,bothActive=0;
let startIrqs=0,underruns=0,minQueued=16,maxQueued=0,mixes=0,mixMin=127,mixMax=-128;
let copiedSource=null,envelopeBefore=null,envelopeChecks=0,tailDecayChecks=0;let expected=[];let totalUnits=0;const unitDurations=[1,2,3,4,6,8,16];for(const phrase of meta.score.playlist){let at=labels['section_'+phrase];for(;;){const token=rom[at++];expected.push({token,unit:totalUnits});if(token===255)break;if(token<224)totalUnits+=unitDurations[token&7];}}
const seconds=Number(process.argv[3]??(totalUnits/4*60/score.tempo_bpm+.1));let endState=null;
let maxBurst=null,pointSigned=0,toneSigned=0,toneContributions=[];
let renderStart=0,renderIrqs=0,maxRenderCycles=0,maxRenderActive=0,rendering=false;
let initializing=null,initializerChecks=0;
const roles=['lead','keys','pluck'];
const caps=roles.map(r=>score[r+'_max_level']);
const expectedEnv=(value,index,clock,fast)=>{
 const amp=value&15,flags=value&240;
 if(value&128){
  const bank=(value>>4)&3,model=score[bank===0?'lead_envelope_model':bank===1?'accompaniment_envelope_model':'pluck_envelope_model'];
  if(model==='bowed'||model==='sustain')return flags|Math.min(caps[bank],amp+4);
  if(model==='piano'||model==='pluck'){
   const role=roles[bank];let mask=fast?score[role+'_fast_decay_mask']:score[role+'_decay_mask'];mask??=model==='piano'?3:1;if(amp<10)mask=2*mask+1;if(amp<7)mask=2*mask+1;
   return flags|Math.max(0,amp-Number(!(clock&mask)));
  }
 }
 if(!amp)return value;
 const leadFast=index===0&&score.lead_release_model==='fast-above-8';
 return flags|Math.max(0,amp-(leadFast?1+Number(((amp-1)&8)!==0):value&64?2:1));
};
const signed=n=>n&128?n-256:n;
const step=c.step.bind(c);
c.step=()=>{
 const pc=c.pc;
 if(!c.inIRQ){
  if(pc===p.audio_step){entry=c.cyc;startIrqs=c.irqCount;}
  if(pc===p.music_tick)envelopeBefore=voices.map(a=>c.data[a]);
  if(pc===p['.L0a8']&&envelopeBefore){
   for(let i=0;i<5;i++){
    assert.equal(c.data[voices[i]],expectedEnv(envelopeBefore[i],i,c.r[24],!!(c.data[voices[i]+4]&128)),`envelope ${i} at ${c.cyc}`);
    envelopeChecks++;if(i>=3&&(envelopeBefore[i]&15))tailDecayChecks++;
   }
   envelopeBefore=null;
  }
  if(pc===p.read_event){commands.push({byte:rom[c.r[30]|c.r[31]<<8],cycles:c.cyc});if(commands.length===expected.length){endState=voices.map(a=>c.data[a]&15);assert.deepEqual(endState,[0,0,0,0,0],'All primary and release voices finish before restart');}}
  if(pc===p.capture_ram_tail){
   const from=c.r[26];copiedSource=Array.from(c.data.subarray(from,from+5));copiedSource[0]&=127;
  }
  if(pc===p.initialize_voice){
   const a=c.r[26],z=c.r[30]|c.r[31]<<8;
   const role=roles[voices.indexOf(a)];initializing={a,phase:Array.from(c.data.subarray(a+1,a+3)),steps:Array.from(rom.subarray(z,z+2)),env:score[role+'_retrigger']==='full'?c.r[25]:((c.data[a]&15)>>1)|c.r[25]};
  }
  if(pc===p.voice_initialized){
   assert.deepEqual(Array.from(c.data.subarray(initializing.a+1,initializing.a+3)),initializing.phase,'continuous main DDS phase');
   assert.deepEqual(Array.from(c.data.subarray(initializing.a+3,initializing.a+5)),initializing.steps,'exact main DDS pitch');
   assert.equal(c.data[initializing.a],initializing.env,'main retrigger envelope');
   initializerChecks++;initializing=null;
  }
  if(pc===p.ram_tail_copy-2){
   assert.ok(copiedSource[0]&15);tailCopies++;
   tails.push({to:c.r[30],source:copiedSource,cycles:c.cyc});
  }
  if(pc===p.no_ram_tail&&copiedSource){
   if(copiedSource[0]&15){const {to}=tails.at(-1);assert.deepEqual(Array.from(c.data.subarray(to,to+5)),copiedSource);}
   copiedSource=null;
  }
  if(pc===p.render_sample){
   renderStart=c.cyc;renderIrqs=c.irqCount;rendering=true;
   mixes++;toneContributions=[];pointSigned=0;
   if((c.data[voices[3]]&15)&&(c.data[voices[4]]&15))bothActive++;
  }
  if(pc===p.primary_gain){toneSigned=signed(c.r[17]);toneContributions.push(toneSigned);pointSigned+=toneSigned;}
  if(score.percussion_enabled&&pc===p.write_pwm-1)pointSigned+=signed(c.r[17]);
  if(pc===p.ring_published){const midpoint=(c.r[23]+c.r[21])>>1;assert.equal(c.r[16],midpoint,'Exact unsigned midpoint');const a=128|((c.r[22]-2)&15);assert.equal(c.data[a],midpoint);assert.equal(c.data[a+1],c.r[21]);}
  if(pc===p.write_pwm){
   assert.ok(pointSigned>=-128&&pointSigned<=127,`mix overflow ${pointSigned}`);
   assert.equal(signed(c.r[21]),pointSigned);
   mixMin=Math.min(mixMin,pointSigned);mixMax=Math.max(mixMax,pointSigned);
  }
 }
 if(c.inIRQ&&pc===p.ring_read){
  const queued=(c.r[22]-c.r[28]+16)%16;
  minQueued=Math.min(minQueued,queued);maxQueued=Math.max(maxQueued,queued);
  if(!queued)underruns++;
 }
 step();
 if(!c.inIRQ&&c.pc===p.idle&&entry!==null){
  const elapsed=c.cyc-entry,active=elapsed-c.maxIRQ*(c.irqCount-startIrqs);
  if(elapsed>maxElapsed){maxElapsed=elapsed;maxBurst={cycles:elapsed,active,sample:mixes};}
  maxActive=Math.max(maxActive,active);entry=null;
  if(rendering){const elapsed=c.cyc-renderStart;maxRenderCycles=Math.max(maxRenderCycles,elapsed);maxRenderActive=Math.max(maxRenderActive,elapsed-c.maxIRQ*(c.irqCount-renderIrqs));rendering=false;}
 }
 maxStack=Math.max(maxStack,159-c.minSP);
};
while(c.cyc<9600000*seconds)c.nextDuty();
assert.equal(c.lost,0);assert.equal(c.workLost,0);assert.equal(underruns,0,'PWM ring underruns');
assert.ok(c.minSP>=144,'stack must not overwrite ring');
assert.ok(tailCopies>0&&tailDecayChecks>0,'The song exercises release voices');
assert.ok(commands.length>=expected.length,'One full song and restart execute');
assert.deepEqual(commands.slice(0,expected.length).map(e=>e.byte),expected.map(e=>e.token),'Every packed musical command is preserved');
const anchor=commands[0].cycles;
const maximumTimingErrorMs=Math.max(...expected.map((e,i)=>Math.abs((commands[i].cycles-anchor)/9600-e.unit/4*60000/score.tempo_bpm)));
assert.ok(maximumTimingErrorMs<25,`${maximumTimingErrorMs}ms whole-song timing error`);
const semanticComparison={exactCommandBytes:expected.length,maximumTimingErrorMs,allFiveVoicesSilentBeforeRestart:endState.every(x=>x===0)};
const report={image:name,flashBytes:rom.length,emulatedSeconds:c.cyc/9600000,mixes,tailCopies,bothActiveRenderedPoints:bothActive,
 maxElapsedCycles:maxElapsed,maxActiveCycles:maxActive,maxBurst,maxStackBytes:maxStack,voiceRamBytes:25,pwmRingBytes:16,
 maxRenderElapsedCycles:maxRenderCycles,maxRenderActiveCycles:maxRenderActive,
 globalRamBytes:0,sramUsedWorstCase:41+maxStack,sramHighWaterReservedBytes:48+maxStack,isrCycles:c.maxIRQ,lostTimerEvents:c.lost,lostWorkEvents:c.workLost,
 ringUnderruns:underruns,minQueuedPwmBytes:minQueued,maxQueuedPwmBytes:maxQueued,mixRange:[mixMin,mixMax],
 envelopeChecks,tailDecayChecks,initializerChecks,commands:commands.length,semanticComparison};
fs.writeFileSync(`web-player/reports/${name}-release-verification.json`,JSON.stringify(report,null,2)+'\n');
fs.mkdirSync('build/release-audit',{recursive:true});fs.writeFileSync(`build/release-audit/${name}-commands.json`,JSON.stringify(commands,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
