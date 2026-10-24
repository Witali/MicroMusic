import fs from 'node:fs';
import assert from 'node:assert/strict';
// Instruction hooks run in the independent JavaScript interpreter. Crossing
// the WASM/JS boundary at every instruction makes a full 158-second audit
// needlessly expensive; the waveform render and cross-engine test use WASM.
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {createHash} from 'node:crypto';
import {pathToFileURL,fileURLToPath} from 'node:url';
export function audit(folder=fileURLToPath(new URL('../ATtiny13A/Music/variants/alicia/',import.meta.url)),{writeReport=true,log=true}={}){
const meta=JSON.parse(fs.readFileSync(folder+'/build-report.json'));
assert.equal(meta.engine,'alicia-native');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const source=JSON.parse(fs.readFileSync(new URL('../ATtiny13A/Music/reference/alicia/source-score.json',import.meta.url)));
const rom=fs.readFileSync(folder+'/synth.bin'),ep=fs.readFileSync(folder+'/eeprom.bin');
assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
assert.equal(hash(fs.readFileSync(new URL('../ATtiny13A/Music/instruments/bank.json',import.meta.url))),meta.instrumentBankSha256);
assert.deepEqual(JSON.parse(fs.readFileSync(folder+'/score.json')).native_score,source);
const c=new AVRCore(rom,ep),labels=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
// Batch only instructions between observation points. Clearing these entries
// makes runBlock stop before every semantic hook, including inside loops.
const observed=new Set([...Object.values(labels),labels.stop_companion_loop+7,labels.ring_published-2]);
for(const pc of observed)if(Number.isInteger(pc)&&pc>=0&&pc<512)c.batch[pc]=0;
const voices=[97,102,107,112,117,122],signed=n=>n<128?n:n-256;
const fraction=x=>{const [n,d=1]=String(x).split('/').map(Number);return n/d;};
const midi=x=>{if(x==='R')return null;const [,n,a,o]=/^([A-G])([#b]?)(-?\d+)$/.exec(x);return(Number(o)+1)*12+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[n]+(a==='#'?1:a==='b'?-1:0);};
const chords={Cm:[36,[55,60,63]],Fm:[41,[56,60,65]],Bb:[46,[58,62,65]],Eb:[39,[55,58,63]],C7b9:[36,[58,61,64]],Gsus4:[43,[55,60,62]],G7:[43,[55,59,62]],Abmaj7:[44,[56,60,63]],Ab:[44,[56,60,63]],Am7b5:[45,[57,60,63]],Bb7:[46,[56,62,65]],'G7/B':[47,[55,59,62]],'Bb/D':[38,[58,62,65]],'Cm/Eb':[39,[55,60,63]],Dm7b5:[38,[53,56,60]],G7b9:[43,[53,56,59]],Ddim7:[38,[53,56,59]],'Cm/G':[43,[55,60,63]],Fm7:[41,[56,60,63]],'Fm/Ab':[44,[56,60,65]],F5:[41,[53,60,65]],Cmadd9:[36,[55,62,63]]};
const expected=[],expectedComp=[];let seconds=0;
for(const name of source.playlist){const p=source.patterns[name];for(const bar of p.bars){let beat=0;for(const token of bar.melody.split(' ')){
 const [pitch,length]=token.split(':'),n=midi(pitch);if(n!==null)expected.push({pitch:n+(bar.lead_transpose??p.lead_transpose??0),instrument:bar.lead_instrument??p.lead_instrument??1,at:seconds+beat*60/p.tempo_bpm});beat+=fraction(length);
 }let cursor=0;for(const [chord,duration]of bar.chords){const [bass,tones]=chords[chord];for(const [state,pitch]of[[107,bass],[112,tones[1]]])expectedComp.push({state,pitch,at:seconds+cursor*60/p.tempo_bpm});
 for(let eighth=0;eighth<duration*2;eighth++)expectedComp.push({state:102,pitch:tones[eighth%2],at:seconds+(cursor+eighth/2)*60/p.tempo_bpm});cursor+=duration;}seconds+=beat*60/p.tempo_bpm;}}
assert.equal(expected.length,169);assert.equal(rom.length,meta.flashBytes);assert.ok(rom.length<=1024);
const queue=Array(14).fill(128),attacks=[],companion=[],envelopeChecks=[];
const expectedCommands=[];for(const phrase of meta.score.playlist){let at=meta.labels['section_'+phrase];for(;;){const token=rom[at++];expectedCommands.push(token);if(token===255)break;}}
const commands=[];let stopChecks=0;
let previous=128,latched=128,minQueued=16,maxStack=0,renderStart=null,renderIrqs=0,maxRender=0,maxBurst=0,burstStart=0,burstIrqs=0;
let initializing=null,envBefore=null,tailCapture=null,tailCopies=0,bothTails=0,contribution=0,minimumMix=127,maximumMix=-128,restarted=false,quietAtRestart=false;
const run=c.step.bind(c);
c.step=()=>{
 const at=c.pc,irq=c.inIRQ,writes=c.writes;
 if(!irq){
  if(at===labels.read_event)commands.push(rom[c.r[30]|c.r[31]<<8]);
  if(at===labels.stop_companion_loop+7){for(const state of voices.slice(1,4))assert.equal(c.data[state]&128,0,'Every companion Note Off removes its held gate');stopChecks++;}
  if(at===labels.audio_step){burstStart=c.cyc;burstIrqs=c.irqCount;}
  if(at===labels.render_sample){renderStart=c.cyc;renderIrqs=c.irqCount;contribution=0;if((c.data[117]&15)&&(c.data[122]&15))bothTails++;}
  if(at===labels.primary_gain)contribution+=signed(c.r[17]);
  if(at===labels.write_pwm){assert.equal(signed(c.r[21]),contribution);assert.ok(contribution>=-128&&contribution<=127,'No mix overflow');minimumMix=Math.min(minimumMix,contribution);maximumMix=Math.max(maximumMix,contribution);}
  if(at===labels.initialize_voice){const a=c.r[26];initializing={a,phase:Array.from(c.data.subarray(a+1,a+3)),env:c.r[25]};}
  if(at===labels.voice_initialized){
   const{a,phase,env}=initializing;assert.deepEqual(Array.from(c.data.subarray(a+1,a+3)),phase,'Unchanged DDS phase at every attack');assert.equal(c.data[a],env);
   if(a!==97)companion.push({state:a,step:c.data[a+3]|c.data[a+4]<<8,at:c.cyc/9600000});initializing=null;
  }
  if(at===labels.capture_ram_tail){const from=c.r[26],old=Array.from(c.data.subarray(from,from+5));tailCapture={from,old,target:(c.data[117]&15)<(c.data[122]&15)?117:122,before:voices.slice(4).map(a=>Array.from(c.data.subarray(a,a+5)))};}
  if(at===labels.no_ram_tail&&tailCapture){
   const{from,old,target,before}=tailCapture;
   assert.deepEqual(Array.from(c.data.subarray(from,from+5)),old,'Tail capture preserves the original complete oscillator state');
   if(old[0]&15){assert.deepEqual(Array.from(c.data.subarray(target,target+5)),[old[0]&127,...old.slice(1)],'Quietest tail receives all five old envelope/phase/frequency bytes');tailCopies++;}
   else assert.deepEqual(voices.slice(4).map(a=>Array.from(c.data.subarray(a,a+5))),before,'Silent old notes do not steal a release slot');
   assert.equal(c.r[26],from+1);tailCapture=null;
  }
  if(at===labels.lead_commit){attacks.push({step:c.data[100]|c.data[101]<<8,env:c.data[97],at:c.cyc/9600000});if(attacks.length===170)restarted=true;}
  if(at===labels.music_tick)envBefore=voices.map(a=>c.data[a]);
  if(at===labels['.L0a8']&&envBefore){
   envBefore.forEach((value,i)=>{const amp=value&15,flags=value&240;let result=value;
    if(value&128){if(value&64){let mask=amp<7?15:amp<10?7:3;if(amp&&!(c.r[24]&mask))result=value-1;}else if(amp<9)result=value+4;}
    else if(amp)result=flags|Math.max(0,amp-((value&64)?2:1));
    assert.equal(c.data[voices[i]],result,`Envelope state${i} at ${c.cyc}`);envelopeChecks.push(1);
   });envBefore=null;
  }
  if(at===labels.read_event&&(c.r[30]|c.r[31]<<8)===meta.labels.first_section&&attacks.length===169){
   assert.deepEqual(voices.map(a=>c.data[a]&143),[0,0,0,0,0,0]);quietAtRestart=true;
  }
 }
 if(irq&&at===labels.ring_read){assert.equal(queue.length,(c.r[22]-c.r[28])&15);minQueued=Math.min(minQueued,queue.length);assert.ok(queue.length>0,JSON.stringify({error:'PWM underrun',seconds:c.cyc/9600000,pc:c.pc,maxRender,maxBurst,voiceStates:voices.map(a=>Array.from(c.data.subarray(a,a+5)))}));assert.equal(c.data[c.r[28]],queue.shift());}
 if(observed.has(at)||!c.runBlock())run();
 if(!irq&&at===labels.ring_published-2){const point=c.r[21],mid=(previous+point)>>1,a=128|((c.r[22]-2)&15);assert.equal(c.data[a],mid);assert.equal(c.data[a+1],point);queue.push(mid,point);previous=point;}
 if(c.writes!==writes)assert.equal(c.duty,latched);if(irq&&at===labels.ring_read)latched=c.r[18];
 if(!c.inIRQ&&c.pc===labels.idle&&renderStart!==null){maxRender=Math.max(maxRender,c.cyc-renderStart-15*(c.irqCount-renderIrqs));maxBurst=Math.max(maxBurst,c.cyc-burstStart-15*(c.irqCount-burstIrqs));renderStart=null;}
 maxStack=Math.max(maxStack,159-c.minSP);
};
while(!restarted&&c.cyc<(seconds+1)*9600000)c.nextDuty();
assert.equal(attacks.length,170,'One entire song plus opening retrigger');assert.ok(quietAtRestart);
let maxError=0;
for(let i=0;i<169;i++){const actual=attacks[i],e=expected[i];assert.equal(actual.step,Math.round(440*2**((e.pitch-69)/12)*65536/18750));assert.equal(actual.env,e.instrument===0?206:144);maxError=Math.max(maxError,Math.abs(actual.at-attacks[0].at-e.at)*1000);}
assert.ok(maxError<30,`Melody timing error ${maxError}ms`);
assert.ok(companion.length>=expectedComp.length);
for(let i=0;i<expectedComp.length;i++){const actual=companion[i],e=expectedComp[i];assert.equal(actual.state,e.state);assert.equal(actual.step,Math.round(440*2**((e.pitch-69)/12)*65536/18750));assert.ok(Math.abs(actual.at-attacks[0].at-e.at)<.03);}
assert.equal(c.lost+c.workLost,0);assert.equal(c.maxIRQ,15);assert.ok(maxRender<=512);assert.ok(c.minSP>=144);assert.ok(tailCopies>0&&bothTails>0);
assert.deepEqual(commands.slice(0,expectedCommands.length),expectedCommands,'Every losslessly packed native command executes');
assert.ok(stopChecks>=71);
const result={image:'alicia',engine:'alicia-native',passed:true,flashBytes:rom.length,sourceNotes:169,sourceCompanionNotes:expectedComp.length,pianoArpeggioNotes:expectedComp.filter(e=>e.state===102).length,wholeSourceSeconds:seconds,emulatedSeconds:c.cyc/9600000,maximumMelodyTimingErrorMs:maxError,allSixVoicesSilentBeforeLoop:quietAtRestart,minQueued,maxRenderCycles:maxRender,maxBurstCycles:maxBurst,maxStackBytes:maxStack,tailCopies,bothTailPoints:bothTails,mixRange:[minimumMix,maximumMix],envelopeChecks:envelopeChecks.length,noteOffChecks:stopChecks,voiceRamBytes:30,pwmRingBytes:16,sramUsedWorstCase:46+maxStack,sramHighWaterReservedBytes:48+maxStack,commands:commands.length,semanticComparison:{exactCommandBytes:expectedCommands.length,allSixVoicesSilentBeforeRestart:quietAtRestart},isrCycles:c.maxIRQ,lost:c.lost+c.workLost};
result.flashSha256=hash(rom);result.eepromSha256=hash(ep);
if(writeReport){fs.mkdirSync(new URL('../web-player/reports/',import.meta.url),{recursive:true});fs.writeFileSync(new URL('../web-player/reports/alicia-release-verification.json',import.meta.url),JSON.stringify(result,null,2)+'\n');}
if(log)console.log(JSON.stringify(result,null,2));return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)audit(process.argv[2]);
