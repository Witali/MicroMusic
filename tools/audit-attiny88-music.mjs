// Execute every sample of both binaries, through a complete song and restart.
// Musical state and command order are compared on the original control clock;
// phase is deliberately excluded because the two sample rates differ.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {AVRCore as ReferenceCore} from '../web-player/lib/avr-reference.js';
import {AVRMusicTargetCore} from './avr-music-target-core.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
const readJSON=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const word=(a,p)=>a[p]|a[p+1]<<8;
const TICK_HZ=9600000/131072;
export const VARIANTS=['rhythmic','lumiere-stereo','alicia','children','turkish-march',
 'greensleeves','cancion-del-mariachi','cancion-del-mariachi-polyphonic','cancion-del-mariachi-sparse'];

function voiceLayout(name,meta){
 const poly=name.endsWith('-polyphonic')||name.endsWith('-sparse');
 const addresses=meta.voiceAddresses??meta.voices?.voiceAddresses??meta.releaseChannels?.voiceAddresses??
  (name==='rhythmic'||name==='lumiere-stereo'?[96,101,106,111,116]:name==='turkish-march'?[96,101,106]:[96,101,106,111,116,121]);
 return {addresses,poly,stepOffset:poly?2:3};
}

// Source words are decoded independently to MIDI, then rounded at the new Fs.
// Do not trust the builder's replacement values as the pitch oracle.
function retune(step){
 if(!step)return 0;
 const flag=step&0x8000,delta=step&0x7fff;
 const midi=Math.round(69+12*Math.log2(delta*18750/65536/440));
 const expected=Math.round(440*2**((midi-69)/12)*65536/15625);
 assert.ok(Math.abs(1200*Math.log2(delta*18750/65536/(440*2**((midi-69)/12))))<15,
  `Source DDS word ${step} must represent a musical semitone`);
 return expected|flag;
}

function auditTables(oldFolder,newFolder){
 const oldMeta=readJSON(path.join(oldFolder,'build-report.json')),meta=readJSON(path.join(newFolder,'build-report.json'));
 const oldRom=fs.readFileSync(path.join(oldFolder,'synth.bin')),rom=fs.readFileSync(path.join(newFolder,'synth.bin'));
 const oldEp=fs.readFileSync(path.join(oldFolder,'eeprom.bin')),ep=fs.readFileSync(path.join(newFolder,'eeprom.bin'));
 assert.equal(sha(oldRom),meta.sourceFlashSha256);assert.equal(sha(oldEp),meta.sourceEepromSha256);
 const retainedEnd=meta.labels.source_data_end??meta.labels.music_data_end;
 const retainedBytes=retainedEnd-meta.codeBytes;
 assert.ok(oldRom.length-oldMeta.codeBytes-retainedBytes>=0&&oldRom.length-oldMeta.codeBytes-retainedBytes<=1,
  'Retained table length may exclude only one assembler alignment byte');
 const expectedTables=Buffer.from(oldRom.subarray(oldMeta.codeBytes,oldMeta.codeBytes+retainedBytes)),expectedEp=Buffer.from(oldEp);
 for(const patch of meta.frequencyPatches){
  const oldData=patch.space==='flash'?oldRom:oldEp,newData=patch.space==='flash'?rom:ep;
  const expected=retune(word(oldData,patch.sourceAddress));
  assert.equal(patch.sourceWord,word(oldData,patch.sourceAddress));
  assert.equal(patch.targetWord,expected,'Builder DDS replacement agrees with independent equal-temperament calculation');
  assert.equal(word(newData,patch.targetAddress),expected,'Actual binary DDS word');
  const buffer=patch.space==='flash'?expectedTables:expectedEp;
  const offset=patch.space==='flash'?patch.targetAddress-meta.codeBytes:patch.targetAddress;
  assert.ok(offset>=0&&offset+1<buffer.length,'Frequency patch inside retained table area');
  buffer.writeUInt16LE(expected,offset);
 }
 assert.deepEqual(rom.subarray(meta.codeBytes,retainedEnd),expectedTables,'All musical tables retained byte for byte except DDS retuning');
 assert.deepEqual(ep,expectedEp,'All timbre samples retained byte for byte except sparse EEPROM DDS retuning');
 let verifiedGainCells=0;
 if(meta.amplitudeGain){
  const {address,bytes}=meta.amplitudeGain;assert.equal(address&255,0);assert.equal(bytes,256);
  for(let level=0;level<16;level++)for(let nibble=0;nibble<16;nibble++){
   const q=nibble-8,expected=meta.sourceVariant==='lumiere-stereo'?
    Math.floor(q*Math.floor(level/2)/2):Math.floor(q*level/4);
   assert.equal(rom[address+level*16+nibble],expected&255,'Amplitude gain table, signed rounding');verifiedGainCells++;
  }
 }
 if(meta.chordGain){
  const {address,bytes}=meta.chordGain;assert.equal(address&255,0);assert.equal(bytes,2048);
  for(let level=0;level<16;level++)for(let q=-64;q<64;q++){
   assert.equal(rom[address+level*128+q+64],Math.floor(q*level/8)&255,'Chord gain table, signed rounding');verifiedGainCells++;
  }
 }
 return {sourceFlashSha256:sha(oldRom),sourceEepromSha256:sha(oldEp),
  retunedWords:meta.frequencyPatches.length,retainedMusicTableBytes:retainedBytes,
  excludedSourceAlignmentBytes:oldRom.length-oldMeta.codeBytes-retainedBytes,
  allOtherMusicTableBytesIdentical:true,allWavetablesIdentical:true,independentlyVerifiedGainCells:verifiedGainCells};
}

export function trace(name,folder,{target=false,baseline=null,afterRestartTicks=74,maxSeconds=320}={}){
 const meta=readJSON(path.join(folder,'build-report.json'));
 const rom=fs.readFileSync(path.join(folder,'synth.bin')),ep=fs.readFileSync(path.join(folder,'eeprom.bin'));
 assert.equal(sha(rom),meta.flashSha256);assert.equal(sha(ep),meta.eepromSha256);
 const c=target?new AVRMusicTargetCore(rom,ep):new ReferenceCore(rom,ep);
 const cpu=target?8000000:9600000,layout=voiceLayout(name,meta),poly=layout.poly;
 const addresses=target?(meta.memory?.voiceAddresses??layout.addresses.map(a=>a<256?a+256:a)):layout.addresses;
 const p=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
 // The port's label precedes its temporary YH=1 instruction; observe LD itself.
 if(target)p.ring_read++;
 const channels=name==='lumiere-stereo'?2:1,compact=poly||name==='greensleeves';
 const producer=()=>c.r[compact?30:22],consumer=()=>c.r[28];
 const ramHigh=target?256:0,ringBase=ramHigh+(compact?96:128);
 const fifo=new Uint8Array(64);let produced=0,consumed=0,initialized=false,previous=[128,128];
 let ticks=0,tickPending=false,restartTick=null,firstTickCycle=null,done=false;
 let renderStart=null,renderIrqs=0,burstStart=null,burstIrqs=0;
 let maxRender=0,maxRenderElapsed=0,maxBurst=0,minQueued=16,maxQueued=0,underruns=0;
 let pwmPairs=0,sampleCount=0,maxActive=0,maxTickJitter=0;
 let rendering=false,currentVoice=null,phaseChecks=0,waveReadChecks=0,gainChecks=0,pendingChordGain=null;
 const snapshots=[],events=[],ticksHash=createHash('sha256'),eventsHash=createHash('sha256');
 const startWall=performance.now();
 const hookPCs=new Set(['idle','audio_step','render_sample','music_tick','read_event',
  'read_stream','classify_symbol','event_leaf','ring_published','ring_read','restart_song','next_section']
  .filter(k=>p[k]!==undefined).map(k=>p[k]));
 if(target){hookPCs.add(p.voice_loop);hookPCs.add(p.write_pwm);}
 let chordGainReturn=null;
 if(target&&meta.amplitudeGain)hookPCs.add(p.primary_gain);
 if(target&&meta.chordGain){
  hookPCs.add(p.chord_gain);
  for(let pc=p.chord_gain;pc<p.music_tick;pc++)if(word(rom,pc*2)===0x9508){chordGainReturn=pc;break;}
  assert.notEqual(chordGainReturn,null,'Chord gain return found');hookPCs.add(chordGainReturn);
 }
 // runBlock must never jump across an observation point.
 for(const pc of hookPCs)c.batch[pc]=0;
 const finishVoice=()=>{
  if(!currentVoice)return;
  const {a,phase}=currentVoice;
  assert.equal(word(c.data,a+(poly?0:1)),phase,`${name}: exact 16-bit DDS accumulation`);phaseChecks++;
  currentVoice=null;
 };
 if(target){
  const writeIO=c.writeIO.bind(c);
  c.writeIO=(address,value)=>{
   // EERE used for musical DDS loads outside rendering is checked by snapshots.
   // During synthesis its address must select the expected instrument/register
   // and the correct packed pair of the sixteen waveform points.
   if(address===0x1f&&(value&1)&&rendering&&currentVoice){
    const {index,env,phase,step}=currentVoice,high=(step&0x7fff)>=1229?8:0;
    let bank;
    if(poly)bank=(index<(name.endsWith('-sparse')?3:2)?0:16)|high;
    else if(name==='greensleeves')bank=index*16|high;
    else{
     bank=(env&48)|high;
     const attack=(name==='rhythmic'||name==='lumiere-stereo')?!!(env&16):
      name==='children'?index<2:name==='alicia'?index===0:name==='turkish-march';
     if(attack&&(env&15)>=14)bank|=48;
    }
    assert.equal(c.data[0x41],bank|(phase>>13),`${name}: instrument, octave register and wavetable index`);
    const packed=ep[bank|(phase>>13)];
    currentVoice.rawSample=((phase&4096?packed>>4:packed)&15)-8;waveReadChecks++;
   }
   return writeIO(address,value);
  };
 }
 const recordEvent=(kind,code)=>{
  const e=[ticks,kind,code];
  if(target&&baseline)assert.deepEqual(e,baseline.events[events.length],`${name}: musical command ${events.length}`);
  events.push(e);eventsHash.update(JSON.stringify(e)+'\n');
 };
 const snapshot=()=>{
  const voices=addresses.map(a=>{
   const step=word(c.data,a+layout.stepOffset);
   return poly?[target?step:retune(step)]:[c.data[a],target?step:retune(step)];
  });
  const envelopes=poly?[c.r[4],c.r[5],...(name.endsWith('-sparse')?[c.r[6]]:[])]:[];
  const state={voices,envelopes};
  if(target&&baseline)assert.deepEqual(state,baseline.snapshots[snapshots.length],`${name}: state after music tick ${ticks}`);
  snapshots.push(state);ticksHash.update(JSON.stringify(state)+'\n');
 };
 const observe=()=>{
  if(!c.inIRQ){
   if(c.pc===p.idle){
    if(!initialized){
     initialized=true;
     if(target){
      assert.equal(c.data[0x24]&(channels===2?6:4),channels===2?6:4,'OC1A/OC1B output directions');
      assert.equal(c.data[0x80],channels===2?0xa1:0x21,'Non-inverting 8-bit fast PWM');
      assert.equal(c.data[0x81],9,'Timer1 fast PWM, no prescaler');
      assert.equal(c.data[0x6f],1,'Timer1 overflow interrupt enable');
      assert.equal(c.data[0x61],0,'CPU clock prescaler /1');
      assert.equal(c.sp,767,'Initialized full 16-bit stack pointer');
     }
     const count=(producer()-consumer())&15;
     for(let i=0;i<count;i++)fifo[produced++&63]=c.data[ringBase+((consumer()+i)&15)];
    }
    if(renderStart!==null){
     const elapsed=c.cyc-renderStart,active=elapsed-c.maxIRQ*(c.irqCount-renderIrqs);
     maxRender=Math.max(maxRender,active);maxRenderElapsed=Math.max(maxRenderElapsed,elapsed);renderStart=null;
    }
    if(burstStart!==null){maxBurst=Math.max(maxBurst,c.cyc-burstStart-c.maxIRQ*(c.irqCount-burstIrqs));burstStart=null;}
   }
   if(c.pc===p.audio_step){burstStart=c.cyc;burstIrqs=c.irqCount;}
   if(c.pc===p.music_tick){
    ticks++;tickPending=true;
    if(firstTickCycle===null)firstTickCycle=c.cyc;
    maxTickJitter=Math.max(maxTickJitter,Math.abs((c.cyc-firstTickCycle)/cpu-(ticks-1)/TICK_HZ)*1000);
   }
   if(c.pc===p.render_sample){
    if(tickPending){snapshot();tickPending=false;}
    renderStart=c.cyc;renderIrqs=c.irqCount;
    maxActive=Math.max(maxActive,poly?addresses.filter((a,i)=>
     (c.r[i<(name.endsWith('-sparse')?3:2)?4:5]&15)&&word(c.data,a+2)).length:
     addresses.filter(a=>c.data[a]&15).length);
    const stopAt=target&&baseline?baseline.ticks:restartTick===null?Infinity:restartTick+afterRestartTicks;
    if(ticks>=stopAt){done=true;return;}
    sampleCount++;
    rendering=true;
   }
   if(target&&c.pc===p.voice_loop){
    finishVoice();
    const a=word(c.r,26),index=addresses.indexOf(a);assert.ok(index>=0,'Valid relocated voice pointer');
    const step=word(c.data,a+layout.stepOffset),phase=word(c.data,a+(poly?0:1));
    const delta=(name==='children'||name==='turkish-march')?step&0x7fff:step;
    currentVoice={a,index,env:poly?0:c.data[a],step,phase:(phase+delta)&65535};
   }
   if(target&&c.pc===p.write_pwm)finishVoice();
   if(target&&meta.amplitudeGain&&c.pc===p.primary_gain){
    const {env,rawSample=0}=currentVoice;let level=env&15,expected;
    if(name==='lumiere-stereo'){
     if(env&16)level>>=1;
     expected=Math.floor(rawSample*Math.floor(level/2)/2);
    }else{
     expected=Math.floor(rawSample*level/4);
     if(c.r[26]&16)expected=Math.floor(expected/2);
    }
    assert.equal(c.r[17],expected&255,'Actual lookup gain equals original signed amplitude arithmetic');gainChecks++;
   }
   if(target&&meta.chordGain&&c.pc===p.chord_gain){
    const q=c.r[21]&128?c.r[21]-256:c.r[21];pendingChordGain=Math.floor(q*c.r[25]/8)&255;
   }
   if(target&&meta.chordGain&&c.pc===chordGainReturn){
    assert.equal(c.r[17],pendingChordGain,'Actual chord lookup gain equals original signed amplitude arithmetic');gainChecks++;
   }
   if(c.pc===p.read_event)recordEvent('score',c.rom[word(c.r,30)]);
   if(c.pc===p.read_stream){
    const address=name==='greensleeves'?word(c.r,2):meta.labels.song_stream+c.r[16];
    recordEvent('stream',c.rom[address]);
   }
   if(c.pc===p.classify_symbol)recordEvent('symbol',c.r[21]);
   if(c.pc===p.event_leaf)recordEvent('leaf',c.r[21]);
   if(c.pc===p.restart_song&&restartTick===null)restartTick=ticks;
   if(c.pc===p.next_section&&c.r[4]===0&&restartTick===null)restartTick=ticks;
   if(c.pc===p.ring_published){
    rendering=false;
    assert.equal(c.r[compact?31:27],target?1:0,'FIFO publication pointer high byte');
    const bytes=2*channels,start=(producer()-bytes)&15,current=[];
    for(let ch=0;ch<channels;ch++){
     const mid=c.data[ringBase+((start+ch)&15)],point=c.data[ringBase+((start+channels+ch)&15)];
     assert.equal(mid,(previous[ch]+point)>>1,`${name}: sample midpoint, channel ${ch}`);
     previous[ch]=point;current.push(mid);
    }
    for(let i=0;i<bytes;i++)fifo[produced++&63]=c.data[ringBase+((start+i)&15)];
    assert.ok(produced-consumed<=16,`${name}: FIFO overwrite`);pwmPairs++;
   }
  }else if(c.pc===p.ring_read){
   assert.equal(c.r[29],target?1:0,'ISR FIFO pointer high byte');
   if(target){assert.equal(c.data[0x89],0,'OCR1A high byte');assert.equal(c.data[0x8b],0,'OCR1B high byte');}
   const queued=produced-consumed;minQueued=Math.min(minQueued,queued);maxQueued=Math.max(maxQueued,queued);
   if(queued<channels)underruns++;
   assert.ok(queued>=channels,`${name}: FIFO underrun at cycle ${c.cyc}; samples=${pwmPairs}, tick=${ticks}, max render=${maxRender} active/${maxRenderElapsed} elapsed cycles, max control/render=${maxBurst}`);
   for(let i=0;i<channels;i++)assert.equal(c.data[ringBase+((consumer()+i)&15)],fifo[consumed++&63],`${name}: FIFO order`);
  }
 };
 while(!done&&c.cyc<maxSeconds*cpu){
  if(hookPCs.has(c.pc)){
   observe();if(done)break;
   if(!(c.fastIdle&&c.idle[c.pc]&&c.skipIdle()))c.step();
  }else if(!(c.fastIdle&&c.idle[c.pc]&&c.skipIdle())&&!c.runBlock())c.step();
 }
 assert.ok(done,`${name}: full song and restart must finish in ${maxSeconds} seconds`);
 assert.notEqual(restartTick,null,`${name}: restart reached`);
 assert.equal(underruns+c.lost+c.workLost,0,`${name}: uninterrupted PWM and foreground work`);
 assert.ok(maxRender<512,`${name}: render budget ${maxRender} cycles`);
 assert.ok(maxTickJitter<0.3,`${name}: control clock jitter ${maxTickJitter.toFixed(3)} ms`);
 if(target&&baseline){
  assert.equal(snapshots.length,baseline.snapshots.length);assert.equal(events.length,baseline.events.length);
  assert.equal(restartTick,baseline.restartTick,'Identical song restart on the musical control clock');
 }
 const result={ticks,restartTick,snapshots,events,report:{
  flashSha256:sha(rom),eepromSha256:sha(ep),
  simulatedSeconds:c.cyc/cpu,controlTicks:ticks,firstRestartControlTick:restartTick,
  postRestartControlTicks:afterRestartTicks,snapshotSha256:ticksHash.digest('hex'),
  musicalCommands:events.length,commandSha256:eventsHash.digest('hex'),synthesisSamples:sampleCount,
  checkedPwmPairs:pwmPairs,channels,maxActiveVoiceStates:maxActive,fifoUnderruns:underruns,
  independentlyCheckedDDSPhases:phaseChecks,independentlyCheckedWavetableReads:waveReadChecks,
  independentlyCheckedLookupGains:gainChecks,
  minimumQueuedBytes:minQueued,maximumQueuedBytes:maxQueued,maxRenderActiveCycles:maxRender,
  maxRenderElapsedCycles:maxRenderElapsed,maxControlAndRenderActiveCycles:maxBurst,
  maxControlTickJitterMs:maxTickJitter,maxISRCycles:c.maxIRQ,lostTimerEvents:c.lost,lostWorkEvents:c.workLost,
  minimumStackPointer:c.minSP,maxStackBytes:(target?767:159)-c.minSP,
  auditWallSeconds:(performance.now()-startWall)/1000,
 }};
 return result;
}

export function audit(name,{writeReport=true,log=true,maxSeconds=320}={}){
 assert.ok(VARIANTS.includes(name),'Unknown variant: '+name);
 const oldFolder=path.join(root,'ATtiny13A/Music/variants',name),newFolder=path.join(root,'ATtiny88/Music/variants',name);
 const tables=auditTables(oldFolder,newFolder);
 if(log)console.log(`${name}: executing complete ATtiny13A reference song`);
 const baseline=trace(name,oldFolder,{maxSeconds});
 if(log)console.log(`${name}: executing complete ATtiny88 port song (${baseline.ticks} control ticks)`);
 const port=trace(name,newFolder,{target:true,baseline,maxSeconds});
 const result={target:'ATtiny88',variant:name,method:'All CPU samples, complete song plus one second of restart',
  musicalStateCompared:'Every control tick: all voice envelopes and independently retuned DDS words; all score and expanded grammar commands in order',
  samplePhaseCompared:false,phaseReason:'Sample rate changes from 18750 to 15625 Hz; phase positions therefore differ',
  allMusicalStatesMatch:true,allMusicalCommandsMatch:true,tables,original:baseline.report,port:port.report};
 assert.equal(result.original.snapshotSha256,result.port.snapshotSha256);
 assert.equal(result.original.commandSha256,result.port.commandSha256);
 if(writeReport)fs.writeFileSync(path.join(newFolder,'verification.json'),JSON.stringify(result,null,2)+'\n');
 if(log)console.log(JSON.stringify(result,null,2));return result;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const requested=process.argv.slice(2),names=requested.length?requested:VARIANTS;
 for(const name of names)audit(name);
}
