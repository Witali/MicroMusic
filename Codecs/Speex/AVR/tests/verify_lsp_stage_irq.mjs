// Preempt every ASM instruction boundary with a compiled MUL-using ISR.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/zero-stage-irq'):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'irq.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('irq_stage_work'),pointer=address('irq_stage_address'),fAddress=address('irq_stage_f'),number=address('irq_stage_number');
const status=address('irq_stage_status'),command=address('irq_stage_command'),config=address('irq_stage_config');
const countAddress=address('irq_stage_count'),accumulator=address('irq_stage_accumulator');
const entries=new Map([2,3,4].map(n=>[symbols.get('speex_avr_lsp_stage'+n),n]));
let sreg,interrupt,trace=null,irq=null,inject=-1,step=0,injections=0,nonzeroR1Interrupts=0,retChecks=0,isrMulInstructions=0;
const boundaryCounts={2:0,3:0,4:0},baselineCycles={2:new Set(),3:new Set(),4:new Set()};
function snapshot(){return {regs:cpu.data.slice(0,32),sreg:cpu.data[sreg],sp:cpu.SP,pc:cpu.pc};}
function raise(){assert.equal(irq,null);assert.ok(cpu.data[sreg]&128);irq=snapshot();cpu.setInterruptFlag(interrupt);}
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'IRQ mailbox timeout');
 const stage=entries.get(cpu.pc*2);
 if(stage&&!trace){
  assert.equal(trace,null);assert.equal(cpu.data[1],0);trace={n:stage,sp:cpu.SP,ops:[],start:cpu.cycles};step=0;
  if(inject===-2){raise();cpu.tick();assert.equal(cpu.pc,interrupt.address);continue;}
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508,reti=op===0x9518,inIsr=irq!==null;
 if(trace&&!inIsr)trace.ops.push(op);
 if(inIsr&&(op&0xfc00)===0x9c00)isrMulInstructions++;
 avrInstruction(cpu);
 if(trace&&!inIsr&&!ret){if(step===inject)raise();step++;}
 if(reti){
  assert.ok(irq);assert.deepEqual(cpu.data.slice(0,32),irq.regs,'ISR restores all registers including interrupted r1');
  assert.equal(cpu.data[sreg],irq.sreg,'ISR restores SREG and I');assert.equal(cpu.SP,irq.sp);assert.equal(cpu.pc,irq.pc);
  if(irq.regs[1])nonzeroR1Interrupts++;injections++;irq=null;retChecks++;
 }
 cpu.tick();
 if(ret&&trace&&!inIsr&&cpu.SP===trace.sp+2){
  assert.equal(cpu.data[1],0);trace.elapsed=cpu.cycles-trace.start;lastTrace=trace;trace=null;
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
let lastTrace=null;
until(()=>cpu.data[status]===1);
const desc=Array.from({length:6},(_,i)=>cpu.dataView.getUint16(config+2*i,true));
sreg=desc[0];interrupt={address:desc[1],flagRegister:desc[2],flagMask:desc[3],enableRegister:desc[4],enableMask:desc[5]};
assert.ok(interrupt.address>0&&interrupt.flagMask&&interrupt.enableMask);
// Startup signals status immediately before SEI. Advance to its idle loop.
while(!cpu.interruptsEnabled){avrInstruction(cpu);cpu.tick();}
function oracle(p,f,n){const out=[...p],word=x=>Number(BigInt.asIntN(32,x)),q14=b=>(BigInt(f)*BigInt(b))>>14n;
 out[n+1]=word(2n*BigInt(p[n-1])-q14(p[n]));
 for(let j=n;j>=2;j--)out[j]=word(BigInt(p[j])-q14(p[j-1])+BigInt(p[j-2]));
 out[1]=word(BigInt(p[1])-BigInt(f)*64n);return out;
}
let calls=0,vectors=0;const traces={};
function call(p,f,n,mode,offset){
 const pp=work+(calls&255),beforeCount=cpu.dataView.getUint16(countAddress,true),beforeAccumulator=cpu.dataView.getUint16(accumulator,true);
 cpu.data.fill(0x69,work,work+384);for(let j=0;j<6;j++)cpu.dataView.setInt32(pp+4*j,p[j],true);
 const expected=cpu.data.slice(work,work+384),view=new DataView(expected.buffer),answer=oracle(p,f,n);
 for(let j=0;j<6;j++)view.setInt32(pp-work+4*j,answer[j],true);
 cpu.dataView.setUint16(pointer,pp,true);cpu.dataView.setInt16(fAddress,f,true);cpu.data[number]=n;
 lastTrace=null;inject=offset;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);
 assert.equal(trace,null);assert.equal(irq,null);assert.deepEqual(cpu.data.slice(work,work+384),expected,'Exact independent BigInt PCM-stage words and untouched guards');
 const expectedIrq=offset===-1?0:1;
 assert.equal(cpu.dataView.getUint16(countAddress,true),(beforeCount+expectedIrq)&65535);
 const u=beforeCount&255,product=((u+37)&255)*((u+129)&255);
 assert.equal(cpu.dataView.getUint16(accumulator,true),(beforeAccumulator+expectedIrq*product)&65535);
 calls++;return lastTrace;
}
const patterns=[
 [1048576,-536870912,536870911,-536870912,536870911,1234567],
 [1048576,536870848,-1,1,-1,-7654321],
 [1048576,-64,73400331,-20971523,6291457,0]
];
for(let n=2;n<=4;n++)for(const f of [-32768,-16384,-1,0,1,16384,32767])for(const p of patterns){
 const baseline=call(p,f,n,1,-1);assert.equal(baseline.n,n);baselineCycles[n].add(baseline.elapsed);
 assert.equal(baseline.ops.at(-1),0x9508);traces[n]=baseline.ops.length;
 call(p,f,n,2,-1); // same oracle, explicitly selected C fallback
 for(const offset of [-2,...Array.from({length:baseline.ops.length-1},(_,i)=>i)]){
  const preempted=call(p,f,n,1,offset);assert.deepEqual(preempted.ops,baseline.ops,'Interrupt preserves complete ASM instruction sequence');boundaryCounts[n]++;
 }
 vectors++;
}
assert.equal(vectors,63);assert.equal(injections,retChecks);assert.ok(nonzeroR1Interrupts>0);assert.equal(isrMulInstructions,injections);
assert.deepEqual(Object.fromEntries(Object.entries(baselineCycles).map(([n,s])=>[n,[...s]])),{'2':[238],'3':[327],'4':[416]});
for(const n of [2,3,4])assert.equal(boundaryCounts[n],21*traces[n]);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',
 binarySha256:createHash('sha256').update(binary).digest('hex'),deviceHeaders:JSON.parse(readFileSync(join(dir,'device-headers.json'),'utf8')),
 scope:'Synthetic Timer2 COMPA flag injected at entry and after every non-RET ASM instruction; real compiled ISR; timer-period playback tested separately',
 vectors,calls,boundaryCounts,asmInstructionsIncludingRet:traces,injections,nonzeroR1Interrupts,isrMulInstructions,retChecks,
 everyInstructionBoundaryPreempted:true,all32RegistersAndSregRestoredAtReti:true,interruptReturnPcAndSpExact:true,
 selectedAndForcedCExact:true,independentBigIntProductOracle:true,guardsAndUntouchedWordsPreserved:true,externalR1Zero:true,
 includesInterrupts:true,modelsHardwareEntryLatency:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
