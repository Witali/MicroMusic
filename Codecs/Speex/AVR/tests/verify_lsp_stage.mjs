// Wide BigInt products model each original polynomial update independently.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1];assert.ok(['asm','c'].includes(backend));
const fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/poly-stage-unit-'+backend):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'stage.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('stage_work'),pointer=address('stage_address'),fAddress=address('stage_f'),number=address('stage_number');
const status=address('stage_status'),command=address('stage_command');
const names=['stage_selected','stage_forced_c'];for(const n of names)assert.ok(symbols.has(n));
for(const n of [2,3,4])assert.equal(symbols.has('speex_avr_lsp_stage'+n),backend==='asm');
const entries=new Map([...symbols].filter(([n])=>names.includes(n)||/^speex_avr_lsp_stage[234]$/.test(n)).map(([n,a])=>[a,n]));
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let trace=null,watch=false,workWatch=false,workReads=[],workWrites=[],retChecks=0,asmCalls=0,asmReadBytes=0,asmWrittenBytes=0,peakSavedStack=0;
const cycles={2:new Set(),3:new Set(),4:new Set()},read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)trace.reads.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+384)workReads.push(a[0]);return read.apply(this,a);};
cpu.writeData=function(...a){if(watch)trace.writes.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+384)workWrites.push(a[0]);return write.apply(this,a);};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'stage mailbox timeout');const name=entries.get(cpu.pc*2);
 if(name){active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name.startsWith('speex_avr_lsp_stage')){
   assert.equal(trace,null);assert.equal(cpu.data[1],0);
   trace={p:cpu.dataView.getUint16(24,true),n:Number(name.at(-1)),sp:cpu.SP,reads:[],writes:[],pushes:[],pops:[],start:cpu.cycles};
  }
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508;
 if(trace){if((op&0xfe0f)===0x920f)trace.pushes.push(cpu.SP);if((op&0xfe0f)===0x900f)trace.pops.push(cpu.SP+1);}
 watch=trace!==null&&!ret;avrInstruction(cpu);cpu.tick();watch=false;
 if(trace&&!ret)peakSavedStack=Math.max(peakSavedStack,trace.sp-cpu.SP);
 if(ret)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name.startsWith('speex_avr_lsp_stage')){
   const expectedReads=[],expectedWrites=[];
   for(let j=trace.n;j>=1;j--)for(let b=0;b<4;b++)expectedReads.push(trace.p+4*j+b);
   for(let j=trace.n+1;j>=1;j--)for(let b=0;b<4;b++)expectedWrites.push(trace.p+4*j+b);
   assert.deepEqual(trace.reads,expectedReads,'Each needed polynomial byte is read exactly once');
   assert.deepEqual(trace.writes,expectedWrites,'Only p[stage+1..1] may be written');
   assert.deepEqual(trace.pushes,Array.from({length:12},(_,i)=>trace.sp-i));assert.deepEqual(trace.pops,[...trace.pushes].reverse());
   cycles[trace.n].add(cpu.cycles-trace.start);asmReadBytes+=trace.reads.length;asmWrittenBytes+=trace.writes.length;asmCalls++;trace=null;
  }
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
let seed=0x1d87cb39,cases=0,addressCases=0,outputs=0;const perStage={2:0,3:0,4:0};
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function input(){const p=Array.from({length:6},(_,i)=>i?(((random()&0x3fffffff)^0x20000000)-0x20000000):1048576);p[1]&=~63;return p;}
function oracle(p,f,n){
 const out=[...p],q14=b=>(BigInt(f)*BigInt(b))>>14n,word=x=>Number(BigInt.asIntN(32,x));
 out[n+1]=word(2n*BigInt(p[n-1])-q14(p[n]));
 for(let j=n;j>=2;j--)out[j]=word(BigInt(p[j])-q14(p[j-1])+BigInt(p[j-2]));
 out[1]=word(BigInt(p[1])-BigInt(f)*64n);return out;
}
function check(p,f,n,low=cases&255){
 assert.equal(p[0],1048576);assert.equal(p[1]&63,0);
 for(let j=1;j<=n;j++)assert.ok(p[j]>=-536870912&&p[j]<536870912);
 const pp=work+low,answer=oracle(p,f,n),inputBytes=new Set(Array.from({length:4*(n+1)},(_,i)=>pp+i));
 const outputBytes=new Set(Array.from({length:4*(n+1)},(_,i)=>pp+4+i));
 for(const mode of [1,2]){
  cpu.data.fill(0x69,work,work+384);for(let j=0;j<6;j++)cpu.dataView.setInt32(pp+4*j,p[j],true);
  const expected=cpu.data.slice(work,work+384),view=new DataView(expected.buffer);
  for(let j=0;j<6;j++)view.setInt32(pp-work+4*j,answer[j],true);
  cpu.dataView.setUint16(pointer,pp,true);cpu.dataView.setInt16(fAddress,f,true);cpu.data[number]=n;
  workReads=[];workWrites=[];workWatch=true;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);workWatch=false;
  assert.equal(active.length,0);assert.equal(trace,null);
  assert.deepEqual(cpu.data.slice(work,work+384),expected,'Guards, p0 and untouched tail are preserved');
  for(const a of workReads)assert.ok(inputBytes.has(a));for(const a of workWrites)assert.ok(outputBytes.has(a));
  assert.equal(new Set(workWrites).size,4*(n+1));
 }
 cases++;perStage[n]++;outputs+=n+1;
}
for(let n=2;n<=4;n++)for(let f=-32768;f<=32767;f++)check(input(),f,n);
for(let n=2;n<=4;n++)for(let i=0;i<16384;i++)check(input(),(random()<<16)>>16,n);
const bound=[-536870912,-536870911,-73400331,-20971523,-6291457,-1,0,1,6291457,20971523,73400331,536870910,536870911];
const aligned=[-536870912,-8388608,-64,0,64,8388608,536870848],fvalues=[-32768,-32767,-16384,-1,0,1,16383,16384,32766,32767];
for(let n=2;n<=4;n++)for(const f of fvalues)for(const p1 of aligned)for(let bi=0;bi<13;bi++)for(const step of [1,5,12]){
 const p=input();p[1]=p1;for(let j=2;j<6;j++)p[j]=bound[(bi+j*step)%13];check(p,f,n);
}
for(let n=2;n<=4;n++)for(const f of [-32768,0,32767])for(let low=0;low<256;low++){check(input(),f,n,low);addressCases++;}
assert.equal(cases,256254);assert.equal(outputs,1025016);assert.equal(addressCases,2304);
assert.deepEqual(perStage,{2:85418,3:85418,4:85418});assert.equal(asmCalls,backend==='asm'?cases:0);
assert.equal(retChecks,cases*(backend==='asm'?3:2));assert.equal(peakSavedStack,backend==='asm'?12:0);
if(backend==='asm')for(const values of Object.values(cycles))assert.equal(values.size,1);
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',backend,
 binarySha256:createHash('sha256').update(binary).digest('hex'),cases,calls:2*cases,perStage,outputsPerPath:outputs,
 all65536Signed16RootsPerStage:true,signed30CoefficientLimits:true,addressCases,all256PointerLowBytes:true,oddAndPageCrossingPointers:true,
 selectedAndForcedCExact:true,independentBigIntProductOracle:true,guardsAndUntouchedWordsPreserved:true,
 exactAsmReadAndWriteAddresses:backend==='asm',asmCalls,asmReadBytes,asmWrittenBytes,savedStackBytes:peakSavedStack,
 calleeSavedRegistersAtRet:true,zeroRegisterAtRet:true,retChecks,
 primitiveCyclesIncludingRet:backend==='asm'?Object.fromEntries(Object.entries(cycles).map(([n,v])=>[n,[...v]])):null,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
