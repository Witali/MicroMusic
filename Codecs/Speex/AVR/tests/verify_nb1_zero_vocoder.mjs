// General and zero-only C/ASM vector primitives versus the original recurrence.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/))
 .filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [out,context,classes,cursor,command,status,end]=['voc_out','voc_context','voc_classes','voc_cursor','voc_command','voc_status','__bss_end'].map(at);
const entries=new Map([[at('speex_nb1_synthesize40_avr'),'general'],[at('speex_nb1_synthesize40_zero_avr'),'zero'],
 [at('speex_nb1_synthesize40_prepared_avr'),'prepared']]);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,zeroCases=0,ordinaryCases=0,returns=0,minSP=2303,lastCall=null,expectedZero=false;
const stats=Object.fromEntries(['general','zero','prepared'].map(n=>[n,{calls:0,minCycles:Infinity,maxCycles:0,muls:0,previousBytes:0,pulseBytes:0}]));
const delta={min:Infinity,max:-Infinity,total:0};
const previousRead=cpu.readData.bind(cpu);
cpu.readData=a=>{if(active){if(a>=context+10&&a<context+20)++active.previousBytes;if(a>=context+20&&a<context+24)++active.pulseBytes;}return previousRead(a);};
function until(done){const limit=cpu.cycles+50000;while(!done()){
 assert.ok(cpu.cycles<limit);const opcode=cpu.progMem[cpu.pc],name=entries.get(cpu.pc*2);
 if(name){
  if(active){assert.equal(active.name,'prepared');assert.equal(name,expectedZero?'zero':'general');assert.equal(cpu.SP,active.sp);active.tail=name;}
  else {
  const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(returns*73+r*29)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={name,original,patterns,sp:cpu.SP,start:cpu.cycles,muls:0,previousBytes:0,pulseBytes:0};
  }
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end);
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.name],cycles=cpu.cycles-a.start;
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns);assert.equal(cpu.data[1],0);assert.equal(a.muls,160);
  const zero=a.name==='zero'||(a.name==='prepared'&&expectedZero);
  if(a.name==='prepared')assert.equal(a.tail,expectedZero?'zero':'general');
  assert.equal(a.previousBytes,(zero?0:80)+(a.name==='prepared'?2:0));assert.equal(a.pulseBytes,zero?0:4);
  ++s.calls;s.muls+=a.muls;s.previousBytes+=a.previousBytes;s.pulseBytes+=a.pulseBytes;
  s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});lastCall={name:a.name,cycles};active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
const word=n=>Number(BigInt.asIntN(16,BigInt(n)));
function model(table,indices,state){
 let [pulse,noise,mean,phase]=state,last=2;const pcm=Buffer.alloc(80),next=Buffer.alloc(8);
 for(let i=0;i<40;i++){
  const isPulse=i===phase;last=indices[i];if(isPulse)phase+=table[13];
  const value=word((isPulse?table[10]:0)+pulse+table[last]-noise);
  pulse=isPulse?table[11]:0;noise=table[5+last];
  mean=word((26214n*BigInt(mean)+6554n*BigInt(value)+16384n)>>15n);
  pcm.writeInt16LE(word(value-mean),2*i);
 }
 [pulse,noise,mean].forEach((v,i)=>next.writeInt16LE(v,2*i));next[6]=phase-40;next[7]=last;return {pcm,next};
}
function check(current,pitch,indices,state,firstPrevious=0){
 const zero=firstPrevious===0;
 const table=zero?[...current,0,0,0,0,0,0,0,0,pitch]:[...current,firstPrevious,signed(),signed(),signed(),signed(),signed(),signed(),0,pitch];
 const expected=model(table,indices,state);expectedZero=zero;
 const rawTable=Buffer.alloc(28),rawCursor=Buffer.alloc(8);table.forEach((v,i)=>rawTable.writeInt16LE(v,2*i));
 state.slice(0,3).forEach((v,i)=>rawCursor.writeInt16LE(v,2*i));rawCursor[6]=state[3];rawCursor[7]=0xee;
 let generalCycles=0;
 for(const kind of zero?[1,2,3,4,5]:[1,2,5]){
  cpu.data.set(rawTable,context);cpu.data.set(indices,classes);cpu.data.set(rawCursor,cursor);cpu.data.fill(0xa5,out,out+80);
  const before=Buffer.from(cpu.data.subarray(256,end));lastCall=null;
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.ok(Buffer.from(cpu.data.subarray(out,out+80)).equals(expected.pcm),`Words ${cases}/${kind}`);
  assert.ok(Buffer.from(cpu.data.subarray(cursor,cursor+8)).equals(expected.next),`Cursor ${cases}/${kind}`);
  for(let p=256;p<end;p++)if(!((p>=out&&p<out+80)||(p>=cursor&&p<cursor+8)||p===command||p===status))assert.equal(cpu.data[p],before[p-256]);
  if(kind===1){assert.equal(lastCall.name,'general');generalCycles=lastCall.cycles;}
  if(kind===3){assert.equal(lastCall.name,'zero');const d=lastCall.cycles-generalCycles;assert.ok(d<0);delta.min=Math.min(delta.min,d);delta.max=Math.max(delta.max,d);delta.total+=d;}
  if(kind===5)assert.equal(lastCall?.name,meta.backend==='asm'?'prepared':undefined,'Explicit architecture/ASM-enable selection');
 }
 ++cases;if(zero)++zeroCases;else ++ordinaryCases;
}
let seed=0x6f192b8c;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const signed=()=>word(random()>>>16),indices=()=>Uint8Array.from({length:40},()=>random()%5);
for(let base=-32768;base<=32767;base+=5)check(Array.from({length:5},(_,i)=>word(base+i)),17+random()%128,
 Uint8Array.from({length:40},(_,i)=>i%5),[signed(),signed(),signed(),random()%144]);
for(let pitch=17;pitch<=144;pitch++)for(let phase=0;phase<144;phase++)check(Array.from({length:5},signed),pitch,indices(),[signed(),signed(),signed(),phase]);
const edge=[-32768,-32767,-1,0,1,32766,32767];
for(const pulse of edge)for(const noise of edge)for(const mean of edge)for(const phase of [0,1,39,40,143])
 check(Array.from({length:5},signed),17+random()%128,indices(),[pulse,noise,mean,phase]);
// Every possible selector word, including high-byte-only nonzero values.
// A zero selector obeys the prepared-context invariant; nonzero uses the
// unrestricted general primitive. All five C/ASM controls remain exercised.
for(let previous=-32768;previous<=32767;previous++)
 check(Array.from({length:5},signed),17+random()%128,indices(),[signed(),signed(),signed(),random()%144],previous);
const report={scope:'Isolated C/ASM vectors; no C decoder execution or timing',backend:meta.backend,binarySha256:meta.binarySha256,
 cases,zeroCases,ordinaryCases,zeroPathsPerCase:5,ordinaryPathsPerCase:3,pitchPhasePairs:128*144,fullSigned16CurrentSweep:true,incomingDifferenceOverflowEdges:true,
 fullSigned16PredicateSweep:true,preparedEntryTailBranchAndArgumentsExact:true,
 originalTwoProductReference:true,wordsAndCursorExact:true,readOnlyInputsAndOutputBounds:true,explicitCSelectionVerified:true,
 calleeSavedAndR1Returns:returns,stats,pairedZeroMinusGeneralCycles:{...delta,mean:delta.total/zeroCases},
 removedPreviousAndPulseBytesPer40:84,includesInterrupts:false,physicalBoardTested:false,peakStack:2303-minSP};
assert.equal(stats.general.calls,cases);assert.equal(stats.zero.calls,zeroCases);
assert.equal(stats.prepared.calls,meta.backend==='asm'?cases:0);
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
