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
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
let base,live,frameBegin,workEnd,ctx,seedAt,pulseAt,meanAt,prevAt,phaseAt;
let row=null,prepPending=null,genPending=null,foldPending=null,parts=[],oldChunks=0,minSP=2303;
let cacheFrames=0,generatedBlocks=0,foldedBlocks=0,valuesCalls=0,indicesCalls=0;
const memory=(p,n)=>Buffer.from(cpu.data.subarray(p,p+n));
const s16=p=>cpu.dataView.getInt16(p,true),word=n=>Number(BigInt.asIntN(16,BigInt(n)));
function cacheIntact(){
 assert.ok(memory(base,row.gen*40).equals(row.classes.subarray(0,row.gen*40)),'Generated class prefix');
 assert.ok(memory(base+160,10).equals(row.rawNoise),'Five raw noise words');
 assert.ok(memory(workEnd,live-workEnd).every(v=>v===0xa5),'Twelve-byte dead-prefix guard');
 assert.ok(memory(live,frameBegin-live).equals(row.delayed),'Delayed history preserved');
 const state=row.states[Math.max(0,row.gen-1)],expectedContext=Buffer.from(row.context);
 expectedContext.writeInt16LE(row.gen?state.noise:row.initialNoise,24);
 assert.ok(memory(ctx,28).equals(expectedContext),'Frame constants and exact prior noise');
}
function until(done){const limit=cpu.cycles+3000000;while(!done()){
 assert.ok(cpu.cycles<limit,'Streaming mailbox timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(row){
  if(pc===prepare){
   assert.equal(row.mode,1);assert.equal(row.prepared,false);row.prepared=true;
   cpu.data.fill(0xa5,workEnd,live);row.delayed=memory(live,frameBegin-live);prepPending={sp:cpu.SP};
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
   foldPending={sp:cpu.SP,out,scratch,output,rawTable,workspace:memory(base,198),
    before:memory(out-2,2),after:memory(out+80,2),scratchBefore:memory(scratch-2,2),scratchAfter:memory(scratch+10,2)};
   ++row.fold;
  }
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(opcode===0x9508){
  if(prepPending&&cpu.SP===prepPending.sp+2){cacheIntact();prepPending=null;}
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
   assert.ok(memory(base,198).equals(p.workspace),'Fold does not write workspace');
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
assert.deepEqual([live-base,frameBegin-base,pointer('cache_move_begin')-base,ctx-base,workEnd-base],[210,290,320,170,198]);
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
 const mode=payload[0]>>3,result={mode,prepared:false,gen:0,fold:0,values:0,indices:0};if(mode!==1)return result;
 const scale=Math.floor(28406*gains[field(payload,34,5)]/32768),pitch=17+field(payload,23,7);
 const coefficient=(2185*(field(payload,30,4)<<6)+16384)>>15,g=Math.max(0,Math.min(64,(24576*(coefficient-13)+8192)>>14));
 const amplitude=word(sqrt(2*pitch)*word((g*((scale+8192)>>14)+32)>>6));
 const q15=(a,b)=>word((BigInt(a)*BigInt(b))>>15n),table=[];
 result.rawNoise=Buffer.alloc(10);result.context=Buffer.alloc(28);result.classes=Buffer.alloc(160);
 result.excitation=Buffer.alloc(320);result.states=[];
 for(let n=-2;n<=2;n++){
  const a=BigInt(n*128),b=BigInt(scale),product=a*(b>>14n)+((a*(b&16383n))>>14n);
  const v=word((BigInt.asIntN(32,product<<7n)+8192n)>>14n);table.push(v);result.rawNoise.writeInt16LE(v,2*(n+2));
 }
 const current=table.map(v=>q15(32767-435*g,v)),previous=table.map(v=>q15(77*g,v));
 const pulseNow=q15(22938,amplitude),pulsePrevious=q15(9830,amplitude);
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
 assert.equal(cpu.dataView.getUint32(seedAt,true),seed);if(row.mode===1){cacheIntact();++cacheFrames;}row=null;
}
cpu.data[status]=0;cpu.data[command]=2;until(()=>cpu.data[status]===1);
assert.equal(cpu.dataView.getUint32(seedAt,true),1000);assert.ok(memory(base,198).every(v=>v===0));
const report={binarySha256:metadata.binarySha256,inputSha256:source.inputSha256,pcmSha256:source.pcmSha256,frames:source.frames,
 cacheFrames,generatedBlocks,foldedBlocks,valuesCalls,indicesCalls,cacheBytes:170,contextBytes:28,reusedWorkspaceBytes:198,
 guardBytes:12,firstDelayedInputByte:210,nextHistorySourceByte:320,independentOriginalVocoder:true,allPartialStatesExact:true,
 classesAndSeedPerQuarterExact:true,readOnlyFoldWorkspace:true,outputAndScratchBounds:true,pcmExact:true,resetClearsWorkspace:true,
 includesInterrupts:false,physicalBoardTested:false,flashBytes:binary.length,staticSramBytes:end-256,peakStack:2303-minSP,freeSram:minSP-end+1};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
