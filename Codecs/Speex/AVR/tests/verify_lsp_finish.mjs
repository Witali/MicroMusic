// Independent ten-output unsigned-32 oracle, exact AVR memory accesses and ABI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1];assert.ok(['asm','c'].includes(backend));
const dir=join(root,'build/pair-finish-unit-'+backend);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'finish.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('finish_work'),pointers=address('finish_addresses'),status=address('finish_status'),command=address('finish_command');
const names=['finish_selected','finish_forced_c'];for(const n of names)assert.ok(symbols.has(n));
assert.equal(symbols.has('speex_avr_lsp_finish10'),backend==='asm');
const entries=new Map([...symbols].filter(([n])=>names.includes(n)||n==='speex_avr_lsp_finish10').map(([n,a])=>[a,n]));
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let trace=null,watch=false,workWatch=false,workReads=[],workWrites=[],retChecks=0,asmCalls=0,asmReadBytes=0,asmWrittenBytes=0;
let minCycles=Infinity,maxCycles=0,totalCycles=0,peakSavedStack=0,positiveClips=0,negativeClips=0;
const read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)trace.reads.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+1152)workReads.push(a[0]);return read.apply(this,a);};
cpu.writeData=function(...a){if(watch)trace.writes.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+1152)workWrites.push(a[0]);return write.apply(this,a);};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'finish mailbox timeout');
 const name=entries.get(cpu.pc*2);
 if(name){active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name==='speex_avr_lsp_finish10'){
   assert.equal(trace,null);assert.equal(cpu.data[1],0);
   trace={p:cpu.dataView.getUint16(24,true),q:cpu.dataView.getUint16(22,true),a:cpu.dataView.getUint16(20,true),
    sp:cpu.SP,reads:[],writes:[],pushes:[],pops:[],start:cpu.cycles};
  }
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508;
 if(trace){if((op&0xfe0f)===0x920f)trace.pushes.push(cpu.SP);if((op&0xfe0f)===0x900f)trace.pops.push(cpu.SP+1);}
 watch=trace!==null&&!ret;avrInstruction(cpu);cpu.tick();watch=false;
 if(trace&&!ret)peakSavedStack=Math.max(peakSavedStack,trace.sp-cpu.SP);
 if(ret)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name==='speex_avr_lsp_finish10'){
   const expectedReads=[],expectedWrites=[];
   for(let j=1;j<=5;j++){
    for(let b=0;b<4;b++)expectedReads.push(trace.p+4*j+b);
    for(let b=0;b<4;b++)expectedReads.push(trace.q+4*j+b);
    expectedWrites.push(trace.a+2*(j-1),trace.a+2*(j-1)+1,trace.a+2*(10-j),trace.a+2*(10-j)+1);
   }
   assert.deepEqual(trace.reads,expectedReads,'Each p/q[1..5] byte read exactly once');
   assert.deepEqual(trace.writes,expectedWrites,'Only the ten paired coefficients are stored');
   assert.deepEqual(trace.pushes,Array.from({length:14},(_,i)=>trace.sp-i));
   assert.deepEqual(trace.pops,[...trace.pushes].reverse());
   const cycles=cpu.cycles-trace.start;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);totalCycles+=cycles;
   asmReadBytes+=trace.reads.length;asmWrittenBytes+=trace.writes.length;asmCalls++;trace=null;
  }
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
let seed=0x8fe1973a,cases=0,addressCases=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function randomInput(){return [Array.from({length:6},(_,i)=>i?random():1048576),Array.from({length:6},(_,i)=>i?random():1048576)];}
function oracle(p,q){const out=[];let pp=0,pq=0;for(let j=1;j<=10;j++){
 const i=j<=5?j:10-j,sum=(p[i]+pp+q[i]-pq)>>>0;let a=((sum+128)|0)>>8;
 pp=p[i];pq=q[i];if(a>32767){a=32767;positiveClips++;}if(a< -32767){a=-32767;negativeClips++;}out.push(a);
}return out;}
function check(p,q,low=cases&255){
 assert.equal(p[0],1048576);assert.equal(q[0],1048576);
 const pp=work+low,qp=work+384+((low*73)&255),ap=work+768+((low*151)&255),answer=oracle(p,q);
 const input=new Set([...Array.from({length:24},(_,i)=>pp+i),...Array.from({length:24},(_,i)=>qp+i)]);
 const output=new Set(Array.from({length:20},(_,i)=>ap+i));
 for(const mode of [1,2]){
  cpu.data.fill(0x69,work,work+1152);
  for(let i=0;i<6;i++){cpu.dataView.setUint32(pp+4*i,p[i],true);cpu.dataView.setUint32(qp+4*i,q[i],true);}
  const expected=cpu.data.slice(work,work+1152),view=new DataView(expected.buffer);
  for(let i=0;i<10;i++)view.setInt16(ap-work+2*i,answer[i],true);
  for(const [i,a] of [pp,qp,ap].entries())cpu.dataView.setUint16(pointers+2*i,a,true);
  workReads=[];workWrites=[];workWatch=true;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);workWatch=false;
  assert.equal(active.length,0);assert.equal(trace,null);
  assert.deepEqual(cpu.data.slice(work,work+1152),expected,'Inputs and all memory outside output preserved');
  for(const a of workReads)assert.ok(input.has(a));for(const a of workWrites)assert.ok(output.has(a));
  assert.equal(new Set(workWrites).size,20);
 }
 cases++;
}
for(let i=0;i<2048;i++)check(...randomInput());
const high=[0,1,0x007ffe,0x007fff,0x008000,0x008001,0x7ffffe,0x7fffff,0x800000,0x800001,0xff7ffe,0xff7fff,0xff8000,0xff8001,0xff8002,0xfffffe,0xffffff];
for(const h of high)for(let low=0;low<256;low++)for(let j=1;j<=5;j++)for(const mirror of [false,true]){
 const [p,q]=randomInput(),target=((h*256)+low)>>>0;
 p[j]=(mirror?target-p[j-1]+q[j]-q[j-1]:target-p[j-1]-q[j]+q[j-1])>>>0;check(p,q);
}
for(let model=0;model<4;model++)for(let low=0;low<256;low++){
 const [p,q]=randomInput();
 if(model===1)for(let j=1;j<=5;j++)p[j]=q[j]=0;
 if(model===2)for(let j=1;j<=5;j++){p[j]=(j%2?0x007fff80:0xff80007f)>>>0;q[j]=0;}
 if(model===3)for(let j=1;j<=5;j++){p[j]=(j%2?0x7fffff80:0x80000080)>>>0;q[j]=0x80000000;}
 check(p,q,low);addressCases++;
}
assert.equal(cases,46592);assert.equal(addressCases,1024);assert.ok(positiveClips&&negativeClips);
assert.equal(asmCalls,backend==='asm'?cases:0);assert.equal(retChecks,cases*(backend==='asm'?3:2));
assert.equal(peakSavedStack,backend==='asm'?14:0);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',backend,
 binarySha256:createHash('sha256').update(binary).digest('hex'),cases,calls:2*cases,outputsPerPath:10*cases,
 directedCases:43520,addressCases,all256RoundingLowBytes:true,all256PointerLowBytes:true,oddAndPageCrossingPointers:true,
 selectedAndForcedCExact:true,sequentialUnsigned32Oracle:true,positiveClips,negativeClips,
 guardsAndInputsPreserved:true,exactAsmReadAndWriteAddresses:backend==='asm',asmCalls,asmReadBytes,asmWrittenBytes,
 savedStackBytes:peakSavedStack,calleeSavedRegistersAtRet:true,zeroRegisterAtRet:true,retChecks,
 primitiveCycles:backend==='asm'?{min:minCycles,max:maxCycles,mean:totalCycles/asmCalls,includesRet:true,includesCallerCall:false}:null,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
