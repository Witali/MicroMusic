// Real decoder: quarter generation, independent vocoder, state and dead-prefix bounds.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]),input=resolve(process.argv[3]);
const binary=readFileSync(join(dir,'cache.bin')),metadata=JSON.parse(readFileSync(join(dir,'input.json')));
const source=JSON.parse(readFileSync(join(input,'input.json'))),raw=readFileSync(join(input,'packets32.bin')),
 expected=readFileSync(join(input,'oracle.pcm'));
const hash=b=>createHash('sha256').update(b).digest('hex');assert.equal(hash(binary),metadata.binarySha256);
assert.equal(hash(raw),source.inputSha256);assert.equal(hash(expected),source.pcmSha256);assert.equal(source.wideband,true);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
function entry(n){const all=[...symbols.keys()].filter(s=>s===n||s.startsWith(n+'.'));assert.equal(all.length,1,n);return at(all[0]);}
const [packet,bytes,command,status,result,chunks,pcm,end]=['cache_packet','cache_bytes','cache_command','cache_status',
 'cache_result','cache_chunks','cache_pcm','__bss_end'].map(at);
const prepare=entry('speex_nb1_excitation_prepare'),generate=entry('speex_nb1_excitation_subframe'),
 values=entry('speex_low_noise_values5'),indices=entry('speex_low_noise_indices40'),fold=entry('speex_wb_noise_fold40_avr');
const generalVocoder=entry('speex_nb1_synthesize40_avr'),zeroVocoder=entry('speex_nb1_synthesize40_zero_avr');
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
let base,live,frameBegin,workEnd,ctx,seedAt,pulseAt,meanAt,prevAt,phaseAt;
let row=null,prepPending=null,genPending=null,foldPending=null,parts=[],oldChunks=0,minSP=2303;
let cacheFrames=0,generatedBlocks=0,foldedBlocks=0,valuesCalls=0,indicesCalls=0;
let generalVocoderCalls=0,zeroVocoderCalls=0;
let zeroGainFrames=0,nonzeroToZero=0,zeroToNonzero=0,zeroWithPriorPulse=0,lastGainZero=null;
const memory=(p,n)=>Buffer.from(cpu.data.subarray(p,p+n));
const s16=p=>cpu.dataView.getInt16(p,true),word=n=>Number(BigInt.asIntN(16,BigInt(n)));
function cacheIntact(){
 assert.ok(memory(base,row.gen*40).equals(row.classes.subarray(0,row.gen*40)),'Generated class prefix');
 assert.ok(memory(base+160,10).equals(row.rawNoise),'Five raw noise words');
 assert.ok(memory(base+198,10).equals(row.prefold),'Frame-invariant Q15 words');
 assert.ok(memory(workEnd,live-workEnd).every(v=>v===0xa5),'Dead-prefix guard');
 assert.ok(memory(live,frameBegin-live).equals(row.delayed),'Delayed history preserved');
 const state=row.states[Math.max(0,row.gen-1)],expectedContext=Buffer.from(row.context);
 expectedContext.writeInt16LE(row.gen?state.noise:row.initialNoise,24);
 assert.ok(memory(ctx,28).equals(expectedContext),'Frame constants and exact prior noise');
}
function until(done){const limit=cpu.cycles+3000000;while(!done()){
 assert.ok(cpu.cycles<limit,'Streaming mailbox timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(row){
  if(pc===generalVocoder||pc===zeroVocoder){
   assert.equal(row.mode,1);assert.equal(pc===zeroVocoder,row.zeroContext,'Independent prepared-context selection');
   ++row.vocoder;if(pc===zeroVocoder)++zeroVocoderCalls;else ++generalVocoderCalls;
  }
  if(pc===prepare){
   assert.equal(row.mode,1);assert.equal(row.prepared,false);row.prepared=true;
   cpu.data.fill(0xa5,workEnd,live);row.delayed=memory(live,frameBegin-live);
   prepPending={sp:cpu.SP,state:[s16(pulseAt),s16(meanAt),s16(prevAt),cpu.data[phaseAt],cpu.dataView.getUint32(seedAt,true)]};
  }
  if(pc===generate){
   assert.equal(row.mode,1);cacheIntact();assert.equal(genPending,null);
   genPending={sp:cpu.SP,sub:row.gen,before:memory(frameBegin+80*row.gen-2,2),after:memory(frameBegin+80*(row.gen+1),2)};
  }
  if(pc===values){++row.values;++valuesCalls;}
  if(pc===indices){++row.indices;++indicesCalls;}
  if(pc===fold){
   cacheIntact();assert.equal(row.gen,row.fold+1);const sub=cpu.data[20],out=cpu.dataView.getUint16(24,true);
   assert.equal(sub,row.fold);assert.equal(cpu.dataView.getUint16(22,true),base);
   const gain=BigInt(cpu.dataView.getInt32(16,true)),scratch=cpu.dataView.getUint16(14,true);
   const table=Array.from({length:5},(_,i)=>word(BigInt.asUintN(32,((29491n*BigInt(row.rawNoise.readInt16LE(2*i)))>>15n)*gain+256n)>>9n));
   const output=Buffer.alloc(80),rawTable=Buffer.alloc(10);table.forEach((v,i)=>rawTable.writeInt16LE(v,2*i));
   for(let i=0;i<40;i++)output.writeInt16LE(word((i&1)?-table[row.classes[40*sub+i]]:table[row.classes[40*sub+i]]),2*i);
   foldPending={sp:cpu.SP,out,scratch,output,rawTable,workspace:memory(base,208),
    before:memory(out-2,2),after:memory(out+80,2),scratchBefore:memory(scratch-2,2),scratchAfter:memory(scratch+10,2)};
   ++row.fold;
  }
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(opcode===0x9508){
  if(prepPending&&cpu.SP===prepPending.sp+2){
   cacheIntact();assert.deepEqual([s16(pulseAt),s16(meanAt),s16(prevAt),cpu.data[phaseAt],cpu.dataView.getUint32(seedAt,true)],prepPending.state,'Preparation preserves persistent vocoder state/seed');
   prepPending=null;
  }
  if(genPending&&cpu.SP===genPending.sp+2){
   const sub=genPending.sub,state=row.states[sub],out=frameBegin+80*sub;
   assert.ok(memory(out,80).equals(row.excitation.subarray(80*sub,80*(sub+1))),'Independent vocoder excitation');
   assert.ok(memory(out-2,2).equals(genPending.before)&&memory(out+80,2).equals(genPending.after),'Generation output bounds');
   assert.deepEqual([s16(pulseAt),s16(meanAt),s16(prevAt),cpu.data[phaseAt]],[state.pulse,state.mean,state.previous,state.phase],'Partial vocoder state');
   assert.equal(cpu.dataView.getUint32(seedAt,true),state.seed,'One quarter RNG advance');
   ++row.gen;++generatedBlocks;cacheIntact();genPending=null;
  }
  if(foldPending&&cpu.SP===foldPending.sp+2){
   const p=foldPending;assert.ok(memory(p.out,80).equals(p.output),'Exact fold');
   assert.ok(memory(p.scratch,10).equals(p.rawTable),'Five folded scratch values');
   assert.ok(memory(base,208).equals(p.workspace),'Fold does not write workspace');
   assert.ok(memory(p.out-2,2).equals(p.before)&&memory(p.out+80,2).equals(p.after),'Fold output bounds');
   assert.ok(memory(p.scratch-2,2).equals(p.scratchBefore)&&memory(p.scratch+10,2).equals(p.scratchAfter),'Fold scratch bounds');
   cacheIntact();foldPending=null;++foldedBlocks;
  }
 }
 if(cpu.data[chunks]!==oldChunks){oldChunks=cpu.data[chunks];parts.push(memory(cpu.dataView.getUint16(pcm,true),160));}
}}
until(()=>cpu.data[status]===1);const pointer=n=>cpu.dataView.getUint16(at(n),true);
base=pointer('cache_begin');live=pointer('cache_live_begin');frameBegin=pointer('cache_frame_begin');
workEnd=pointer('cache_work_end');ctx=pointer('cache_context');seedAt=pointer('cache_seed');
pulseAt=pointer('cache_voc_pulse');meanAt=pointer('cache_voc_mean');prevAt=pointer('cache_voc_previous');phaseAt=pointer('cache_voc_phase');
assert.deepEqual([live-base,frameBegin-base,pointer('cache_move_begin')-base,ctx-base,workEnd-base],[210,290,320,170,208]);
const gains=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8')
 .match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
function field(payload,bit,n){let value=0;for(let i=0;i<n;i++)value=value*2+((payload[(bit+i)>>3]>>(7-((bit+i)&7)))&1);return value;}
// Pinned Xiph math_approx.h fixed-point polynomial, including signed16 casts.
function sqrt(x){
 let t=x,r=0;if(t>=65536){t>>=16;r+=8;}if(t>=256){t>>=8;r+=4;}if(t>=16){t>>=4;r+=2;}if(t>=4)r++;
 const k=r-6,shift=(v,n)=>n>=0?v>>BigInt(n):v<<BigInt(-n);x=Number(shift(BigInt(x),2*k));
 const q14=(a,b)=>word((BigInt(word(a))*BigInt(word(b)))>>14n);
 const rt=word(3634+q14(x,word(21173+q14(x,word(-12627+q14(x,4204))))));
 return Number(shift(BigInt(rt),7-k));
}
let seed=1000,state={pulse:0,mean:0,previous:0,phase:0};
function prepared(payload){
 const mode=payload[0]>>3,result={mode,prepared:false,gen:0,fold:0,values:0,indices:0,vocoder:0};if(mode!==1)return result;
 const scale=Math.floor(28406*gains[field(payload,34,5)]/32768),pitch=17+field(payload,23,7);
 const coefficient=(2185*(field(payload,30,4)<<6)+16384)>>15,g=Math.max(0,Math.min(64,(24576*(coefficient-13)+8192)>>14));
 result.zeroGain=g===0;result.priorPulse=state.pulse;
 const amplitude=word(sqrt(2*pitch)*word((g*((scale+8192)>>14)+32)>>6));
 const q15=(a,b)=>word((BigInt(a)*BigInt(b))>>15n),table=[];
 result.rawNoise=Buffer.alloc(10);result.prefold=Buffer.alloc(10);result.context=Buffer.alloc(28);result.classes=Buffer.alloc(160);
 result.excitation=Buffer.alloc(320);result.states=[];
 for(let n=-2;n<=2;n++){
  const a=BigInt(n*128),b=BigInt(scale),product=a*(b>>14n)+((a*(b&16383n))>>14n);
  const v=word((BigInt.asIntN(32,product<<7n)+8192n)>>14n);table.push(v);result.rawNoise.writeInt16LE(v,2*(n+2));
  result.prefold.writeInt16LE(word((29491n*BigInt(v))>>15n),2*(n+2));
 }
 const current=table.map(v=>q15(32767-435*g,v)),previous=table.map(v=>q15(77*g,v));
 const pulseNow=q15(22938,amplitude),pulsePrevious=q15(9830,amplitude);
 result.zeroContext=previous[0]===0;
 if(result.zeroContext)assert.ok(previous.every(v=>v===0)&&pulseNow===0&&pulsePrevious===0);
 let {pulse,mean,phase}=state,priorNoise=q15(77*g,state.previous);result.initialNoise=priorNoise;
 [...current,...previous,pulseNow,pulsePrevious,priorNoise,pitch].forEach((v,i)=>result.context.writeInt16LE(v,2*i));
 for(let sub=0;sub<4;sub++){
  let last=2;
  for(let i=0;i<40;i++){
   seed=(Math.imul(1664525,seed)+1013904223)>>>0;
   const high=(seed>>>16)-((seed&0x80000000)?65536:0);
   last=Math.floor((high-Math.floor(high/8)+8192)/16384)+2;result.classes[40*sub+i]=last;
   const isPulse=i===phase;if(isPulse)phase+=pitch;
   const value=word((isPulse?pulseNow:0)+pulse+current[last]-priorNoise);
   pulse=isPulse?pulsePrevious:0;priorNoise=previous[last];
   mean=word((26214n*BigInt(mean)+6554n*BigInt(value)+16384n)>>15n);
   result.excitation.writeInt16LE(word(value-mean),80*sub+2*i);
  }
  phase-=40;result.states.push({pulse,mean,phase,previous:table[last],noise:priorNoise,seed});
 }
 state=result.states[3];return result;
}
for(let f=0;f<source.frames;f++){
 const payload=raw.subarray(f*32,(f+1)*32);row=prepared(payload);cpu.data.set(payload,packet);cpu.data[bytes]=source.packetLengths[f];
 parts=[];cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.equal(cpu.dataView.getInt8(result),0);assert.equal(parts.length,4);
 assert.ok(Buffer.concat(parts).equals(expected.subarray(f*640,(f+1)*640)),'Mixed PCM '+f);
 assert.deepEqual([row.prepared,row.gen,row.fold,row.values,row.indices],row.mode===1?[true,4,4,1,4]:[false,0,0,0,0]);
 assert.equal(row.vocoder,row.mode===1?4:0);
 assert.equal(cpu.dataView.getUint32(seedAt,true),seed);if(row.mode===1){
  cacheIntact();++cacheFrames;
  if(row.zeroGain){++zeroGainFrames;if(row.priorPulse!==0)++zeroWithPriorPulse;if(lastGainZero===false)++nonzeroToZero;}
  else if(lastGainZero===true)++zeroToNonzero;
  lastGainZero=row.zeroGain;
}row=null;
}
const corpusCounts={cacheFrames,generatedBlocks,foldedBlocks,valuesCalls,indicesCalls,generalVocoderCalls,zeroVocoderCalls};
cpu.data[status]=0;cpu.data[command]=2;until(()=>cpu.data[status]===1);
assert.equal(cpu.dataView.getUint32(seedAt,true),1000);assert.ok(memory(base,208).every(v=>v===0));
// Natural mixed speech has no zero-gain frame beginning with a nonzero pulse.
// Inject that legal persistent-state case explicitly; the independent original
// vocoder checks every excitation word and quarter state, not the speech oracle.
const firstNb1=Array.from({length:source.frames},(_,i)=>i).find(i=>(raw[i*32]>>3)===1);
assert.notEqual(firstNb1,undefined);
const targeted=[];
for(let code=0;code<4;code++){
 cpu.data[status]=0;cpu.data[command]=2;until(()=>cpu.data[status]===1);
 const pulse=[1,-1,9830,-9830][code],mean=[0,0,32767,-32768][code],previous=[14771,-14771,1,-1][code],phase=[0,1,39,40][code];
 cpu.dataView.setInt16(pulseAt,pulse,true);cpu.dataView.setInt16(meanAt,mean,true);
 cpu.dataView.setInt16(prevAt,previous,true);cpu.data[phaseAt]=phase;
 state={pulse,mean,previous,phase};seed=1000;
 const payload=Buffer.from(raw.subarray(firstNb1*32,(firstNb1+1)*32));
 payload[3]&=252;payload[4]=(payload[4]&63)|(code<<6);
 row=prepared(payload);assert.ok(row.zeroGain&&row.priorPulse!==0);
 cpu.data.set(payload,packet);cpu.data[bytes]=source.packetLengths[firstNb1];
 parts=[];cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.equal(cpu.dataView.getInt8(result),0);assert.equal(parts.length,4);
 assert.deepEqual([row.prepared,row.gen,row.fold,row.values,row.indices],[true,4,4,1,4]);
 assert.equal(row.vocoder,4);
 assert.equal(cpu.dataView.getUint32(seedAt,true),seed);cacheIntact();
 targeted.push({code,priorPulse:pulse,priorMean:mean,priorNoise:previous,priorPhase:phase,independentExcitationAndQuarterStatesExact:true});row=null;
}
// The broader arithmetic predicate also admits gain>0 with scale<=4096,
// but no legal packet can create that case with the pinned 32-entry table.
// Arbitrary incoming prior noise is covered by the isolated vector fixture.
const packetScales=gains.map(g=>Math.floor(28406*g/32768));assert.equal(packetScales.length,32);
assert.ok(packetScales.every(s=>s>4096));
const report={binarySha256:metadata.binarySha256,inputSha256:source.inputSha256,pcmSha256:source.pcmSha256,frames:source.frames,
 ...corpusCounts,cacheBytes:170,contextBytes:28,prefoldBytes:10,reusedWorkspaceBytes:208,
 guardBytes:2,firstDelayedInputByte:210,nextHistorySourceByte:320,independentOriginalVocoder:true,allPartialStatesExact:true,
 classesAndSeedPerQuarterExact:true,readOnlyFoldWorkspace:true,outputAndScratchBounds:true,pcmExact:true,resetClearsWorkspace:true,
 zeroGainFrames,nonzeroToZero,zeroToNonzero,zeroFramesWithPriorPulse:zeroWithPriorPulse,preparationPreservesPersistentState:true,
 targetedZeroGainWithPriorPulse:{cases:targeted,allFourGainCodes:true,scope:'Injected persistent states; independent original excitation, quarter state, seed, fold and guards; no PCM-oracle claim for these four frames'},
 positiveGainZeroContext:{packetScaleCodes:32,minimumScale:Math.min(...packetScales),zeroBoundary:4096,unreachableForAllPacketScales:true},
 preparedContextDispatchExact:true,
 includesInterrupts:false,physicalBoardTested:false,flashBytes:binary.length,staticSramBytes:end-256,peakStack:2303-minSP,freeSram:minSP-end+1};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
