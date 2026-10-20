import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';

const signed=n=>n&128?n-256:n;
const halfEven=x=>{const f=Math.floor(x),d=x-f;return d===.5?f+(f&1):Math.round(x);};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function sourceNotes(source,track){
 const result=[],active=new Map();
 for(const event of source.tracks.find(t=>t.index===track).events){
  if(!['noteOn','noteOff'].includes(event.type))continue;
  const key=event.channel+':'+event.note,list=active.get(key)??[];
  if(event.type==='noteOn'&&event.velocity>0)list.push(event.tick);
  else if(list.length){const start=list.shift();if(event.tick>start)result.push({pitch:event.note,unit:halfEven(start*4/source.ppqn),off:Math.max(halfEven(start*4/source.ppqn)+1,halfEven(event.tick*4/source.ppqn))});}
  active.set(key,list);
 }
 return result.filter(n=>n.unit<1712).sort((a,b)=>a.unit-b.unit);
}

export function audit(folder='build/children-four'){
 const read=name=>fs.readFileSync(path.join(folder,name));
 const production=fs.existsSync(path.join(folder,'build-report.json'));
 const stored=JSON.parse(read(production?'build-report.json':'feasibility.json')),meta=stored.native??stored,{labels,metadata}=meta;
 const rom=read('synth.bin'),ep=read('eeprom.bin'),raw=meta.sourceStream?Buffer.from(meta.sourceStream):read('source-stream.bin');
 const sourceBytes=fs.readFileSync('ATtiny13A/Music/reference/children/source-events.json');
 assert.equal(hash(sourceBytes),meta.sourceSha256);
 const source=JSON.parse(sourceBytes),lead=sourceNotes(source,1),bass=sourceNotes(source,4);
 assert.equal(lead.length,256);assert.equal(bass.length,345);
 assert.ok(rom.length<=1024);assert.equal(ep.length,64);
 const p=Object.fromEntries(Object.entries(labels).map(([name,value])=>[name,value/2]));
 const addresses=[97,102,107,112,117,122],durations=[1,2,3,4,6,8,16];
 const expected=[];let unit=0;
 for(let index=0;index<labels.PLAYLIST_LEN;index++){
  let at=labels.melody_data+rom[labels.playlist+index];
  for(;;){const token=rom[at++];expected.push({token,unit});if(token===255)break;if(token<151)unit+=durations[token&7];}
 }
 assert.equal(unit,1728);assert.deepEqual(Buffer.from(expected.filter(e=>e.token!==255).map(e=>e.token)),raw);
 const model=(value,clock,fast)=>{
  const level=value&15,flags=value&240;
  if(value&128){
   if(value&32)return flags|Math.min(7,level+Number(!(clock&1)));
   let mask=level>=10?3:level>=7?7:15;if(fast)mask>>=2;
   return flags|Math.max(0,level-Number(!(clock&mask)));
  }
  if(value&32&&clock&7)return value;
  return flags|Math.max(0,level-((value&64)?2:1));
 };
 const c=new AVRCore(rom,ep),step=c.step.bind(c),onsets=[[],[],[],[]];
 let grid=-1,commands=[],before=null,envelopeChecks=0,tailChecks=0,copied=null,initializing=null,initializerChecks=0;
 let tailCopies=0,bothTails=0,sixActive=0,maxStack=0,underruns=0,minQueued=16,maxQueued=0,mixes=0,mixMin=127,mixMax=-128,sum=0;
 let render=null,maxRender=0,maxRenderActive=0,event=null,maxBurst=0,maxBurstActive=0,loopSilent=[],waveChecks=0,gateChecks=0;
 let previousGates=[false,false,false,false];
 const releases=[[],[],[],[]];
 c.step=()=>{
  if(!c.inIRQ){
   const pc=c.pc;
   if(pc===p.audio_step)event={cycle:c.cyc,irq:c.irqCount};
   if(pc===p.grid_step)grid++;
   if(pc===p.music_tick)before=addresses.map(a=>c.data[a]);
   if(pc===p['.L0a8']&&before){
    addresses.forEach((a,i)=>{assert.equal(c.data[a],model(before[i],c.r[24],!!(c.data[a+4]&128)),`envelope voice ${i}, clock ${c.r[24]}, before ${before[i]}, grid ${grid}`);envelopeChecks++;if(i>=4&&(before[i]&15))tailChecks++;});before=null;
   }
   if(pc===p.read_event){
    const token=rom[c.r[30]|c.r[31]<<8];
    commands.push({token,cycles:c.cyc,grid});
    if(commands.length%expected.length===1&&commands.length>1){
     const state=addresses.map(a=>c.data[a]&15);assert.deepEqual(state,[0,0,0,0,0,0],'Every main voice and both tails finish before restart');loopSilent.push(state);
     console.error(`Children native: completed loop ${loopSilent.length} at ${(c.cyc/9600000).toFixed(3)}s`);
    }
   }
   if(pc===p.initialize_voice){
    const a=c.r[26],i=addresses.indexOf(a),z=c.r[30]|c.r[31]<<8,steps=Array.from(rom.subarray(z,z+2));
    assert.ok(i>=0&&i<4);
    const pitch=metadata.pitches[(z-labels.note_steps)/2];
    assert.ok(Number.isInteger(pitch));
    onsets[i].push({unit:grid,pitch,cycles:c.cyc});
    initializing={a,phase:Array.from(c.data.subarray(a+1,a+3)),steps,env:((c.data[a]&15)>>1)|c.r[25]};
   }
   if(pc===p.voice_initialized){
    assert.deepEqual(Array.from(c.data.subarray(initializing.a+1,initializing.a+3)),initializing.phase,'Continuous DDS phase');
    assert.deepEqual(Array.from(c.data.subarray(initializing.a+3,initializing.a+5)),initializing.steps,'Exact DDS step plus decay flag');
    assert.equal(c.data[initializing.a],initializing.env,'Peak/half retrigger');initializerChecks++;initializing=null;
   }
   if(pc===p.capture_ram_tail){const a=c.r[26];copied={source:Array.from(c.data.subarray(a,a+5)),to:null};copied.source[0]&=127;}
   if(pc===p.ram_tail_destination&&copied)copied.to=c.r[30];
   if(pc===p.no_ram_tail&&copied){if(copied.source[0]&15){assert.deepEqual(Array.from(c.data.subarray(copied.to,copied.to+5)),copied.source,'Exact old phase/pitch/flags tail copy');tailCopies++;}copied=null;}
   if(pc===p.render_sample){render={cycle:c.cyc,irq:c.irqCount};mixes++;sum=0;if(addresses.every(a=>c.data[a]&15))sixActive++;if((c.data[117]&15)&&(c.data[122]&15))bothTails++;}
   if(pc===p.primary_gain){
    const a=c.r[26]-5,index=addresses.indexOf(a),value=c.data[a],level=value&15;
    let wave=0;
    if(level){let bank=value&48;if(index<2&&level>=14)bank=48;const slot=bank|((c.data[a+4]&127)>=4?8:0),point=c.data[a+2]>>4,byte=ep[slot+(point>>1)];wave=((point&1)?byte>>4:byte&15)-8;}
    let tone=(wave*level)>>2;if(index>=2)tone>>=1;
    assert.equal(signed(c.r[17]),tone,`EEPROM waveform/phase/gain voice ${index}`);waveChecks++;sum+=tone;
   }
   if(pc===p.write_pwm){assert.ok(sum>=-128&&sum<=127,`Mix overflow ${sum}`);assert.equal(signed(c.r[21]),sum);mixMin=Math.min(mixMin,sum);mixMax=Math.max(mixMax,sum);
    for(let i=0;i<4;i++){const gate=!!(c.data[addresses[i]]&128);if(previousGates[i]&&!gate)releases[i].push(grid);previousGates[i]=gate;}
   }
   if(pc===p.ring_published){const midpoint=(c.r[23]+c.r[21])>>1,a=128|((c.r[22]-2)&15);assert.equal(c.r[16],midpoint);assert.equal(c.data[a],midpoint);assert.equal(c.data[a+1],c.r[21]);}
  }
  if(c.inIRQ&&c.pc===p.ring_read){const queued=(c.r[22]-c.r[28]+16)%16;minQueued=Math.min(minQueued,queued);maxQueued=Math.max(maxQueued,queued);if(!queued)underruns++;}
  step();
  if(!c.inIRQ&&c.pc===p.idle){
   if(render){const elapsed=c.cyc-render.cycle;maxRender=Math.max(maxRender,elapsed);maxRenderActive=Math.max(maxRenderActive,elapsed-c.maxIRQ*(c.irqCount-render.irq));render=null;}
   if(event){const elapsed=c.cyc-event.cycle;maxBurst=Math.max(maxBurst,elapsed);maxBurstActive=Math.max(maxBurstActive,elapsed-c.maxIRQ*(c.irqCount-event.irq));event=null;}
  }
  maxStack=Math.max(maxStack,159-c.minSP);
 };
 // Two complete passes expose stale macro counters and non-silent restarts.
 while(commands.length<expected.length*2+2&&c.cyc<9600000*372)c.nextDuty();
 assert.ok(commands.length>=expected.length*2+2,'Two whole songs and restart finish within their source duration');
 assert.equal(c.lost+c.workLost,0);assert.equal(underruns,0);assert.ok(c.minSP>=144);assert.ok(maxRender<512);assert.ok(sixActive>0&&tailCopies>0&&loopSilent.length>=2);
 let maximumTimingErrorMs=0,sourceLeadGateChecks=0;
 for(let loop=0;loop<2;loop++){
  const commandsAt=commands.slice(loop*expected.length,(loop+1)*expected.length),anchor=commandsAt[0].cycles;
  assert.deepEqual(commandsAt.map(e=>e.token),expected.map(e=>e.token),'Lossless dictionary command replay');
  for(let i=0;i<expected.length;i++)assert.equal(commandsAt[i].grid,expected[i].unit+loop*1728,'Every command remains on its grid');
  const maxError=Math.max(...commandsAt.map((e,i)=>Math.abs((e.cycles-anchor)/9600-expected[i].unit/4*60000/140)));
  maximumTimingErrorMs=Math.max(maximumTimingErrorMs,maxError);
  assert.ok(maxError<25,`Timing error ${maxError} ms`);
  for(const [index,wanted] of [[0,[...lead,{unit:1712,pitch:65}]],[2,[...bass,{unit:1712,pitch:29}]]]){
   const actual=onsets[index].filter(e=>e.unit>=loop*1728&&e.unit<(loop+1)*1728).map(e=>({unit:e.unit-loop*1728,pitch:e.pitch}));
   assert.deepEqual(actual,wanted.map(({unit,pitch})=>({unit,pitch})),`Source ${index===0?'256 piano':'345 bass'} note attacks preserved`);
  }
  for(const note of bass){const next=onsets[2].find(e=>e.unit>note.unit+loop*1728);assert.equal(next.unit-loop*1728,note.off,'Selected source bass NoteOff equals next native onset');gateChecks++;}
  for(const note of lead){const next=onsets[0].find(e=>e.unit>note.unit+loop*1728);if(note.off<next.unit-loop*1728)assert.ok(releases[0].includes(note.off+loop*1728),'Every main-piano gap receives its source NoteOff');else assert.equal(note.off,next.unit-loop*1728,'Contiguous piano note gate ends at atomic replacement');sourceLeadGateChecks++;}
  for(const echo of onsets[1].filter(e=>e.unit>=loop*1728&&e.unit<(loop+1)*1728))assert.ok(releases[1].includes(echo.unit+2),'Echo eighth gate ends exactly');
  assert.ok(releases[2].includes(loop*1728+1716),'Bass cadence finite gate');assert.ok(releases[3].includes(loop*1728+1716),'Pad cadence finite gate');
  assert.ok(!onsets[3].some(e=>e.unit>=loop*1728&&e.unit<loop*1728+128),'Pad initial silence is reset every loop');
 }
 const report={engine:'children-native',flashBytes:rom.length,codeBytes:labels.code_end,emulatedSeconds:c.cyc/9600000,mainVoices:4,releaseVoices:2,
  sourceLeadNotes:lead.length,sourceBassNotes:bass.length,leadAndBassExactOnNearestSixteenthGrid:true,completeSourceQuarterBeats:428,cadenceQuarterBeats:4,
  mainVoiceOnsetsPerLoop:onsets.map(events=>events.filter(e=>e.unit<1728).length),sourceEchoReduction:metadata.limitation,
  waveformChecks:waveChecks,envelopeChecks,initializerChecks,sourceBassGateChecks:gateChecks,sourceLeadGateChecks,tailChecks,tailDecayChecks:tailChecks,tailCopies,sixActiveRenderedPoints:sixActive,bothTailsActiveRenderedPoints:bothTails,bothActiveRenderedPoints:bothTails,
  maxRenderElapsedCycles:maxRender,maxRenderActiveCycles:maxRenderActive,maxEventBurstCycles:maxBurst,maxEventActiveCycles:maxBurstActive,isrCycles:c.maxIRQ,
  ringUnderruns:underruns,lostTimerEvents:c.lost,lostWorkEvents:c.workLost,minQueuedPwmBytes:minQueued,maxQueuedPwmBytes:maxQueued,mixRange:[mixMin,mixMax],
  maxStackBytes:maxStack,voiceStateBytes:30,voiceRamBytes:30,pwmRingBytes:16,globalRamBytes:0,activeSramBytes:46+maxStack,sramUsedWorstCase:46+maxStack,sramHighWaterReservedBytes:48+maxStack,allSixVoicesSilentBeforeEachRestart:true,verifiedLoops:2,
  maxElapsedCycles:maxBurst,maxActiveCycles:maxBurstActive,mixes,semanticComparison:{exactCommandBytes:expected.length,maximumTimingErrorMs,allSixVoicesSilentBeforeRestart:true},
  romSha256:hash(rom),eepromSha256:hash(ep),sourceSha256:hash(sourceBytes)};
 fs.writeFileSync(production?'web-player/reports/children-release-verification.json':path.join(folder,'native-verification.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report,null,2));return report;
}
if(process.argv[1]&&path.resolve(process.argv[1])===path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1')))audit(process.argv[2]);
