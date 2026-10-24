import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';

const [input,output]=process.argv.slice(2),spec=JSON.parse(readFileSync(input,'utf8'));
const bytes=readFileSync(spec.image),results=[];
const engines=[['reference',new Reference(bytes)],['wasm',new Wasm(bytes)],
 ['wasm-unoptimized',new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})]];
function expected(value,coefficient,bits){
 const operand=coefficient<0?(((-value+32768)&65535)-32768):value;
 const product=operand*Math.abs(coefficient),half=1<<(bits-1),scale=1<<bits;
 return (product<0?-Math.floor((-product+half)/scale):Math.floor((product+half)/scale))&65535;
}
for(const [name,cpu] of engines){
 const result={engine:name,checked:0,irqChecked:0,q4:{minimum:Infinity,maximum:0},q5:{minimum:Infinity,maximum:0}};
 function check(value,coefficient,bits,interrupt=false){
  cpu.pc=spec.symbols[bits===4?'mul_word_q4':'mul_word_q5']/2;cpu.sp=0x9f;
  cpu.sreg=interrupt?0xc1:0x41;cpu.io[0x39]=interrupt?2:0;cpu.pending=false;cpu.irqDelay=0;
  cpu.r[1]=0x5a;cpu.r[16]=0xa6;cpu.r[17]=0x79;
  cpu.r[18]=value&255;cpu.r[19]=(value>>8)&255;cpu.r[20]=coefficient&255;
  cpu.r[26]=0x68;cpu.r[27]=0;cpu.r[28]=0x70;cpu.r[29]=0;cpu.r[30]=0x42;cpu.r[31]=1;
  cpu.pushPC(511);const before=cpu.cyc,irqs=cpu.irqCount;let steps=0,injected=false;
  while(cpu.pc!==511&&steps++<200){
   if(interrupt&&!injected&&cpu.pc===spec.symbols.word_mul_round/2){
    cpu.pending=true;cpu.interrupt();injected=true;
   }
   cpu.step();
  }
  assert.equal(cpu.pc,511);const got=cpu.r[24]|(cpu.r[25]<<8);
  if(got!==expected(value,coefficient,bits))throw Error(JSON.stringify({name,value,coefficient,bits,got,expected:expected(value,coefficient,bits)}));
  assert.equal(cpu.r[1],0x5a);assert.equal(cpu.r[16],0xa6);assert.equal(cpu.r[17],0x79);
  assert.equal(cpu.r[20],coefficient&255);assert.equal(cpu.r[26],0x68);assert.equal(cpu.r[27],0);
  assert.equal(cpu.r[28],0x70);assert.equal(cpu.r[29],0);assert.equal(cpu.r[30],0x42);assert.equal(cpu.r[31],1);
  assert.equal(cpu.sp,0x9f);assert.equal(cpu.sreg&0xc0,interrupt?0xc0:0x40);
  if(interrupt){assert.ok(injected);assert.equal(cpu.irqCount-irqs,1);result.irqChecked++;}
  else{
   const clock=result[bits===4?'q4':'q5'],elapsed=cpu.cyc-before;
   clock.minimum=Math.min(clock.minimum,elapsed);clock.maximum=Math.max(clock.maximum,elapsed);result.checked++;
  }
 }
 const values=spec.quick?Array.from({length:256},(_,i)=>-32768+i*257):Array.from({length:65536},(_,i)=>i-32768);
 for(const value of values)for(let k=-15;k<=15;k++)check(value,k,4);
 const edges=new Set([-32768,-32767,-2048,-129,-128,-127,-17,-16,-15,-1,0,1,15,16,17,127,128,2047,32767]);
 for(let value=-32768;value<32768;value+=257)edges.add(value);
 for(const value of edges)for(let k=-31;k<=31;k++)check(value,k,5);
 for(let tap=-7;tap<=7;tap++)for(let gain=0;gain<=30;gain++)check(tap*128,gain,5);
 for(const bits of [4,5])for(const value of [-32768,-1025,-17,-1,1,15,1023,32767])
  for(const coefficient of [-(1<<bits)+1,-1,1,(1<<bits)-1])check(value,coefficient,bits,true);
 results.push(result);
}
for(const result of results.slice(1))for(const key of ['q4','q5'])assert.deepEqual(result[key],results[0][key]);
const report={pass:true,quick:spec.quick,scope:spec.quick?'Q4 sampled':'Q4 exhaustive signed16 x -15..15',
 q5Scope:'All coefficients on boundary/strided word samples plus every physical tap/gain pair',
 checked:results.reduce((n,r)=>n+r.checked,0),irqChecked:results.reduce((n,r)=>n+r.irqChecked,0),
 kernelBytes:spec.kernelBytes,engines:results,
 timingScope:'Entry through RET, excludes caller RCALL; isolated fixture, not full-player deadline',
 fullDecoderImplemented:false,hardwareTested:false};
writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
