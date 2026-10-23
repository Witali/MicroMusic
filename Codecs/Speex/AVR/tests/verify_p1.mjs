import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {CPU,avrInstruction} from 'avr8js';
const here=new URL('../build/math/',import.meta.url);
const symbols=new Map(readFileSync(new URL('symbols.txt',here),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const program=new Uint16Array(16384).fill(65535);
new Uint8Array(program.buffer).set(readFileSync(new URL('math.bin',here)));
const cpu=new CPU(program,2048),addr=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const status=addr('math_status'),command=addr('math_command'),a=addr('math_a'),b=addr('math_value');
const result=addr('math_result'),zero=addr('math_zero');
let kernelEntry=-1,inKernel=false,kernelCycles=0;
function until(predicate){const end=cpu.cycles+10000;while(!predicate()){
 assert.ok(cpu.cycles<end,'timeout');
 if(cpu.pc*2===kernelEntry)inKernel=true;
 const opcode=cpu.progMem[cpu.pc],before=cpu.cycles;
 avrInstruction(cpu);cpu.tick();
 if(inKernel){kernelCycles+=cpu.cycles-before;if(opcode===0x9508)inKernel=false;}
}}
until(()=>cpu.data[status]===1);
let cases=0,beforeSum=0,afterSum=0,beforeKernel=0,afterKernel=0,minGain=Infinity,maxGain=-Infinity;
function check(lhs,rhs){
 assert.ok(rhs>=-536870912&&rhs<536870912&&rhs%64===0);
 cpu.dataView.setInt16(a,lhs,true);cpu.dataView.setInt32(b,rhs,true);
 const expected=Math.floor(lhs*rhs/16384)|0,cycles=[];
 for(const cmd of [101,103]){
  kernelEntry=addr(cmd===101?'speex_avr_lsp_mul_q14':'speex_avr_p1_mul_q14');
  inKernel=false;kernelCycles=0;
  cpu.data[status]=1;cpu.data[command]=cmd;const before=cpu.cycles;
  until(()=>cpu.data[status]===2);cycles.push(cpu.cycles-before);
  assert.equal(cpu.dataView.getInt32(result,true),expected,`${cmd}: ${lhs}, ${rhs}`);
  assert.equal(cpu.data[zero],0,'r1');
  assert.ok(!inKernel&&kernelCycles>0);
  if(cmd===101)beforeKernel+=kernelCycles;else afterKernel+=kernelCycles;
 }
 beforeSum+=cycles[0];afterSum+=cycles[1];
 minGain=Math.min(minGain,cycles[0]-cycles[1]);maxGain=Math.max(maxGain,cycles[0]-cycles[1]);cases++;
}
for(const rhs of [0,64,-64,536870848,-536870912,8388608,-8388608,7901184])
 for(let lhs=-32768;lhs<=32767;lhs++)check(lhs,rhs);
let seed=0x15708a95;
for(let i=0;i<131072;i++){
 seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;const lhs=seed<<16>>16;
 seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;check(lhs,(seed<<2)>>2&~63);
}
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',simulator:'avr8js 0.21.1',cases,exact:true,r1:true,bound:'signed30 b divisible by 64',
 beforeMeanMailboxCycles:beforeSum/cases,afterMeanMailboxCycles:afterSum/cases,
 minMailboxGain:minGain,maxMailboxGain:maxGain,
 beforeMeanKernelCycles:beforeKernel/cases,afterMeanKernelCycles:afterKernel/cases,
 kernelScope:'Entry through RET, excluding CALL/mailbox/dispatch',includesInterrupts:false,physicalBoardTested:false};
writeFileSync(new URL('verification-p1.json',here),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
