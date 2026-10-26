// Full signed16 angle domain: selected backend, explicit C, untouched Xiph.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware'),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1],irqMode=process.argv.includes('--irq');assert.ok(['asm','c'].includes(backend)&&(!irqMode||backend==='asm'));
const dir=fi<0?join(root,irqMode?'build/angle-irq':'build/angle-unit-'+backend):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'unit.bin')),program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),input=address('angle_input'),output=address('angle_result'),command=address('angle_command'),status=address('angle_status');
const entries=new Map([...symbols].filter(([n])=>['angle_selected','angle_forced_c','reference_lsp_angle','speex_avr_lsp_angle'].includes(n)).map(([n,a])=>[a,n]));
assert.equal(symbols.has('speex_avr_lsp_angle'),backend==='asm');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[],cycles=new Map(),initialT=new Set();
let sreg,interrupt,irq=null,trace=null,lastTrace=null,inject=-1,step=0,asmCalls=0,retChecks=0,ownStack=0,watch=false,reads=0,writes=0;
let injections=0,nonzeroR1Interrupts=0,t0Interrupts=0,t1Interrupts=0,isrMulInstructions=0,calls=0;
const read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)reads++;return read.apply(this,a);};cpu.writeData=function(...a){if(watch)writes++;return write.apply(this,a);};
function raise(){assert.equal(irq,null);assert.ok(cpu.data[sreg]&128);irq={regs:cpu.data.slice(0,32),sreg:cpu.data[sreg],sp:cpu.SP,pc:cpu.pc};cpu.setInterruptFlag(interrupt);}
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'angle mailbox timeout');const name=entries.get(cpu.pc*2);
 if(name&&!irq&&(name!=='speex_avr_lsp_angle'||!trace)){
  active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name==='speex_avr_lsp_angle'){
   assert.equal(cpu.data[1],0);if(!irqMode)cpu.data[sreg]=(cpu.data[sreg]&~64)|((calls&1)<<6);initialT.add((cpu.data[sreg]>>6)&1);
   trace={sp:cpu.SP,ops:[],start:cpu.cycles};step=0;
   if(inject===-2){raise();cpu.tick();assert.equal(cpu.pc,interrupt.address);continue;}
  }
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508,reti=op===0x9518,inIsr=irq!==null;
 if(trace&&!inIsr)trace.ops.push(op);if(inIsr&&(op&0xfc00)===0x9c00)isrMulInstructions++;
 watch=!!trace&&!inIsr&&!ret;avrInstruction(cpu);watch=false;
 if(trace&&!inIsr&&!ret){if(step===inject)raise();step++;ownStack=Math.max(ownStack,trace.sp-cpu.SP);}
 if(reti){assert.ok(irq);assert.deepEqual(cpu.data.slice(0,32),irq.regs);assert.equal(cpu.data[sreg],irq.sreg);assert.equal(cpu.SP,irq.sp);assert.equal(cpu.pc,irq.pc);
  if(irq.regs[1])nonzeroR1Interrupts++;if(irq.sreg&64)t1Interrupts++;else t0Interrupts++;injections++;irq=null;}
 cpu.tick();
 if(ret&&!inIsr)while(active.length&&cpu.SP===active.at(-1).sp+2){const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name==='speex_avr_lsp_angle'){
   trace.elapsed=cpu.cycles-trace.start;lastTrace=trace;if(inject===-1)cycles.set(trace.elapsed,(cycles.get(trace.elapsed)||0)+1);trace=null;asmCalls++;
  }}
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);const config=address('angle_config');sreg=cpu.dataView.getUint16(config,true);
let count,accumulator;if(irqMode){const d=Array.from({length:6},(_,i)=>cpu.dataView.getUint16(config+2*i,true));interrupt={address:d[1],flagRegister:d[2],flagMask:d[3],enableRegister:d[4],enableMask:d[5]};assert.ok(cpu.interruptsEnabled);count=address('angle_irq_count');accumulator=address('angle_accumulator');}
const w=x=>BigInt.asIntN(16,x);
function oracle(value){let x=BigInt(value),negative=x>=12868n;if(negative)x=w(25736n-x);const y=w((x*x+4096n)>>13n),a=w(340n+((4096n-10n*y)>>13n)),b=w(-4096n+((y*a+4096n)>>13n)),p=(y*b+4096n)>>13n;return Number(w(w(negative?-8192n-p:8192n+p)<<2n));}
function call(value,mode,offset=-1){
 const previousCount=irqMode?cpu.dataView.getUint16(count,true):0,previousAccumulator=irqMode?cpu.dataView.getUint16(accumulator,true):0;
 cpu.dataView.setInt16(input,value,true);cpu.dataView.setInt16(output,0x5a5a,true);cpu.data[status]=1;cpu.data[command]=mode;inject=offset;lastTrace=null;until(()=>cpu.data[status]===2);
 assert.equal(active.length,0);assert.equal(trace,null);assert.equal(irq,null);assert.equal(cpu.dataView.getInt16(output,true),oracle(value),'angle '+value+' mode '+mode);assert.equal(cpu.dataView.getInt16(input,true),value);
 if(irqMode){const num=offset===-1?0:1,u=previousCount&255;assert.equal(cpu.dataView.getUint16(count,true),(previousCount+num)&65535);assert.equal(cpu.dataView.getUint16(accumulator,true),(previousAccumulator+num*((u+37)&255)*((u+129)&255))&65535);}
 calls++;return lastTrace;
}
let cases=0;const boundaries=[];
if(!irqMode){for(let value=-32768;value<=32767;value++){for(const mode of [1,2,3])call(value,mode);cases++;}assert.equal(cases,65536);if(backend==='asm'){assert.equal(asmCalls,cases);assert.deepEqual([...initialT].sort(),[0,1]);}}
else{
 for(const value of [-32768,-32767,-30000,-16385,-16384,-1,0,1,12867,12868,16384,25735,25736,32767]){
  const base=call(value,1);call(value,2);call(value,3);
  for(const offset of [-2,...Array.from({length:base.ops.length-1},(_,i)=>i)])assert.deepEqual(call(value,1,offset).ops,base.ops);
  boundaries.push({value,instructions:base.ops.length});cases++;
 }
 assert.equal(injections,boundaries.reduce((sum,r)=>sum+r.instructions,0));assert.ok(nonzeroR1Interrupts&&t0Interrupts&&t1Interrupts);assert.equal(isrMulInstructions,injections);
}
if(backend==='asm'){assert.equal(ownStack,0);assert.equal(reads,0);assert.equal(writes,0);}
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',backend,binarySha256:createHash('sha256').update(binary).digest('hex'),
 cases,calls,asmCalls,retChecks,fullSigned16Domain:!irqMode,selectedForcedCAndUntouchedXiphExact:true,independentBigIntOracle:true,inputPreserved:true,
 calleeSavedRegistersAndR1AtRet:true,initialTStates:[...initialT].sort(),ownStackBytes:ownStack,ramReadsInsideAsm:reads,ramWritesInsideAsm:writes,
 primitiveCyclesIncludingRet:[...cycles].sort((a,b)=>a[0]-b[0]).map(([cycles,calls])=>({cycles,calls})),includesInterrupts:irqMode,physicalBoardTested:false};
if(irqMode)Object.assign(report,{boundaries,injections,nonzeroR1Interrupts,t0Interrupts,t1Interrupts,isrMulInstructions,all32RegistersAndSregRestoredAtReti:true,interruptReturnPcAndSpExact:true,everyInstructionBoundaryPreempted:true,modelsHardwareEntryLatency:false,deviceHeaders:JSON.parse(readFileSync(join(dir,'device-headers.json'),'utf8'))});
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
