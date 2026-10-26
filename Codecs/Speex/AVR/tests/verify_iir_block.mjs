// Both production C filters and selected backend against independent BigInt.
// IRQ mode interrupts every executed ASM boundary in one heavily preempted call.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/seed-iir-asm'):resolve(process.argv[fi+1]);
const metadata=JSON.parse(readFileSync(join(dir,'backend.json'),'utf8')),irqMode=metadata.irq;
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'unit.bin'));assert.equal(createHash('sha256').update(binary).digest('hex'),metadata.binarySha256);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const [work,command,status,orderAt,xa,da,oa,sa,config]=['iir_work','iir_command','iir_status','iir_order','iir_x','iir_den','iir_out','iir_state','iir_config'].map(address);
const entries=new Map(['speex_avr_iir40','speex_wb_iir40_avr'].filter(n=>symbols.has(n)).map(n=>[address(n),n]));
assert.equal(entries.size,metadata.backend==='asm'?2:0);
const callee=[...Array.from({length:16},(_,i)=>i+2),28,29];let active=null,trace=null,lastTrace=null,irq=null,preempt=false,sreg,interrupt;
let calls=0,cases=0,retChecks=0,injections=0,dirtyR1=0,isrMuls=0,minSP=2303,seed=0x2c713a69;
const timings={8:[],10:[]},tStates=new Set(),rows=[];
function raise(){assert.equal(irq,null);assert.ok(cpu.interruptsEnabled);irq={regs:cpu.data.slice(0,32),sreg:cpu.data[sreg],sp:cpu.SP,pc:cpu.pc};cpu.setInterruptFlag(interrupt);}
function until(predicate){const deadline=cpu.cycles+10000000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'IIR block timeout');const name=entries.get(cpu.pc*2);
 if(name&&!active&&!irq){active={sp:cpu.SP,regs:callee.map(r=>cpu.data[r]),begin:cpu.cycles};trace={ops:[],name};
  assert.equal(cpu.data[1],0);cpu.data[sreg]=(cpu.data[sreg]&~64)|((cases&1)<<6);tStates.add((cpu.data[sreg]>>6)&1);
  if(preempt){raise();cpu.tick();continue;}
 }
 const op=cpu.progMem[cpu.pc],inIsr=irq!==null,ret=op===0x9508,reti=op===0x9518;
 if(trace&&!inIsr)trace.ops.push(op);if(inIsr&&(op&0xfc00)===0x9c00)isrMuls++;
 avrInstruction(cpu);minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=address('__bss_end'));
 if(reti){assert.ok(irq);assert.deepEqual(cpu.data.slice(0,32),irq.regs);assert.equal(cpu.data[sreg],irq.sreg);assert.equal(cpu.SP,irq.sp);assert.equal(cpu.pc,irq.pc);
  dirtyR1+=Number(irq.regs[1]!==0);injections++;irq=null;
 }
 if(active&&!inIsr&&ret&&cpu.SP===active.sp+2){
  assert.deepEqual(callee.map(r=>cpu.data[r]),active.regs);assert.equal(cpu.data[1],0);retChecks++;
  trace.elapsed=cpu.cycles-active.begin;lastTrace=trace;trace=null;active=null;
 } else if(trace&&!inIsr&&preempt)raise();
 cpu.tick();
}}
until(()=>cpu.data[status]===1);sreg=cpu.dataView.getUint16(config,true);
if(irqMode){const d=Array.from({length:6},(_,i)=>cpu.dataView.getUint16(config+2*i,true));interrupt={address:d[1],flagRegister:d[2],flagMask:d[3],enableRegister:d[4],enableMask:d[5]};assert.ok(cpu.interruptsEnabled);}
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed<<16)>>16;}
const signed32=n=>BigInt.asIntN(32,n),clip=n=>Number(n>32767n?32767n:n< -32767n?-32767n:n);
function oracle(input,den,state,n){let pos=0;const out=[],next=[...state];
 for(const x of input){let sum=0n;for(let j=0;j<n;j++)sum+=BigInt(next[2*n+j])*BigInt(next[pos+n-1-j]);
  const y=clip(BigInt(x)+(signed32(signed32(sum)+4096n)>>13n));out.push(y);next[pos]=next[pos+n]=-y;
  if(++pos===n)pos=0;if(out.length<=n)next[2*n+out.length-1]=den[out.length-1];
 }return {out,state:next};
}
function run(input,den,state,n,mode,low,inPlace,inject=false){
 const x=work+4+(cases&31),out=inPlace?x:work+132+(cases&63),coef=work+284,mem=work+352+low;
 cpu.data.fill(0x69,work,work+768);for(let i=0;i<40;i++)cpu.dataView.setInt16(x+2*i,input[i],true);
 for(let j=0;j<n;j++)cpu.dataView.setInt16(coef+2*j,den[j],true);for(let j=0;j<3*n;j++)cpu.dataView.setInt16(mem+2*j,state[j],true);
 const expected=cpu.data.slice(work,work+768),view=new DataView(expected.buffer),answer=oracle(input,den,state,n);
 for(let i=0;i<40;i++)view.setInt16(out-work+2*i,answer.out[i],true);for(let j=0;j<3*n;j++)view.setInt16(mem-work+2*j,answer.state[j],true);
 for(const [at,pointer] of [[xa,x],[da,coef],[oa,out],[sa,mem]])cpu.dataView.setUint16(at,pointer,true);
 cpu.data[orderAt]=n;if(irqMode){cpu.dataView.setUint16(address('iir_irq_count'),0,true);cpu.dataView.setUint16(address('iir_accumulator'),0,true);}
 lastTrace=null;const previousIrqs=injections;preempt=inject;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);preempt=false;
 assert.equal(active,null);assert.equal(trace,null);assert.equal(irq,null);assert.deepEqual(cpu.data.slice(work,work+768),expected,'Outputs/state/guards order '+n+' case '+cases+' mode '+mode);
 if(mode===1&&lastTrace&&!inject)timings[n].push(lastTrace.elapsed);
 if(irqMode){const num=injections-previousIrqs;let acc=0;for(let k=0;k<num;k++)acc=(acc+((k+37)&255)*((k+129)&255))&65535;
  assert.equal(cpu.dataView.getUint16(address('iir_irq_count'),true),num&65535);assert.equal(cpu.dataView.getUint16(address('iir_accumulator'),true),acc);
  if(inject)assert.equal(num,lastTrace.ops.length,'Entry plus every non-RET boundary');
 }calls++;return lastTrace;
}
if(irqMode){
 for(const n of [8,10])for(let pattern=0;pattern<4;pattern++){
  const den=Array.from({length:n},()=>random()),history=Array.from({length:n},()=>pattern?random():0),state=[...history,...history,...den];
  const input=Array.from({length:40},(_,i)=>pattern===0?0:pattern===1?(i&1?-32768:32767):pattern===2?(i&1?32767:-32768):random());
  const normal=run(input,den,state,n,1,pattern*73&255,!!(pattern&1));run(input,den,state,n,2,pattern*73&255,!!(pattern&1));
  const interrupted=run(input,den,state,n,1,pattern*73&255,!!(pattern&1),true);assert.deepEqual(interrupted.ops,normal.ops);
  rows.push({order:n,pattern,executedBoundaries:normal.ops.length,primitiveCycles:normal.elapsed});cases++;
 }
 assert.equal(isrMuls,injections);assert.ok(dirtyR1>0);assert.deepEqual([...tStates].sort(),[0,1]);
}else{
 for(const n of [8,10])for(const inPlace of [false,true])for(let low=0;low<256;low++){
  let history=Array.from({length:n},()=>random()),state=[...history,...history,...Array.from({length:n},()=>random())];
  for(let block=0;block<4;block++){
   const input=Array.from({length:40},()=>random()),den=Array.from({length:n},()=>random());
   for(const mode of [1,2])run(input,den,state,n,mode,low,inPlace);state=oracle(input,den,state,n).state;cases++;
  }
 }
 // Every signed16 input is passed through a zero-coefficient filter: verify
 // clipping plus every reachable 16-bit history negation and low-byte carry.
 for(const n of [8,10])for(let first=-32768;first<=32767;first+=40){
  const input=Array.from({length:40},(_,i)=>Math.min(32767,first+i)),den=Array(n).fill(0),state=Array(3*n).fill(0);
  for(const mode of [1,2])run(input,den,state,n,mode,cases&255,!!(cases&1));cases++;
 }
}
const result={backend:metadata.backend,binarySha256:metadata.binarySha256,mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',
 cases,calls,samplesPerPath:cases*40,orders:[8,10],selectedAndExplicitProductionCExact:true,independentBigIntOracle:true,
 fullSigned16InputNegationSweep:!irqMode,statePageLowBytes:irqMode?null:256,inPlaceAndSeparate:true,wholeWorkArenaAndGuardsExact:true,
 calleeSavedAndR1AtRet:retChecks,peakStackBytes:2303-minSP,includesInterrupts:irqMode,physicalBoardTested:false,
 primitiveCyclesIncludingRet:Object.fromEntries([8,10].map(n=>[n,{min:Math.min(...timings[n]),max:Math.max(...timings[n])}]))};
if(irqMode)Object.assign(result,{injections,nonzeroR1Interrupts:dirtyR1,isrMulInstructions:isrMuls,everyExecutedBoundaryPreempted:true,
 all32RegistersAndSregRestoredAtReti:true,interruptPcAndSpRestored:true,traceUnchanged:true,modelsHardwareEntryLatency:false,vectors:rows,deviceHeaders:metadata.headers});
writeFileSync(join(dir,'verification.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
