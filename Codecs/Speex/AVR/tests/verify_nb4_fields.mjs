// Bit-at-a-time oracle independent of the reader's seven-byte expressions.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),fi=process.argv.indexOf('--firmware');
const dir=fi<0?join(root,'build/nb4-fields-unit'):resolve(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const binary=readFileSync(join(dir,'unit.bin')),program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const work=address('nb4_field_buffer'),pointer=address('nb4_field_address'),indices=address('nb4_field_indices'),header=address('nb4_field_header');
const subAddress=address('nb4_field_sub'),status=address('nb4_field_status'),command=address('nb4_field_command'),entry=address('speex_nb4_unpack_subframe');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];let trace=null,watch=false,retChecks=0,readBytes=0;
const read=cpu.readData;
cpu.readData=function(...a){if(watch&&a[0]>=work&&a[0]<work+384)trace.reads.push(a[0]);return read.apply(this,a);};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'reader timeout');if(cpu.pc*2===entry){assert.equal(trace,null);trace={sp:cpu.SP,regs:regs.map(r=>cpu.data[r]),reads:[]};}
 const ret=cpu.progMem[cpu.pc]===0x9508;watch=trace!==null&&!ret;avrInstruction(cpu);cpu.tick();watch=false;
 if(ret&&trace&&cpu.SP===trace.sp+2){assert.deepEqual(regs.map(r=>cpu.data[r]),trace.regs);assert.equal(cpu.data[1],0);
  const pp=cpu.dataView.getUint16(pointer,true)+3+6*cpu.data[subAddress];
  assert.deepEqual([...trace.reads].sort((a,b)=>a-b),Array.from({length:7},(_,i)=>pp+i));readBytes+=7;retChecks++;trace=null;}
 assert.ok(cpu.SP>=address('__bss_end'),'Static/stack collision');
}}
until(()=>cpu.data[status]===1);
let seed=0x8216db79,cases=0,addressCases=0,paddingCases=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function input(){return Array.from({length:28},()=>random()&255);}
function get(p,bit,n){let v=0;for(let i=0;i<n;i++)v=(v<<1)|((p[(bit+i)>>3]>>(7-((bit+i)&7)))&1);return v;}
function put(p,bit,n,value){for(let i=0;i<n;i++){const b=bit+i,m=1<<(7-(b&7));p[b>>3]=(p[b>>3]&~m)|(((value>>(n-1-i))&1)?m:0);}}
function check(p,sub,low=cases&255){
 const pp=work+low;cpu.data.fill(0x69,work,work+384);cpu.data.set(p,pp);const expected=cpu.data.slice(work,work+384);
 cpu.data.fill(0x57,indices,indices+8);cpu.dataView.setUint16(pointer,pp,true);cpu.data[subAddress]=sub;
 cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);assert.equal(trace,null);
 assert.equal(cpu.dataView.getUint16(header,true),get(p,28+48*sub,13));
 for(let j=0;j<5;j++)assert.equal(cpu.data[indices+j],get(p,41+48*sub+7*j,7));
 assert.deepEqual([...cpu.data.slice(indices+5,indices+8)],[0x57,0x57,0x57]);assert.deepEqual(cpu.data.slice(work,work+384),expected);cases++;
}
for(let sub=0;sub<4;sub++){
 for(let h=0;h<8192;h++){const p=input();put(p,28+48*sub,13,h);check(p,sub);}
 for(let adjacent=0;adjacent<4;adjacent++)for(let pair=0;pair<16384;pair++){
  const p=input();put(p,41+48*sub+7*adjacent,14,pair);check(p,sub);
 }
}
for(let i=0;i<8192;i++)check(input(),i&3);
for(let low=0;low<256;low++)for(let sub=0;sub<4;sub++){check(input(),sub,low);addressCases++;}
for(let pad=0;pad<16;pad++)for(let sub=0;sub<4;sub++){const p=input();p[27]=(p[27]&240)|pad;check(p,sub);paddingCases++;}
assert.equal(cases,304192);assert.equal(addressCases,1024);assert.equal(paddingCases,64);assert.equal(retChecks,cases);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0',simulator:'avr8js 0.21.1',binarySha256:createHash('sha256').update(binary).digest('hex'),
 cases,fields:cases*6,all8192HeadersAtEachSubframe:true,all16384AdjacentIndexPairsAtEveryBoundaryAndSubframe:true,
 addressCases,paddingCases,all256PointerLowBytes:true,exactSevenInputBytesOnce:true,readBytes,
 inputAndGuardsPreserved:true,indexTailPreserved:true,calleeSavedRegistersAndR1AtRet:true,retChecks,
 independentBitByBitOracle:true,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
