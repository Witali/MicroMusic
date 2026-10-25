// Execute every sample of both binaries, through a complete song and restart.
// Musical state and command order are compared on the original control clock;
// phase is deliberately excluded because the two sample rates differ.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {AVRCore as ReferenceCore} from '../web-player/lib/avr-reference.js';
import {AVRCore as WasmCore} from '../web-player/lib/avr-core.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
const readJSON=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const word=(a,p)=>a[p]|a[p+1]<<8;
const TICK_HZ=9600000/131072;
export const MICRONUCLEUS_BOARD='mh-et-live-16mhz';
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
function retune(step,synthesisHz=15625){
 if(!step)return 0;
 const flag=step&0x8000,delta=step&0x7fff;
 const midi=Math.round(69+12*Math.log2(delta*18750/65536/440));
 const expected=Math.round(440*2**((midi-69)/12)*65536/synthesisHz);
 assert.ok(Math.abs(1200*Math.log2(delta*18750/65536/(440*2**((midi-69)/12))))<15,
  `Source DDS word ${step} must represent a musical semitone`);
 return expected|flag;
}

function auditTables(oldFolder,newFolder){
 const oldMeta=readJSON(path.join(oldFolder,'build-report.json')),meta=readJSON(path.join(newFolder,'build-report.json'));
 const oldRom=fs.readFileSync(path.join(oldFolder,'synth.bin')),rom=fs.readFileSync(path.join(newFolder,'synth.bin'));
 const oldEp=fs.readFileSync(path.join(oldFolder,'eeprom.bin'));
 const embedded=meta.wavetableStorage?.space==='flash',bank=meta.wavetableStorage;
 const ep=embedded?rom.subarray(bank.address,bank.address+bank.bytes):fs.readFileSync(path.join(newFolder,'eeprom.bin'));
 if(embedded){
  assert.equal(bank.bytes,64);assert.equal(bank.alignment,256);assert.equal(bank.address&255,0);
  assert.equal(ep.length,64);assert.equal(sha(ep),bank.sha256);assert.equal(meta.eepromBytes,0);
  assert.ok(rom.length<=meta.applicationFlashLimit,'Firmware stays below the Micronucleus application limit');
 }
 assert.equal(sha(oldRom),meta.sourceFlashSha256);assert.equal(sha(oldEp),meta.sourceEepromSha256);
 const retainedEnd=meta.labels.source_data_end??meta.labels.music_data_end;
 const retainedBytes=retainedEnd-meta.codeBytes;
 assert.ok(oldRom.length-oldMeta.codeBytes-retainedBytes>=0&&oldRom.length-oldMeta.codeBytes-retainedBytes<=1,
  'Retained table length may exclude only one assembler alignment byte');
 const expectedTables=Buffer.from(oldRom.subarray(oldMeta.codeBytes,oldMeta.codeBytes+retainedBytes)),expectedEp=Buffer.from(oldEp);
 for(const patch of meta.frequencyPatches){
  const oldData=patch.space==='flash'?oldRom:oldEp;
  const targetSpace=patch.targetSpace??patch.space,newData=targetSpace==='flash'?rom:ep;
  const expected=retune(word(oldData,patch.sourceAddress),meta.synthesisHz);
  assert.equal(patch.sourceWord,word(oldData,patch.sourceAddress));
  assert.equal(patch.targetWord,expected,'Builder DDS replacement agrees with independent equal-temperament calculation');
  assert.equal(word(newData,patch.targetAddress),expected,'Actual binary DDS word');
  const buffer=patch.space==='flash'?expectedTables:expectedEp;
  const offset=patch.space==='flash'?patch.targetAddress-meta.codeBytes:patch.sourceAddress;
  if(embedded&&patch.space==='eeprom'){
   assert.equal(targetSpace,'flash');assert.equal(patch.targetAddress,bank.address+patch.sourceAddress);
  }
  assert.ok(offset>=0&&offset+1<buffer.length,'Frequency patch inside retained table area');
  buffer.writeUInt16LE(expected,offset);
 }
 assert.deepEqual(rom.subarray(meta.codeBytes,retainedEnd),expectedTables,'All musical tables retained byte for byte except DDS retuning');
 assert.deepEqual(ep,expectedEp,'All timbre samples retained byte for byte except sparse DDS retuning');
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
  allOtherMusicTableBytesIdentical:true,allWavetablesIdentical:true,independentlyVerifiedGainCells:verifiedGainCells,
  ...(embedded?{wavetableStorage:'flash',embeddedBankAddress:bank.address,embeddedBankSha256:sha(ep),eepromRequired:false}:{})};
}

export function trace(name,folder,{target=false,baseline=null,afterRestartTicks=74,maxSeconds=320,engine='js',targetSynthesisHz=15625}={}){
 const meta=readJSON(path.join(folder,'build-report.json'));
 const embedded=meta.wavetableStorage?.space==='flash',bank=meta.wavetableStorage;
 const rom=fs.readFileSync(path.join(folder,'synth.bin'));
 const ep=embedded?rom.subarray(bank.address,bank.address+bank.bytes):fs.readFileSync(path.join(folder,'eeprom.bin'));
 assert.equal(sha(rom),meta.flashSha256);assert.equal(sha(ep),embedded?bank.sha256:meta.eepromSha256);
 assert.ok(['js','wasm'].includes(engine),'Unknown audit engine');
 const Core=engine==='wasm'?WasmCore:ReferenceCore;
 const cpu=meta.cpuHz??(target?8000000:9600000);
 const highStepThreshold=Math.round(1024*18750/(meta.synthesisHz??15625));
 if(embedded)assert.equal(meta.wavetableHighStepThreshold,highStepThreshold,'Independently scaled octave-bank threshold');
 // USB programming transfers Flash only. Execute with erased EEPROM to prove
 // that no retained note or sample depends on separately programmed EEPROM.
 const c=new Core(rom,embedded?new Uint8Array(64).fill(255):ep,{target:target?'attiny88':'attiny13a',cpuHz:cpu});
 const layout=voiceLayout(name,meta),poly=layout.poly;
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
 let executedFlashBankReads=0,executedEepromReads=0;
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
 // Observe the actual EERE instruction in both executors. Native instructions
 // call C's internal I/O handler; overriding the JS bridge cannot observe it.
 // EEAR and voice phase remain stable through the synchronous SBI bus access.
 const eepromReadPCs=new Set(),flashBankReadPCs=new Set();
 if(target){
  for(let pc=0;pc<meta.codeBytes/2;pc++)if(word(rom,pc*2)===0x9af8){
   eepromReadPCs.add(pc);hookPCs.add(pc);
  }
  if(embedded){
   assert.equal(eepromReadPCs.size,0,'Flash-only firmware contains no EERE instruction');
   for(const [label,byteAddress]of Object.entries(meta.labels))if(/^tiny88_flash_read_\d+$/.test(label)){
    const pc=byteAddress/2,w=word(rom,byteAddress);
    assert.equal(w&0xfe0f,0x9004,'Embedded-bank label identifies an actual LPM instruction');
    flashBankReadPCs.add(pc);hookPCs.add(pc);
   }
   assert.ok(flashBankReadPCs.size>0,'Actual embedded-bank LPM instructions located');
  }else assert.ok(eepromReadPCs.size>0,'Target EEPROM-read instruction located');
 }
 // runBlock must never jump across an observation point.
 for(const pc of hookPCs)c.batch[pc]=0;
 const finishVoice=()=>{
  if(!currentVoice)return;
  const {a,phase}=currentVoice;
  assert.equal(word(c.data,a+(poly?0:1)),phase,`${name}: exact 16-bit DDS accumulation`);phaseChecks++;
  currentVoice=null;
 };
 const observeWaveRead=()=>{
   // EERE used for musical DDS loads outside rendering is checked by snapshots.
   // During synthesis its address must select the expected instrument/register
   // and the correct packed pair of the sixteen waveform points.
   if(rendering&&currentVoice){
    const {index,env,phase,step}=currentVoice,high=(step&0x7fff)>=highStepThreshold?8:0;
    let waveBank;
    if(poly)waveBank=(index<(name.endsWith('-sparse')?3:2)?0:16)|high;
    else if(name==='greensleeves')waveBank=index*16|high;
    else{
     waveBank=(env&48)|high;
     const attack=(name==='rhythmic'||name==='lumiere-stereo')?!!(env&16):
      name==='children'?index<2:name==='alicia'?index===0:name==='turkish-march';
     if(attack&&(env&15)>=14)waveBank|=48;
    }
    const indexInBank=waveBank|(phase>>13);
    assert.equal(embedded?word(c.r,30)-bank.address:c.data[0x41],indexInBank,`${name}: instrument, octave register and wavetable index`);
    const packed=ep[indexInBank];
    currentVoice.rawSample=((phase&4096?packed>>4:packed)&15)-8;waveReadChecks++;
   }
 };
 const recordEvent=(kind,code)=>{
  const e=[ticks,kind,code];
  if(target&&baseline)assert.deepEqual(e,baseline.events[events.length],`${name}: musical command ${events.length}`);
  events.push(e);eventsHash.update(JSON.stringify(e)+'\n');
 };
 const snapshot=()=>{
  const voices=addresses.map(a=>{
   const step=word(c.data,a+layout.stepOffset);
   return poly?[target?step:retune(step,targetSynthesisHz)]:[c.data[a],target?step:retune(step,targetSynthesisHz)];
  });
  const envelopes=poly?[c.r[4],c.r[5],...(name.endsWith('-sparse')?[c.r[6]]:[])]:[];
  const state={voices,envelopes};
  if(target&&baseline)assert.deepEqual(state,baseline.snapshots[snapshots.length],`${name}: state after music tick ${ticks}`);
  snapshots.push(state);ticksHash.update(JSON.stringify(state)+'\n');
 };
 const observe=()=>{
  if(!c.inIRQ){
   if(flashBankReadPCs.has(c.pc))executedFlashBankReads++;
   if(eepromReadPCs.has(c.pc))executedEepromReads++;
   if(eepromReadPCs.has(c.pc)||flashBankReadPCs.has(c.pc))observeWaveRead();
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
 if(target){
  assert.ok(phaseChecks>0&&waveReadChecks>0,'Executed DDS and wavetable-read observations');
  if(meta.amplitudeGain||meta.chordGain)assert.ok(gainChecks>0,'Executed gain observations');
  if(embedded){
   assert.ok(executedFlashBankReads>0,'Executed actual Flash-bank LPM reads');
   assert.equal(executedEepromReads,0);assert.ok(c.eeprom.every(byte=>byte===255),'EEPROM remains erased');
  }
 }
 assert.notEqual(restartTick,null,`${name}: restart reached`);
 assert.equal(underruns+c.lost+c.workLost,0,`${name}: uninterrupted PWM and foreground work`);
 assert.ok(maxRender<512,`${name}: render budget ${maxRender} cycles`);
 assert.ok(maxTickJitter<0.3,`${name}: control clock jitter ${maxTickJitter.toFixed(3)} ms`);
 if(target&&baseline){
  assert.equal(snapshots.length,baseline.snapshots.length);assert.equal(events.length,baseline.events.length);
  assert.equal(restartTick,baseline.restartTick,'Identical song restart on the musical control clock');
 }
 const result={ticks,restartTick,snapshots,events,report:{
  flashSha256:sha(rom),eepromSha256:embedded?null:sha(ep),
  ...(embedded?{embeddedBankSha256:sha(ep),eepromRequired:false,erasedEepromSha256:sha(c.eeprom),
    staticFlashBankReadSites:flashBankReadPCs.size,executedFlashBankReads,
    staticEepromReadSites:eepromReadPCs.size,executedEepromReads}:{}),
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

export function audit(name,{writeReport=true,log=true,maxSeconds=320,engine='js',board=null}={}){
 assert.ok(VARIANTS.includes(name),'Unknown variant: '+name);
 assert.ok(board===null||board===MICRONUCLEUS_BOARD,'Unknown board: '+board);
 const oldFolder=path.join(root,'ATtiny13A/Music/variants',name),newFolder=path.join(root,'ATtiny88/Music',board?'variants-micronucleus':'variants',name);
 const meta=readJSON(path.join(newFolder,'build-report.json'));
 if(board){
  assert.equal(meta.board,board);assert.equal(meta.cpuHz,16000000);
  assert.equal(meta.pwmHz,62500);assert.equal(meta.synthesisHz,31250);
  assert.equal(meta.controlClock.virtualSamples,3);assert.equal(meta.controlClock.physicalSamples,5);
  assert.equal(meta.controlTickHz,TICK_HZ);assert.equal(meta.applicationFlashLimit,6012);
 }
 const targetSynthesisHz=meta.synthesisHz;
 const tables=auditTables(oldFolder,newFolder);
 if(log)console.log(`${name}: executing complete ATtiny13A reference song`);
 const baseline=trace(name,oldFolder,{maxSeconds,engine,targetSynthesisHz});
 if(log)console.log(`${name}: executing complete ATtiny88 port song (${baseline.ticks} control ticks)`);
 const port=trace(name,newFolder,{target:true,baseline,maxSeconds,engine,targetSynthesisHz});
 const result={target:'ATtiny88',variant:name,method:'All CPU samples, complete song plus one second of restart',
  musicalStateCompared:'Every control tick: all voice envelopes and independently retuned DDS words; all score and expanded grammar commands in order',
  samplePhaseCompared:false,phaseReason:`Sample rate changes from 18750 to ${targetSynthesisHz} Hz; phase positions therefore differ`,
  ...(board?{board,engine,cpuHz:meta.cpuHz,pwmHz:meta.pwmHz,synthesisHz:meta.synthesisHz,
    modelsOnly:true,electricalPwmEdgesMeasured:false,eepromRequired:false}:{}),
  allMusicalStatesMatch:true,allMusicalCommandsMatch:true,tables,original:baseline.report,port:port.report};
 assert.equal(result.original.snapshotSha256,result.port.snapshotSha256);
 assert.equal(result.original.commandSha256,result.port.commandSha256);
 if(writeReport)fs.writeFileSync(path.join(newFolder,'verification.json'),JSON.stringify(result,null,2)+'\n');
 if(log)console.log(JSON.stringify(result,null,2));return result;
}

export function writeBoardReport(results,output,{engine='wasm'}={}){
 assert.equal(results.length,VARIANTS.length,'Board report covers all nine arrangements');
 assert.deepEqual([...new Set(results.map(r=>r.variant))].sort(),[...VARIANTS].sort());
 const baseline=readJSON(path.join(root,'tools/fixtures/attiny-music-startup-baseline.json'));
 const hashSource=file=>sha(file.endsWith('.wasm')?fs.readFileSync(path.join(root,file)):
  fs.readFileSync(path.join(root,file),'utf8').replace(/\r\n/g,'\n'));
 const sources=['web-player/lib/avr-profiles.js','web-player/lib/avr-reference.js',
  'web-player/lib/avr-wasm.js','web-player/native/avr.c','web-player/wasm/avr.wasm',
  'tools/audit-attiny88-music.mjs','tools/build-attiny88-music.py'];
 for(const result of results){
  assert.equal(result.board,MICRONUCLEUS_BOARD);assert.equal(result.engine,engine);
  assert.equal(result.allMusicalStatesMatch,true);assert.equal(result.allMusicalCommandsMatch,true);
  assert.equal(result.tables.allOtherMusicTableBytesIdentical,true);assert.equal(result.tables.allWavetablesIdentical,true);
  const folder=path.join(root,'ATtiny88/Music/variants-micronucleus',result.variant),meta=readJSON(path.join(folder,'build-report.json'));
  assert.equal(result.port.flashSha256,sha(fs.readFileSync(path.join(folder,'synth.bin'))));
  assert.equal(result.port.embeddedBankSha256,meta.wavetableStorage.sha256);
  assert.equal(result.port.executedEepromReads,0);assert.equal(result.port.staticEepromReadSites,0);
  assert.ok(result.port.executedFlashBankReads>0);
  for(const field of ['independentlyCheckedDDSPhases','independentlyCheckedWavetableReads'])assert.ok(result.port[field]>0,field);
  if(meta.amplitudeGain||meta.chordGain)assert.ok(result.port.independentlyCheckedLookupGains>0);
  for(const target of ['original','port']){
   const actual=result[target],expected=baseline.variants[result.variant];
   for(const field of ['controlTicks','firstRestartControlTick','musicalCommands','commandSha256'])
    assert.equal(actual[field],expected[field],result.variant+'/'+target+'/'+field);
   for(const field of ['fifoUnderruns','lostTimerEvents','lostWorkEvents'])assert.equal(actual[field],0,field);
   assert.equal(actual.postRestartControlTicks,74);assert.equal(actual.checkedPwmPairs,actual.synthesisSamples);
  }
  assert.equal(result.original.snapshotSha256,result.port.snapshotSha256);
 }
 const report={board:MICRONUCLEUS_BOARD,engine,
  method:'Every CPU sample through each complete ATtiny13A source song and the 16 MHz Flash-only port, plus 74 control ticks after restart. Compare every musical command and every control-tick voice/envelope state after independently retuning DDS words to 31250 Hz.',
  modelsOnly:true,electricalPwmEdgesMeasured:false,eepromRequired:false,
  cpuHz:16000000,pwmHz:62500,synthesisHz:31250,controlTickHz:TICK_HZ,
  retainedMusicalCommandBaselineCommit:baseline.commit,snapshotReferenceSynthesisHz:31250,
  sourceHashNormalization:'UTF-8 with LF line endings; WASM hashed as raw bytes',
  sourceHashes:Object.fromEntries(sources.map(file=>[file,hashSource(file)])),
  coverage:{variants:VARIANTS.length,firmwareExecutions:VARIANTS.length*2,
   allMusicalStatesMatch:true,allMusicalCommandsMatch:true,allPortsRunWithErasedEeprom:true,
   independentlyCheckedDDSPhases:results.reduce((sum,r)=>sum+r.port.independentlyCheckedDDSPhases,0),
   independentlyCheckedWavetableReads:results.reduce((sum,r)=>sum+r.port.independentlyCheckedWavetableReads,0),
   independentlyCheckedLookupGains:results.reduce((sum,r)=>sum+r.port.independentlyCheckedLookupGains,0)},
  entries:results.sort((a,b)=>VARIANTS.indexOf(a.variant)-VARIANTS.indexOf(b.variant))};
 fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');return report;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const {values,positionals}=parseArgs({allowPositionals:true,options:{board:{type:'string'},engine:{type:'string',default:'js'},report:{type:'string'}}});
 const names=positionals.length?positionals:VARIANTS;
 if(values.report)assert.equal(values.board,MICRONUCLEUS_BOARD,'Aggregate report requires the Micronucleus board');
 const results=names.map(name=>audit(name,{board:values.board??null,engine:values.engine}));
 if(values.report)writeBoardReport(results,path.resolve(values.report),{engine:values.engine});
}
