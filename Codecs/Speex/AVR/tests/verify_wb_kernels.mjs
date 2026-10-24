// Independent equations, full-scale inputs, state transitions, alias and ABI.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=fileURLToPath(new URL('../build/wb-kernels/',import.meta.url));
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function addr(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const [buffer,den,gain,command,kind,status,alias]=['wb_unit_buffer','wb_unit_den','wb_unit_gain','wb_unit_command','wb_unit_kind','wb_unit_status','wb_unit_alias'].map(addr);
const binary=readFileSync(join(dir,'wb.bin')),rows=[];
const textAddresses=readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+[tT]\s+/)).filter(Boolean).map(m=>parseInt(m[1],16));
const h=[-4,-10,7,15,-14,-26,37,123,123,37,-26,-14,15,7,-10,-4];
const clip=x=>Math.max(-32767,Math.min(32767,x)),s16=x=>(x<<16)>>16;
const callee=[...Array.from({length:16},(_,i)=>i+2),28,29];
for(let test=0;test<6;test++) {
 const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
 const cpu=new CPU(program,2048),family=Math.floor(test/2),isAsm=!(test&1);
 const fn=['speex_wb_qmf40_avr','speex_wb_qmf40_c','speex_wb_fold40_avr','speex_wb_fold40_c','speex_wb_iir40_avr','speex_wb_iir40_c'][test];
 const start=isAsm?addr(fn):0;
 const finish=isAsm?Math.min(...textAddresses.filter(v=>v>start)):0;
 let saved=null,returns=0,minSP=2303,seed=12345678;
 const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return (seed>>>16)-32768;};
 function until(predicate){const deadline=cpu.cycles+1000000;while(!predicate()) {
   assert.ok(cpu.cycles<deadline,'timeout');
   if(isAsm&&cpu.pc*2===start)saved=callee.map(r=>cpu.data[r]);
   if(isAsm&&cpu.pc*2>=start&&cpu.pc*2<finish&&program[cpu.pc]===0x9508){
     assert.deepEqual(callee.map(r=>cpu.data[r]),saved,'callee-saved '+fn);assert.equal(cpu.data[1],0,'r1 '+fn);returns++;
   }
   avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);
 }}
 until(()=>cpu.data[status]===1);cpu.data[command]=2;cpu.data[status]=0;until(()=>cpu.data[status]===1);cpu.data[kind]=test;
 const lowMem=Array(8).fill(0),highMem=Array(8).fill(0),iirMem=Array(8).fill(0);
 const blocks=family===1?1640:512,cycles=[];
 for(let f=0;f<blocks;f++) {
   const input=Array.from({length:80},(_,i)=>family===1?s16(f*40+i-32768):f===0?0:f===1?32767:f===2?-32768:f===3?(i<40?32767:-32768):f===4?(i&1?-32768:32767):random());
   const coeff=Array.from({length:8},()=>random());
   const gains=[0,1,255,256,511,512,513,32767,32768,65535,65536,904448,0x7fffffff,-2147483648,-1];
   const g=gains[f%gains.length],expected=[];
   cpu.data[alias]=f&1;
   for(let i=0;i<80;i++)cpu.dataView.setInt16(buffer+4+2*i,input[i],true);
   for(let i=0;i<8;i++)cpu.dataView.setInt16(den+2*i,coeff[i],true);
   cpu.dataView.setInt32(gain,g,true);
   if(family===0)for(let i=0;i<40;i++) {
     lowMem[i&7]=input[i];highMem[i&7]=input[i+40];let e=0,o=0;
     for(let k=0;k<8;k++){const j=(i-k)&7,l=lowMem[j],r=highMem[j];e+=h[2*k]*((l-r)>>1);o+=h[2*k+1]*((l+r)>>1);}
     expected.push(clip((e+32)>>6),clip((o+32)>>6));
   }
   if(family===1)for(let i=0;i<40;i++) {
     // Literal fixed_generic.h P15 -> SHL14 -> PSHR14, rather than the
     // shortened product/shift identity used by the implementation.
     const t=Math.floor(29491*input[i]/32768),b=g<<6;
     const v=(t*s16(b>>15)+Math.floor((t*(b&32767)+16384)/32768))|0;
     const exc=i&1?-(v<<14):v<<14;
     expected.push(s16(((exc+8192)|0)>>14));
   }
   if(family===2)for(let i=0;i<40;i++) {
     const y=clip(input[i]+(((iirMem[0]+4096)|0)>>13));expected.push(y);
     for(let j=0;j<7;j++)iirMem[j]=(iirMem[j+1]-coeff[j]*y)|0;
     iirMem[7]=(-coeff[7]*y)|0;
   }
   cpu.data[status]=1;cpu.data[command]=1;const begin=cpu.cycles;until(()=>cpu.data[status]===3);cycles.push(cpu.cycles-begin);
   const output=family===1?buffer+4:buffer+168;
   assert.deepEqual(expected.map((_,i)=>cpu.dataView.getInt16(output+2*i,true)),expected,fn+' block '+f);
   for(const offset of [0,164,328,396])for(let j=0;j<4;j++)assert.equal(cpu.data[buffer+offset+j],165,'guard '+fn);
   for(let i=family===1?40:0;i<80;i++)assert.equal(cpu.dataView.getInt16(buffer+4+2*i,true),input[i],'read-only input');
 }
 if(isAsm)assert.equal(returns,blocks,'actual top-level RET count');
 rows.push({kernel:fn,blocks,samples:blocks*(family===0?80:40),pcmExact:true,
   minCycles:Math.min(...cycles),maxCycles:Math.max(...cycles),calleeSavedAndR1Returns:isAsm?returns:null,
   guards:true,readOnlyInputs:true,aliasQmf:family===0,peakStackBytes:2303-minSP});
 console.log(JSON.stringify(rows.at(-1)));
}
writeFileSync(join(dir,'verification.json'),JSON.stringify({scope:'AVR machine code; independent mathematical/Xiph equations, both backends',streams:rows},null,2)+'\n');
