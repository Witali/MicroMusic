// Signed64-equivalent BigInt equations, exhaustive sum/flag partitions and ABI.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),bi=process.argv.indexOf('--backend');
const backend=bi<0?'asm':process.argv[bi+1];assert.ok(['asm','c'].includes(backend));
const fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/first-unit-'+backend):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'first.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('first_work'),pointer=address('first_addresses'),aAddress=address('first_a'),bAddress=address('first_b');
const status=address('first_status'),command=address('first_command');
const names=['first_selected','first_forced_c'];for(const n of names)assert.ok(symbols.has(n));
assert.equal(symbols.has('speex_avr_lsp_first'),backend==='asm');
const entries=new Map([...symbols].filter(([n])=>names.includes(n)||n==='speex_avr_lsp_first').map(([n,a])=>[a,n]));
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29],active=[];
let trace=null,watch=false,workWatch=false,workReads=[],workWrites=[],retChecks=0,asmCalls=0,asmReadBytes=0,asmWrittenBytes=0,peakSavedStack=0;
let sregAddress,flagChecks=0;
const cycles={negative:new Set(),zero:new Set(),positive:new Set()},highCarry=new Uint8Array(131072),sums=new Uint8Array(131071);
const read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)trace.reads.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+384)workReads.push(a[0]);return read.apply(this,a);};
cpu.writeData=function(...a){if(watch)trace.writes.push(a[0]);if(workWatch&&a[0]>=work&&a[0]<work+384)workWrites.push(a[0]);return write.apply(this,a);};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'constructor mailbox timeout');const name=entries.get(cpu.pc*2);
 if(name){active.push({name,sp:cpu.SP,regs:regs.map(r=>cpu.data[r])});
  if(name==='speex_avr_lsp_first'){
   assert.equal(trace,null);assert.equal(cpu.data[1],0);
   trace={p:cpu.dataView.getUint16(24,true),a:cpu.dataView.getInt16(22,true),b:cpu.dataView.getInt16(20,true),
    sp:cpu.SP,reads:[],writes:[],pushes:0,pops:0,start:cpu.cycles};
  }
 }
 const op=cpu.progMem[cpu.pc],ret=op===0x9508;
 if(trace){
  if((op&0xfe0f)===0x920f)trace.pushes++;
  if((op&0xfe0f)===0x900f)trace.pops++;
  if((op&0xfc07)===0xf404){
   const sum=trace.a+trace.b;
   assert.equal((cpu.data[sregAddress]>>4)&1,Number(sum<0),'ADC S is the true signed17 sum sign');
   const carry=Number((trace.a&255)+(trace.b&255)>255);
   highCarry[((trace.a>>>8)&255)*512+((trace.b>>>8)&255)*2+carry]=1;
   sums[sum+65536]=1;flagChecks++;
  }
 }
 watch=trace!==null&&!ret;avrInstruction(cpu);cpu.tick();watch=false;
 if(trace&&!ret)peakSavedStack=Math.max(peakSavedStack,trace.sp-cpu.SP);
 if(ret)while(active.length&&cpu.SP===active.at(-1).sp+2){
  const frame=active.pop();assert.deepEqual(regs.map(r=>cpu.data[r]),frame.regs);assert.equal(cpu.data[1],0);retChecks++;
  if(frame.name==='speex_avr_lsp_first'){
   assert.deepEqual(trace.reads,[],'Constructor must not read SRAM');
   assert.deepEqual(trace.writes,Array.from({length:8},(_,i)=>trace.p+4+i),'Only p1 and p2 are written');
   assert.equal(trace.pushes,0);assert.equal(trace.pops,0);assert.equal(cpu.SP,trace.sp+2);
   cycles[trace.a+trace.b<0?'negative':trace.a+trace.b>0?'positive':'zero'].add(cpu.cycles-trace.start);
   asmReadBytes+=trace.reads.length;asmWrittenBytes+=trace.writes.length;asmCalls++;trace=null;
  }
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
sregAddress=cpu.dataView.getUint16(pointer+2,true);
assert.ok(sregAddress>=32&&sregAddress<256,'SREG address supplied by official avr/io.h');
let seed=0x713a6c91,cases=0,addressCases=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function check(a,b,low=cases&255){
 const pp=work+low,salt=random(),first=Number(-BigInt(a+b)*64n),second=Number(2097152n+((BigInt(a)*BigInt(b)+255n)>>8n));
 for(const mode of [1,2]){
  cpu.data.fill(0x69,work,work+384);cpu.dataView.setUint32(pp,salt,true);
  const expected=cpu.data.slice(work,work+384),view=new DataView(expected.buffer);
  view.setInt32(pp-work+4,first,true);view.setInt32(pp-work+8,second,true);
  cpu.dataView.setUint16(pointer,pp,true);cpu.dataView.setInt16(aAddress,a,true);cpu.dataView.setInt16(bAddress,b,true);
  workReads=[];workWrites=[];workWatch=true;cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);workWatch=false;
  assert.equal(active.length,0);assert.equal(trace,null);
  assert.deepEqual(cpu.data.slice(work,work+384),expected,'Guards and arbitrary p0 remain unchanged');
  assert.deepEqual(workReads,[]);assert.equal(workWrites.length,8);
  assert.deepEqual([...workWrites].sort((a,b)=>a-b),Array.from({length:8},(_,i)=>pp+4+i));
 }
 cases++;
}
const fixed=[-32768,-32767,-32512,-256,-255,-129,-128,-1,0,1,127,128,255,256,32766,32767];
for(const b of fixed)for(let a=-32768;a<=32767;a++)check(a,b);
for(let ah=0;ah<256;ah++)for(let bh=0;bh<256;bh++)for(let carry=0;carry<2;carry++)
 check(((ah<<8)|(carry?255:0))<<16>>16,((bh<<8)|(carry?1:0))<<16>>16);
for(let sum=-65536;sum<=65534;sum++){
 const a=Math.max(-32768,Math.min(32767,sum));check(a,sum-a);
}
for(let i=0;i<65536;i++)check(random()<<16>>16,random()<<16>>16);
for(let low=0;low<256;low++)for(const b of fixed){check(random()<<16>>16,b,low);addressCases++;}
assert.equal(cases,1380351);assert.equal(addressCases,4096);
assert.equal(asmCalls,backend==='asm'?cases:0);assert.equal(retChecks,cases*(backend==='asm'?3:2));
assert.equal(peakSavedStack,0);
if(backend==='asm'){
 assert.equal(flagChecks,cases);assert.equal(highCarry.reduce((s,x)=>s+x,0),131072);assert.equal(sums.reduce((s,x)=>s+x,0),131071);
 for(const values of Object.values(cycles))assert.deepEqual([...values],[66]);
 assert.equal(asmWrittenBytes,11042808);
}
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',backend,
 binarySha256:createHash('sha256').update(binary).digest('hex'),deviceHeaders:JSON.parse(readFileSync(join(dir,'device-headers.json'),'utf8')),
 cases,calls:2*cases,outputWordsPerPath:2*cases,allSigned16LeftRootsAt16RightRoots:true,allSigned17Sums:true,
 all131072HighByteCarryInputs:true,addressCases,all256PointerLowBytes:true,oddAndPageCrossingPointers:true,
 selectedAndForcedCExact:true,independentBigIntProductOracle:true,guardsAndP0Preserved:true,
 exactAsmReadAndWriteAddresses:backend==='asm',asmCalls,asmReadBytes,asmWrittenBytes,savedStackBytes:peakSavedStack,
 flagChecks,highByteCarryInputsChecked:backend==='asm'?131072:0,signed17SumsChecked:backend==='asm'?131071:0,
 calleeSavedRegistersAtRet:true,zeroRegisterAtRet:true,retChecks,
 primitiveCyclesIncludingRet:backend==='asm'?Object.fromEntries(Object.entries(cycles).map(([n,v])=>[n,[...v]])):null,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
