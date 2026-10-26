// Independent BigInt updates for two disjoint polynomials, C/ASM and IRQ ABI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware'),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1],irqMode=process.argv.includes('--irq');assert.ok(['asm','c'].includes(backend));
assert.ok(!irqMode||backend==='asm');
const dir=fi<0?join(root,irqMode?'build/pair-irq':'build/pair-unit-'+backend):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'unit.bin')),program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),work=address('pair_work'),command=address('pair_command'),status=address('pair_status');
const args=['pair_p','pair_q','pair_fp','pair_fq','pair_number'].map(address);
const entries=new Map([...symbols].filter(([n])=>['pair_selected','pair_forced_c'].includes(n)||/^speex_avr_lsp_pair[234]$/.test(n)).map(([n,a])=>[a,n]));
for(const n of [2,3,4])assert.equal(symbols.has('speex_avr_lsp_pair'+n),backend==='asm');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let trace=null,lastTrace=null,watch=false,workWatch=false,workReads=[],workWrites=[],retChecks=0,asmCalls=0,readBytes=0,writtenBytes=0,maxStack=0;
let sreg,interrupt,irq=null,inject=-1,step=0,injections=0,nonzeroR1Interrupts=0,t0Interrupts=0,t1Interrupts=0,isrMulInstructions=0;
const cycles={2:new Set(),3:new Set(),4:new Set()},initialT=new Set(),read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)trace.reads.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+768)workReads.push(a[0]);return read.apply(this,a);};
cpu.writeData=function(...a){if(watch)trace.writes.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+768)workWrites.push(a[0]);return write.apply(this,a);};
function raise(){assert.equal(irq,null);assert.ok(cpu.data[sreg]&128);irq={regs:cpu.data.slice(0,32),sreg:cpu.data[sreg],sp:cpu.SP,pc:cpu.pc};cpu.setInterruptFlag(interrupt);}
function until(predicate){const deadline=cpu.cycles+300000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'pair mailbox timeout');const name=entries.get(cpu.pc*2);
 if(name&&!irq&&(!name.startsWith('speex_avr_lsp_pair')||!trace)){active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name.startsWith('speex_avr_lsp_pair')){
   assert.equal(trace,null);assert.equal(cpu.data[1],0);
   if(!irqMode)cpu.data[sreg]=(cpu.data[sreg]&~64)|((asmCalls&1)<<6);
   initialT.add((cpu.data[sreg]>>6)&1);
   trace={n:Number(name.at(-1)),p:cpu.dataView.getUint16(24,true),q:cpu.dataView.getUint16(22,true),sp:cpu.SP,reads:[],writes:[],pushes:[],pops:[],ops:[],start:cpu.cycles};step=0;
   if(inject===-2){raise();cpu.tick();assert.equal(cpu.pc,interrupt.address);continue;}
  }
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508,reti=op===0x9518,inIsr=irq!==null,externalRet=ret&&trace&&cpu.SP===trace.sp;
 if(trace&&!inIsr){trace.ops.push(op);if((op&0xfe0f)===0x920f)trace.pushes.push(cpu.SP);if((op&0xfe0f)===0x900f)trace.pops.push(cpu.SP+1);}
 if(inIsr&&(op&0xfc00)===0x9c00)isrMulInstructions++;
 watch=trace!==null&&!ret&&!inIsr;avrInstruction(cpu);watch=false;
 if(trace&&!inIsr&&!externalRet){if(step===inject)raise();step++;maxStack=Math.max(maxStack,trace.sp-cpu.SP);}
 if(reti){assert.ok(irq);assert.deepEqual(cpu.data.slice(0,32),irq.regs);assert.equal(cpu.data[sreg],irq.sreg);assert.equal(cpu.SP,irq.sp);assert.equal(cpu.pc,irq.pc);
  if(irq.regs[1])nonzeroR1Interrupts++;if(irq.sreg&64)t1Interrupts++;else t0Interrupts++;injections++;irq=null;
 }
 cpu.tick();
 if(ret&&!inIsr)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name.startsWith('speex_avr_lsp_pair')){
   const reads=[],writes=[];for(const p of [trace.p,trace.q]){for(let j=trace.n;j>=1;j--)for(let b=0;b<4;b++)reads.push(p+4*j+b);for(let j=trace.n+1;j>=1;j--)for(let b=0;b<4;b++)writes.push(p+4*j+b);}
   assert.deepEqual(trace.reads,reads);assert.deepEqual(trace.writes,writes);
   assert.deepEqual(trace.pushes,Array.from({length:16},(_,i)=>trace.sp-i));assert.deepEqual(trace.pops,[...trace.pushes].reverse());
   trace.elapsed=cpu.cycles-trace.start;if(inject===-1)cycles[trace.n].add(trace.elapsed);
   readBytes+=trace.reads.length;writtenBytes+=trace.writes.length;asmCalls++;lastTrace=trace;trace=null;
  }
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
sreg=cpu.dataView.getUint16(address('pair_config'),true);
let countAddress,accumulator;
if(irqMode){const config=address('pair_config'),d=Array.from({length:6},(_,i)=>cpu.dataView.getUint16(config+2*i,true));sreg=d[0];interrupt={address:d[1],flagRegister:d[2],flagMask:d[3],enableRegister:d[4],enableMask:d[5]};
 assert.ok(cpu.interruptsEnabled&&interrupt.address>0);countAddress=address('pair_irq_count');accumulator=address('pair_accumulator');}
let seed=0x71c943e5,cases=0,addressCases=0,calls=0,outputs=0;const perStage={2:0,3:0,4:0};
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function input(){const p=Array.from({length:6},(_,i)=>i?(((random()&0x3fffffff)^0x20000000)-0x20000000):1048576);p[1]&=~63;return p;}
function oracle(p,f,n){const out=[...p],word=x=>Number(BigInt.asIntN(32,x)),product=b=>(BigInt(f)*BigInt(b))>>14n;
 out[n+1]=word(2n*BigInt(p[n-1])-product(p[n]));for(let j=n;j>=2;j--)out[j]=word(BigInt(p[j])-product(p[j-1])+BigInt(p[j-2]));out[1]=word(BigInt(p[1])-BigInt(f)*64n);return out;}
function call(p,q,fp,fq,n,mode,offset=-1,low=calls&255,layout=0){
 const pp=work+low+(layout===2?32:0),qp=layout===1?pp+24:layout===2?pp-24:work+384+((low*37+73)&255);
 const beforeCount=irqMode?cpu.dataView.getUint16(countAddress,true):0,beforeAccumulator=irqMode?cpu.dataView.getUint16(accumulator,true):0;
 cpu.data.fill(0x69,work,work+768);for(const [ptr,values] of [[pp,p],[qp,q]])for(let j=0;j<6;j++)cpu.dataView.setInt32(ptr+4*j,values[j],true);
 const expected=cpu.data.slice(work,work+768),view=new DataView(expected.buffer),allowedReads=new Set(),allowedWrites=new Set();
 for(const [ptr,values,f] of [[pp,p,fp],[qp,q,fq]]){const answer=oracle(values,f,n);for(let j=0;j<6;j++)view.setInt32(ptr-work+4*j,answer[j],true);
  for(let i=0;i<4*(n+1);i++){allowedReads.add(ptr+i);allowedWrites.add(ptr+4+i);}}
 cpu.dataView.setUint16(args[0],pp,true);cpu.dataView.setUint16(args[1],qp,true);cpu.dataView.setInt16(args[2],fp,true);cpu.dataView.setInt16(args[3],fq,true);cpu.data[args[4]]=n;
 workReads=[];workWrites=[];workWatch=true;lastTrace=null;inject=offset;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);workWatch=false;
 assert.equal(active.length,0);assert.equal(trace,null);assert.equal(irq,null);assert.deepEqual(cpu.data.slice(work,work+768),expected);
 for(const a of workReads)assert.ok(allowedReads.has(a));for(const a of workWrites)assert.ok(allowedWrites.has(a));assert.equal(new Set(workWrites).size,8*(n+1));
 if(irqMode){const num=offset===-1?0:1,u=beforeCount&255;assert.equal(cpu.dataView.getUint16(countAddress,true),(beforeCount+num)&65535);assert.equal(cpu.dataView.getUint16(accumulator,true),(beforeAccumulator+num*((u+37)&255)*((u+129)&255))&65535);}
 calls++;return lastTrace;
}
function check(p,q,fp,fq,n,low=cases&255,layout=0){for(const mode of [1,2])call(p,q,fp,fq,n,mode,-1,low,layout);cases++;perStage[n]++;outputs+=2*(n+1);}
let irqVectors=0;const boundaryCounts={2:0,3:0,4:0},instructionCounts={};
if(irqMode){
 const patterns=[[1048576,-536870912,536870911,-536870912,536870911,1234567],[1048576,536870848,-1,1,-1,-7654321],[1048576,-64,73400331,-20971523,6291457,0]];
 for(let n=2;n<=4;n++)for(const f of [-32768,-16384,-1,0,1,16384,32767])for(let k=0;k<3;k++){
  const p=patterns[k],q=patterns[(k+1)%3],fq=(f*109+173)<<16>>16,base=call(p,q,f,fq,n,1);call(p,q,f,fq,n,2);instructionCounts[n]=base.ops.length;
  for(const offset of [-2,...Array.from({length:base.ops.length-1},(_,i)=>i)]){const checked=call(p,q,f,fq,n,1,offset);assert.deepEqual(checked.ops,base.ops);boundaryCounts[n]++;}irqVectors++;
 }
 assert.equal(irqVectors,63);assert.equal(isrMulInstructions,injections);assert.ok(nonzeroR1Interrupts>0&&t0Interrupts>0&&t1Interrupts>0);
 for(const n of [2,3,4])assert.equal(boundaryCounts[n],21*instructionCounts[n]);
}else{
 for(let n=2;n<=4;n++)for(let f=-32768;f<=32767;f++)check(input(),input(),f,(f*109+173)<<16>>16,n);
 for(let n=2;n<=4;n++)for(let i=0;i<16384;i++)check(input(),input(),random()<<16>>16,random()<<16>>16,n);
 const bound=[-536870912,-536870911,-73400331,-20971523,-6291457,-1,0,1,6291457,20971523,73400331,536870910,536870911],aligned=[-536870912,-8388608,-64,0,64,8388608,536870848];
 for(let n=2;n<=4;n++)for(const f of [-32768,-32767,-16384,-1,0,1,16383,16384,32766,32767])for(const p1 of aligned)for(let b=0;b<13;b++)for(const stride of [1,5,12]){
  const p=input(),q=input();p[1]=p1;q[1]=aligned[(b+stride)%7];for(let j=2;j<6;j++){p[j]=bound[(b+j*stride)%13];q[j]=bound[(b+2*j*stride)%13];}check(p,q,f,(-f)<<16>>16,n);
 }
 for(let n=2;n<=4;n++)for(const f of [-32768,0,32767])for(let low=0;low<256;low++){check(input(),input(),f,(~f)<<16>>16,n,low);addressCases++;}
 for(let n=2;n<=4;n++)for(let low=0;low<256;low++)for(const layout of [1,2]){check(input(),input(),-32768,32767,n,low,layout);addressCases++;}
 assert.equal(cases,257790);assert.equal(addressCases,3840);assert.equal(outputs,2062320);
 if(backend==='asm'){assert.equal(asmCalls,cases);assert.deepEqual([...initialT].sort(),[0,1]);assert.equal(maxStack,18);}
}
for(const values of Object.values(cycles))if(backend==='asm')assert.equal(values.size,1);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',backend,binarySha256:createHash('sha256').update(binary).digest('hex'),
 cases,calls,perStage,outputsPerPath:outputs,addressCases,all65536Signed16RootsAtBothInputs:!irqMode,independentBigIntProductOracle:true,
 selectedAndForcedCExact:true,guardsAndUntouchedWordsPreserved:true,calleeSavedRegistersAndR1AtRet:true,retChecks,
 exactAsmReadAndWriteAddresses:backend==='asm',asmCalls,readBytes,writtenBytes,stackBytesInsideAsm:maxStack,initialTStates:[...initialT].sort(),
 primitiveCyclesIncludingRet:backend==='asm'?Object.fromEntries(Object.entries(cycles).map(([n,s])=>[n,[...s]])):null,
 includesInterrupts:irqMode,physicalBoardTested:false};
if(irqMode)Object.assign(report,{irqVectors,deviceHeaders:JSON.parse(readFileSync(join(dir,'device-headers.json'),'utf8')),injections,nonzeroR1Interrupts,t0Interrupts,t1Interrupts,isrMulInstructions,
 boundaryCounts,instructionCounts,everyInstructionBoundaryIncludingInternalRetPreempted:true,all32RegistersAndSregRestoredAtReti:true,interruptReturnPcAndSpExact:true,modelsHardwareEntryLatency:false});
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
