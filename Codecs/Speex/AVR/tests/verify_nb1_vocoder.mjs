// Independent original two-product model, ABI, bounds and read-only inputs.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin'));
const metadata=JSON.parse(readFileSync(join(dir,'input.json')));
const hash=b=>createHash('sha256').update(b).digest('hex');assert.equal(hash(binary),metadata.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [out,context,classes,cursor,command,status,entry,end]=['voc_out','voc_context','voc_classes','voc_cursor',
 'voc_command','voc_status','speex_nb1_synthesize40_avr','__bss_end'].map(at);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,returns=0,minCycles=Infinity,maxCycles=0,minSP=2303;
function until(done){const limit=cpu.cycles+50000;while(!done()){
 assert.ok(cpu.cycles<limit,'Vector timeout');const opcode=cpu.progMem[cpu.pc];
 if(cpu.pc*2===entry){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]);
  const patterns=saved.map(r=>(returns*73+r*29)&255);saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={sp:cpu.SP,cycles:cpu.cycles,original,patterns,muls:0};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  assert.deepEqual(saved.map(r=>cpu.data[r]),active.patterns,'Callee-saved registers');assert.equal(cpu.data[1],0);
  assert.equal(active.muls,160,'Exactly four MUL per sample');const cycles=cpu.cycles-active.cycles;
  minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=active.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
const word=n=>Number(BigInt.asIntN(16,BigInt(n)));
function model(table,indices,state){
 let [priorPulse,priorNoise,mean,phase]=state;const pcm=Buffer.alloc(80);let last=2;
 for(let i=0;i<40;i++){
  const pulse=i===phase;last=indices[i];if(pulse)phase+=table[13];
  const value=word((pulse?table[10]:0)+priorPulse+table[last]-priorNoise);
  priorPulse=pulse?table[11]:0;priorNoise=table[5+last];
  mean=word((26214n*BigInt(mean)+6554n*BigInt(value)+16384n)>>15n);
  pcm.writeInt16LE(word(value-mean),2*i);
 }
 const next=Buffer.alloc(8);[priorPulse,priorNoise,mean].forEach((v,i)=>next.writeInt16LE(v,2*i));
 next[6]=phase-40;next[7]=last;return {pcm,next};
}
function check(table,indices,state){
 const expected=model(table,indices,state),rawTable=Buffer.alloc(28),rawState=Buffer.alloc(8);
 table.forEach((v,i)=>rawTable.writeInt16LE(v,2*i));state.slice(0,3).forEach((v,i)=>rawState.writeInt16LE(v,2*i));
 rawState[6]=state[3];rawState[7]=0xee;
 for(const kind of [1,2]){
  cpu.data.set(rawTable,context);cpu.data.set(indices,classes);cpu.data.set(rawState,cursor);
  cpu.data.fill(0xa5,out,out+80);const before=Buffer.from(cpu.data.subarray(256,end));
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.ok(Buffer.from(cpu.data.subarray(out,out+80)).equals(expected.pcm),`PCM ${cases}/${kind}`);
  assert.ok(Buffer.from(cpu.data.subarray(cursor,cursor+8)).equals(expected.next),`State ${cases}/${kind}`);
  for(let i=256;i<end;i++)if(!((i>=out&&i<out+80)||(i>=cursor&&i<cursor+8)||i===status||i===command))
   assert.equal(cpu.data[i],before[i-256],`Read-only/guard byte ${i}`);
  assert.equal(cpu.data[1],0);
 }
 ++cases;
}
let seed=0x6f192b8c;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const signed=()=>word(random()>>>16),indices=()=>Uint8Array.from({length:40},()=>random()%5);
// All signed16 values occupy a table slot; all five classes used every block.
for(let base=-32768;base<=32767;base+=5){
 const table=Array.from({length:14},signed);for(let i=0;i<5;i++)table[i]=word(base+i);
 table[13]=17+(random()%128);check(table,Uint8Array.from({length:40},(_,i)=>i%5),[signed(),signed(),signed(),random()%144]);
}
// Every valid pitch/phase pair, including phase beyond a newly selected pitch.
for(let pitch=17;pitch<=144;pitch++)for(let phase=0;phase<144;phase++){
 const table=Array.from({length:14},signed);table[13]=pitch;
 check(table,indices(),[signed(),signed(),signed(),phase]);
}
const report={scope:'Isolated vector C/ASM primitives; C decoder not executed or timed',binarySha256:metadata.binarySha256,
 cases,pcmAndCursorExact:true,originalTwoProductBigIntReference:true,completeSignedWordTableSweep:true,
 pitchPhasePairs:128*144,readOnlyInputsAndOutputBounds:true,calleeSavedAndR1Returns:returns,
 arbitraryRegisterPatterns:true,hardwareMultipliesPer40:160,asmMinCycles:minCycles,asmMaxCycles:maxCycles,
 includesInterrupts:false,physicalBoardTested:false,peakStack:2303-minSP};
assert.equal(returns,cases);writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
