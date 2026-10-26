// Independent BigInt quantization/folding, complete codebook/address coverage.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/high-fold-unit'):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'unit.bin')),program=new Uint16Array(16384).fill(65535);
new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('high_unit_buffer'),pointer=address('high_unit_address'),indices=address('high_unit_indices');
const scaleAddress=address('high_unit_scale'),gainAddress=address('high_unit_gain'),command=address('high_unit_command'),status=address('high_unit_status');
const entry=address('speex_wb_excitation8_40_avr'),table=address('exc_8_128_table');
const text=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/exc_8_128_table.c'),'utf8');
const values=text.slice(text.indexOf('{',text.indexOf('exc_8_128_table[1024]'))+1,text.lastIndexOf('}')).split(',').map(s=>s.trim()).filter(Boolean).map(Number);
assert.equal(values.length,1024);assert.deepEqual([...binary.subarray(table,table+1024)],values.map(v=>v&255));
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];let trace=null,watch=false,calls=0,asmCalls=0,readBytes=0,writtenBytes=0,flashBytes=0,peakSaved=0;
const cycles=new Set(),read=cpu.readData,write=cpu.writeData;
cpu.readData=function(...a){if(watch)trace.reads.push(a[0]);return read.apply(this,a);};
cpu.writeData=function(...a){if(watch)trace.writes.push(a[0]);return write.apply(this,a);};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'mailbox timeout');
 if(cpu.pc*2===entry){assert.equal(trace,null);assert.equal(cpu.data[1],0);trace={sp:cpu.SP,p:cpu.dataView.getUint16(24,true),i:cpu.dataView.getUint16(22,true),saved:regs.map(r=>cpu.data[r]),start:cpu.cycles,reads:[],writes:[],flash:[],pushes:0,pops:0};}
 const op=cpu.progMem[cpu.pc],ret=op===0x9508;
 if(trace){
  if((op&0xfe0f)===0x920f)trace.pushes++;if((op&0xfe0f)===0x900f)trace.pops++;
  if((op&0xfe0f)===0x9005)trace.flash.push(cpu.dataView.getUint16(30,true));
 }
 watch=trace!==null&&!ret;avrInstruction(cpu);cpu.tick();watch=false;
 if(trace&&!ret)peakSaved=Math.max(peakSaved,trace.sp-cpu.SP);
 if(ret&&trace&&cpu.SP===trace.sp+2){
  assert.deepEqual(regs.map(r=>cpu.data[r]),trace.saved);assert.equal(cpu.data[1],0);
  assert.deepEqual(trace.reads,Array.from({length:5},(_,i)=>trace.i+i));
  assert.deepEqual(trace.writes,Array.from({length:80},(_,i)=>trace.p+i));
  const expected=[];for(let v=0;v<5;v++)for(let j=0;j<8;j++)expected.push(table+8*cpu.data[trace.i+v]+j);
  assert.deepEqual(trace.flash,expected);assert.equal(trace.pushes,16);assert.equal(trace.pops,16);
  cycles.add(cpu.cycles-trace.start);readBytes+=5;writtenBytes+=80;flashBytes+=40;asmCalls++;trace=null;
 }
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
function oracle(codes,scale,g){const out=[];for(let i=0;i<40;i++){
 const shape=values[8*codes[Math.floor(i/8)]+i%8];
 const innovation=(BigInt(shape)*BigInt(scale)+262144n)>>19n;
 const t=(29491n*innovation)>>15n;
 let v=(t*BigInt(g)+256n)>>9n;if(i&1)v=-v;
 out.push(Number(BigInt.asIntN(16,v)));
}return out;}
let cases=0,addressCases=0,seed=0x63d91abc;const seen=Array.from({length:5},()=>new Set());
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function check(codes,scale,g,low=cases&255){
 const pp=work+low,answer=oracle(codes,scale,g);
 for(const mode of [1,2]){
  cpu.data.fill(0x69,work,work+384);const expected=cpu.data.slice(work,work+384),view=new DataView(expected.buffer);
  for(let i=0;i<40;i++)view.setInt16(pp-work+2*i,answer[i],true);
  cpu.data.set(codes,indices);cpu.dataView.setUint16(pointer,pp,true);cpu.dataView.setInt32(scaleAddress,scale,true);cpu.dataView.setInt32(gainAddress,g,true);
  cpu.data[status]=1;cpu.data[command]=mode;until(()=>cpu.data[status]===2);
  assert.equal(trace,null);assert.deepEqual(cpu.data.slice(work,work+384),expected,'All forty samples, guards and untouched bytes');
  assert.deepEqual([...cpu.data.slice(indices,indices+5)],codes,'Read-only five indices');calls++;
 }
 for(let v=0;v<5;v++)seen[v].add(codes[v]);cases++;
}
const scales=[0,1,7,8,15,16,4095,4096,4097,1048575,1048576,120988612,121000000],gains=[-2147483648,-65537,-1,0,1,65536,2147483647];
for(let code=0;code<128;code++)for(let pos=0;pos<5;pos++)for(const s of scales)for(const g of gains){
 const codes=Array.from({length:5},(_,j)=>(code*13+pos*7+j*29)&127);codes[pos]=code;check(codes,s,g);
}
for(let i=0;i<4096;i++)check(Array.from({length:5},()=>random()&127),random()%121000001,random()|0);
for(let low=0;low<256;low++)for(const g of [-2147483648,0,1,2147483647]){check([127,0,126,1,125],121000000,g,low);addressCases++;}
assert.equal(cases,63360);assert.equal(calls,126720);assert.equal(asmCalls,cases);assert.equal(addressCases,1024);assert.equal(peakSaved,16);assert.ok(cycles.size>0);
for(const s of seen)assert.equal(s.size,128);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',binarySha256:createHash('sha256').update(binary).digest('hex'),
 cases,calls,outputSamplesPerPath:cases*40,all128IndicesAtEveryVector:true,signed32GainExtrema:true,scaleBound:121000000,addressCases,
 all256PointerLowBytes:true,oddAndPageCrossingPointers:true,selectedAndForcedCExact:true,independentBigIntOracle:true,
 guardsAndReadOnlyIndicesPreserved:true,calleeSavedRegistersAndR1AtRet:true,exactRamAndFlashAddresses:true,
 asmCalls,readBytes,writtenBytes,flashBytes,savedStackBytes:peakSaved,primitiveCyclesIncludingRet:[...cycles].sort((a,b)=>a-b),includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
