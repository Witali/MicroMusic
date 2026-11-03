// Isolated QMF boundary-preemption/ABI proof, never a decoder execution.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';

const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'wb.bin'));
const meta=JSON.parse(readFileSync(join(dir,'input.json'),'utf8'));
assert.equal(meta.irq,true);assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [work,command,status,kind,alias,config,irqCount,accumulator,entry,end]=[
 'wb_unit_buffer','wb_unit_command','wb_unit_status','wb_unit_kind','wb_unit_alias','qmf_config',
 'qmf_irq_count','qmf_accumulator','speex_wb_qmf40_avr','__bss_end'].map(at);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),callee=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,irq=null,preempt=false,sreg,interrupt,lastTrace=null;
let injections=0,dirtyR1=0,isrMuls=0,returns=0,ownStack=0,minSP=2303,caseId=0;
const tStates=new Set(),rows=[];
function isMul(op){return (op&0xfc00)===0x9c00||(op&0xff00)===0x0200||(op&0xff88)===0x0300;}
function raise(){
 assert.equal(irq,null);assert.ok(cpu.interruptsEnabled);
 irq={regs:cpu.data.slice(0,32),sreg:cpu.data[sreg],sp:cpu.SP,pc:cpu.pc};
 cpu.setInterruptFlag(interrupt);
}
function until(done){const deadline=cpu.cycles+10000000;while(!done()){
 assert.ok(cpu.cycles<deadline,'QMF boundary timeout');
 if(cpu.pc*2===entry&&!active&&!irq){
  assert.equal(cpu.data[1],0);
  const original=callee.map(r=>cpu.data[r]),patterns=callee.map(r=>(caseId*73+r*29)&255);
  callee.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  cpu.data[sreg]=(cpu.data[sreg]&~64)|((caseId&1)<<6);tStates.add((cpu.data[sreg]>>6)&1);
  active={original,patterns,sp:cpu.SP,begin:cpu.cycles,ops:[],muls:0};
  if(preempt){raise();cpu.tick();continue;}
 }
 const op=cpu.progMem[cpu.pc],inIsr=irq!==null,ret=op===0x9508,reti=op===0x9518;
 if(active&&!inIsr){active.ops.push(op);if(isMul(op))active.muls++;}
 if(inIsr&&isMul(op))isrMuls++;
 avrInstruction(cpu);minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(active&&!inIsr)ownStack=Math.max(ownStack,active.sp-cpu.SP);
 if(reti){
  assert.ok(irq);assert.deepEqual(cpu.data.slice(0,32),irq.regs);assert.equal(cpu.data[sreg],irq.sreg);
  assert.equal(cpu.SP,irq.sp);assert.equal(cpu.pc,irq.pc);dirtyR1+=Number(irq.regs[1]!==0);injections++;irq=null;
 }
 if(active&&!inIsr&&ret&&cpu.SP===active.sp+2){
  assert.deepEqual(callee.map(r=>cpu.data[r]),active.patterns);assert.equal(cpu.data[1],0);
  callee.forEach((r,i)=>{cpu.data[r]=active.original[i];});
  lastTrace={ops:active.ops,muls:active.muls,elapsed:cpu.cycles-active.begin};active=null;returns++;
 }else if(active&&!inIsr&&preempt)raise();
 cpu.tick();
}}
until(()=>cpu.data[status]===1);
const d=Array.from({length:6},(_,i)=>cpu.dataView.getUint16(config+2*i,true));sreg=d[0];
interrupt={address:d[1],flagRegister:d[2],flagMask:d[3],enableRegister:d[4],enableMask:d[5]};
assert.ok(cpu.interruptsEnabled);
let seed=0x6f192b8c;
function random(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>16)-32768;}
const h=[-4,-10,7,15,-14,-26,37,123,123,37,-26,-14,15,7,-10,-4];
const clip=n=>Math.max(-32767,Math.min(32767,n));
function model(input,state){
 const next=[...state],out=[];
 for(let i=0;i<40;i++){
  const pos=i&7;next[2*pos]=(input[i]-input[i+40])>>1;next[2*pos+1]=(input[i]+input[i+40])>>1;
  let e=0,o=0;for(let k=0;k<8;k++){
   const j=(i-k)&7;e+=h[2*k]*next[2*j];o+=h[2*k+1]*next[2*j+1];
  }
  out.push(clip((e+32)>>6),clip((o+32)>>6));
 }
 return {out,state:next};
}
function run(input,state,aliased,inject){
 cpu.data.fill(165,work,work+400);
 input.forEach((v,i)=>cpu.dataView.setInt16(work+4+2*i,v,true));
 for(const mirror of [0,32])state.forEach((v,i)=>cpu.dataView.setInt16(work+332+mirror+2*i,v,true));
 const expected=cpu.data.slice(work,work+400),view=new DataView(expected.buffer),answer=model(input,state);
 answer.out.forEach((v,i)=>view.setInt16(168+2*i,v,true));
 for(const mirror of [0,32])answer.state.forEach((v,i)=>view.setInt16(332+mirror+2*i,v,true));
 cpu.data[alias]=Number(aliased);cpu.data[kind]=0;cpu.dataView.setUint16(irqCount,0,true);cpu.dataView.setUint16(accumulator,0,true);
 const previous=injections;lastTrace=null;preempt=inject;cpu.data[status]=1;cpu.data[command]=1;
 until(()=>cpu.data[status]===3);preempt=false;assert.equal(active,null);assert.equal(irq,null);
 assert.deepEqual(cpu.data.slice(work,work+400),expected,'QMF words/state/guards/input '+caseId);
 const count=injections-previous;assert.equal(cpu.dataView.getUint16(irqCount,true),count&65535);
 let sum=0;for(let k=0;k<count;k++)sum=(sum+((k+37)&255)*((k+129)&255))&65535;
 assert.equal(cpu.dataView.getUint16(accumulator,true),sum);
 if(inject)assert.equal(count,lastTrace.ops.length,'Entry plus every non-RET boundary');
 return lastTrace;
}
for(let pattern=0;pattern<4;pattern++)for(const aliased of [false,true]){
 const state=Array.from({length:8},()=>{
  const a=random(),b=random();return [(a-b)>>1,(a+b)>>1];
 }).flat();
 const input=Array.from({length:80},(_,i)=>pattern===0?0:pattern===1?(i&1?-32768:32767):
  pattern===2?(i<40?32767:-32768):random());
 const ordinary=run(input,state,aliased,false),interrupted=run(input,state,aliased,true);
 assert.deepEqual(interrupted.ops,ordinary.ops);assert.equal(interrupted.muls,ordinary.muls);
 rows.push({pattern,aliased,executedBoundaries:ordinary.ops.length,muls:ordinary.muls,cyclesIncludingRet:ordinary.elapsed});caseId++;
}
assert.equal(isrMuls,injections);assert.ok(dirtyR1>0);assert.deepEqual([...tStates].sort(),[0,1]);
const report={scope:'Isolated QMF C-independent model and every-boundary compiled ISR proof',
 binarySha256:meta.binarySha256,cases:caseId,asmReturns:returns,ownAsmStackBytes:ownStack,
 wholeProbePeakStackBytes:2303-minSP,injections,nonzeroR1Interrupts:dirtyR1,isrMulInstructions:isrMuls,
 full32RegistersAndSregRestored:true,interruptPcAndSpRestored:true,traceUnchanged:true,
 calleeSavedAndR1Exact:true,wholeArenaInputsGuardsAndMirroredStateExact:true,
 bothIncomingTValues:true,permittedAliasAndSeparate:true,vectors:rows,deviceHeaders:meta.headers,
 includesInterrupts:true,modelsHardwareEntryLatency:false,physicalBoardTested:false,productionOutputAdmitted:false};
writeFileSync(join(dir,'irq-verification.json'),JSON.stringify(report,null,2)+'\n');
console.log('PASS',JSON.stringify(report));
