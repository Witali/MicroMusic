import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(process.env.AVR8JS_PACKAGE);
const {CPU,avrInstruction,AVRTimer,timer2Config}=require('avr8js');
import {tickAvr} from './avr_tick.mjs';

const dir=resolve(process.argv[2]),quick=process.argv.includes('--quick'),irq=process.argv.includes('--irq');
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
const sha=data=>createHash('sha256').update(data).digest('hex');
assert.equal(sha(binary),meta.binarySha256);
for(const [name,digest] of Object.entries(meta.sourceSha256))assert.equal(sha(readFileSync(join(dir,'..',name),'utf8').replace(/\r\n/g,'\n')),digest,'Source binding: '+name);
const verifierSha256=sha(readFileSync(fileURLToPath(import.meta.url),'utf8').replace(/\r\n/g,'\n'));
const tickSha256=sha(readFileSync(fileURLToPath(new URL('./avr_tick.mjs',import.meta.url)),'utf8').replace(/\r\n/g,'\n'));
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [work,pointers,status,command,end,config,irqCount,irqSum]=['finish_work','finish_addresses','finish_status',
 'finish_command','__bss_end','finish_device','finish_irq_count','finish_irq_sum'].map(at);
const asmName='speex_avr_lsp_finish10',names=[asmName,'finish10_selected','finish10_paired_c','finish10_sequential_os','finish10_sequential_o3'];
const entries=new Map(names.map(n=>[at(n),n]));assert.equal(entries.size,names.length,'Distinct scalar entries');
const stats=Object.fromEntries(names.map(n=>[n,{calls:0,min:Infinity,max:0,total:0,last:0}]));
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);new AVRTimer(cpu,timer2Config);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let trace=null,watch=false,workWatch=false,workReads=[],workWrites=[],retChecks=0,asmCalls=0,minSP=2303;
let insideIrq=false,irqVector=-1,irqEntries=0,irqReturns=0,timerEvents=0,leafSaved=0;
const setFlag=cpu.setInterruptFlag.bind(cpu);cpu.setInterruptFlag=i=>{if(i.address===timer2Config.compAInterrupt)++timerEvents;setFlag(i);};
const oldRead=cpu.readData.bind(cpu),oldWrite=cpu.writeData.bind(cpu);
cpu.readData=(a,...rest)=>{if(watch)trace.reads.push(a);if(workWatch&&a>=work&&a<work+1152)workReads.push(a);return oldRead(a,...rest);};
cpu.writeData=(a,...rest)=>{if(watch)trace.writes.push(a);if(workWatch&&a>=work&&a<work+1152)workWrites.push(a);return oldWrite(a,...rest);};
function until(done){const limit=cpu.cycles+100000;while(!done()){
 assert.ok(cpu.cycles<limit,'Finish mailbox timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(pc===irqVector){assert.equal(insideIrq,false);insideIrq=true;++irqEntries;}
 const name=entries.get(pc);
 if(name){
  const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(retChecks*73+r*29)&255);
  if(name===asmName)saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active.push({name,sp:cpu.SP,original,expected:name===asmName?patterns:original,cycles:0});
  if(name===asmName){
   assert.equal(trace,null);assert.equal(cpu.data[1],0);
   trace={p:cpu.dataView.getUint16(24,true),q:cpu.dataView.getUint16(22,true),a:cpu.dataView.getUint16(20,true),
    sp:cpu.SP,reads:[],writes:[],pushes:[],pops:[]};
  }
 }
 const returning=opcode===0x9508;
 if(trace&&!insideIrq){if((opcode&0xfe0f)===0x920f)trace.pushes.push(cpu.SP);if((opcode&0xfe0f)===0x900f)trace.pops.push(cpu.SP+1);}
 watch=trace!==null&&!insideIrq&&!returning;
 const before=cpu.cycles,enabled=cpu.interruptsEnabled;avrInstruction(cpu);watch=false;
 if(!insideIrq)for(const frame of active)frame.cycles+=cpu.cycles-before;
 if(trace&&!insideIrq&&!returning)leafSaved=Math.max(leafSaved,trace.sp-cpu.SP);
 if(returning)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop(),s=stats[frame.name];assert.deepEqual(saved.map(r=>cpu.data[r]),frame.expected);assert.equal(cpu.data[1],0);++retChecks;
  ++s.calls;s.min=Math.min(s.min,frame.cycles);s.max=Math.max(s.max,frame.cycles);s.total+=frame.cycles;s.last=frame.cycles;
  if(frame.name===asmName){
   const reads=[],writes=[];
   for(let j=1;j<=5;j++){
    for(let b=0;b<4;b++)reads.push(trace.p+4*j+b);
    for(let b=0;b<4;b++)reads.push(trace.q+4*j+b);
    writes.push(trace.a+2*(j-1),trace.a+2*(j-1)+1);
    if(['loop','inline'].includes(meta.variant))writes.push(trace.a+2*(10-j)+1,trace.a+2*(10-j));
    else writes.push(trace.a+2*(10-j),trace.a+2*(10-j)+1);
   }
   assert.deepEqual(trace.reads,reads,'Exactly one read of p/q[1..4]');
   assert.deepEqual(trace.writes,writes,'Only the eight paired outputs');
   assert.deepEqual(trace.pushes,Array.from({length:meta.savedRegisters},(_,i)=>trace.sp-i));
   assert.deepEqual(trace.pops,[...trace.pushes].reverse());
   saved.forEach((r,i)=>{cpu.data[r]=frame.original[i];});trace=null;++asmCalls;
  }
 }
 if(opcode===0x9518){assert.ok(insideIrq);insideIrq=false;++irqReturns;}
 tickAvr(cpu,enabled);minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack/static collision');
}}
until(()=>cpu.data[status]===1);
irqVector=2*cpu.dataView.getUint16(config+4,true);assert.equal(irqVector,2*timer2Config.compAInterrupt);
const clockAddress=cpu.dataView.getUint16(config,true),clockValue=cpu.dataView.getUint16(config+2,true);
if(irq)cpu.writeData(clockAddress,clockValue);
let seed=0x8fe1973a,cases=0,addressCases=0,positiveClips=0,negativeClips=0;
const workloads={};
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function randomInput(){return [Array.from({length:6},(_,i)=>i?random():1048576),Array.from({length:6},(_,i)=>i?random():1048576)];}
function oracle(p,q){const out=[];let pp=0n,pq=0n;for(let j=1;j<=10;j++){
 const i=j<=5?j:10-j;let value=BigInt.asIntN(32,BigInt(p[i])+pp+BigInt(q[i])-pq+128n)>>8n;
 pp=BigInt(p[i]);pq=BigInt(q[i]);if(value>32767n){value=32767n;++positiveClips;}if(value< -32767n){value=-32767n;++negativeClips;}out.push(Number(value));
}return out;}
const modeNames={1:'finish10_selected',2:'finish10_paired_c',3:'finish10_sequential_os',4:'finish10_sequential_o3',5:asmName};
function check(p,q,label,low=cases&255){
 assert.equal(p[0],1048576);assert.equal(q[0],1048576);
 const pp=work+low,qp=work+384+((low*73)&255),ap=work+768+((low*151)&255),answer=oracle(p,q);
 const inputs=new Set([...Array.from({length:24},(_,i)=>pp+i),...Array.from({length:24},(_,i)=>qp+i)]);
 const outputs=new Set(Array.from({length:20},(_,i)=>ap+i));
 const group=workloads[label]??={cases:0,paths:Object.fromEntries(Object.values(modeNames).map(n=>[n,{total:0,min:Infinity,max:0}]))};
 for(const mode of [1,2,3,4,5]){
  cpu.data.fill(0x69,work,work+1152);
  for(let i=0;i<6;i++){cpu.dataView.setUint32(pp+4*i,p[i],true);cpu.dataView.setUint32(qp+4*i,q[i],true);}
  const expected=cpu.data.slice(work,work+1152),view=new DataView(expected.buffer);
  answer.forEach((value,i)=>view.setInt16(ap-work+2*i,value,true));
  [pp,qp,ap].forEach((value,i)=>cpu.dataView.setUint16(pointers+2*i,value,true));
  const asmBefore=asmCalls;workReads=[];workWrites=[];workWatch=true;
  cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);workWatch=false;
  assert.equal(active.length,0);assert.equal(trace,null);
  assert.deepEqual(cpu.data.slice(work,work+1152),expected,'Output, inputs and guards');
  for(const a of workReads)assert.ok(inputs.has(a));for(const a of workWrites)assert.ok(outputs.has(a));
  assert.equal(new Set(workWrites).size,20);
  assert.equal(asmCalls-asmBefore,mode===5||(mode===1&&meta.backend==='asm')?1:0,'Explicit backend selection');
  const s=group.paths[modeNames[mode]],cycles=stats[modeNames[mode]].last;s.total+=cycles;s.min=Math.min(s.min,cycles);s.max=Math.max(s.max,cycles);
 }
 ++cases;++group.cases;
}
for(let i=0;i<(quick?32:2048);i++)check(...randomInput(),'random');
const high=[0,1,0x007ffe,0x007fff,0x008000,0x008001,0x7ffffe,0x7fffff,0x800000,0x800001,0xff7ffe,0xff7fff,0xff8000,0xff8001,0xff8002,0xfffffe,0xffffff];
const lows=quick?[0,1,127,128,255]:Array.from({length:256},(_,i)=>i);
for(const h of high)for(const low of lows)for(let j=1;j<=5;j++)for(const mirror of [false,true]){
 const [p,q]=randomInput(),target=(h*256+low)>>>0;
 p[j]=(mirror?target-p[j-1]+q[j]-q[j-1]:target-p[j-1]-q[j]+q[j-1])>>>0;check(p,q,'boundary');
}
for(let model=0;model<4;model++)for(const low of lows){
 const [p,q]=randomInput();
 if(model===1)for(let j=1;j<=5;j++)p[j]=q[j]=0;
 if(model===2)for(let j=1;j<=5;j++){p[j]=(j%2?0x007fff80:0xff80007f)>>>0;q[j]=0;}
 if(model===3)for(let j=1;j<=5;j++){p[j]=(j%2?0x7fffff80:0x80000080)>>>0;q[j]=0x80000000;}
 check(p,q,'address',low);++addressCases;
}
function polynomial(roots){
 const word=n=>BigInt.asIntN(32,n),p=[1048576n,word(-BigInt(roots[0]+roots[1])*64n),(BigInt(roots[0])*BigInt(roots[1])+536871167n)>>8n,0n,0n,0n];
 for(let stage=2;stage<=4;stage++){
  const f=BigInt(roots[stage]);p[stage+1]=word(2n*p[stage-1]-((f*p[stage])>>14n));
  for(let j=stage;j>=2;j--)p[j]=word(p[j]-((f*p[j-1])>>14n)+p[j-2]);p[1]=word(p[1]-64n*f);
 }
 return p.map(n=>Number(BigInt.asUintN(32,n)));
}
for(let i=0;i<(quick?64:4096);i++){
 const roots=[31000,26000,20000,13000,5000,-5000,-13000,-20000,-26000,-31000].map(n=>n+random()%1025-512);
 check(polynomial([roots[0],roots[2],roots[4],roots[6],roots[8]]),polynomial([roots[1],roots[3],roots[5],roots[7],roots[9]]),'structured');
}
if(irq){
 cpu.writeData(clockAddress,0);until(()=>!insideIrq&&cpu.dataView.getUint32(irqCount,true)===timerEvents&&cpu.interruptsEnabled);
 assert.equal(irqEntries,timerEvents);assert.equal(irqReturns,timerEvents);
 let sum=0;for(let i=0;i<timerEvents;i++)sum=(sum+(((i+37)&255)*((i+129)&255)))&65535;
 assert.equal(cpu.dataView.getUint16(irqSum,true),sum);
}else assert.equal(timerEvents,0);
assert.equal(cases,quick?966:50688);assert.ok(positiveClips&&negativeClips);assert.equal(leafSaved,meta.stackBytes);
assert.equal(asmCalls,cases*(meta.backend==='asm'?2:1));
for(const group of Object.values(workloads))for(const s of Object.values(group.paths))s.mean=s.total/group.cases;
const disassembly=readFileSync(join(dir,'disassembly.txt'),'utf8'),functions=[...disassembly.matchAll(/^([0-9a-f]+) <([^>]+)>:/gm)];
const bytes=Object.fromEntries(names.map(name=>{const i=functions.findIndex(m=>m[2]===name);return [name,parseInt(functions[i+1][1],16)-parseInt(functions[i][1],16)];}));
const report={scope:'Isolated order-ten polynomial finish; no C decoder runtime',backend:meta.backend,binarySha256:meta.binarySha256,
 verifierSha256,tickSha256,variant:meta.variant,order:meta.order,sourceSha256:meta.sourceSha256,cases,addressCases,all256LowBytes:!quick,outputsPerPath:10*cases,independentSequentialBigIntExact:true,
 originalSequentialAndPairedCExact:true,guardsAndReadonlyInputs:true,exactAsmReadBytesPerCall:40,exactAsmWrittenBytesPerCall:20,
 arbitraryCalleeSavedPatterns:true,calleeSavedAndR1Returns:retChecks,asmCalls,savedStackBytes:leafSaved,fixturePeakStack:2303-minSP,
 includesInterrupts:irq,timerEvents,completedTimerInterrupts:irqReturns,noLostTimerInterrupts:irq?irqReturns===timerEvents:null,
 positiveClips,negativeClips,stats,workloads,functionBytes:bytes,physicalBoardTested:false};
writeFileSync(join(dir,`verification-${quick?'quick':'full'}${irq?'-irq':''}.json`),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({variant:meta.variant,order:meta.order,backend:meta.backend,cases,irq,timerEvents,leafSaved,stats,bytes}));
