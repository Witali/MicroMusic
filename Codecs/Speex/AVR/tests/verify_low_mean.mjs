// Independent exact arithmetic, four-MUL operation count and GNU ABI checks.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin'));
const meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=name=>{assert.ok(symbols.has(name),name);return symbols.get(name);};
const [old,value,result,command,status,entry,end]=['mean_old','mean_value','mean_result','mean_command','mean_status','speex_low_mean_avr','__bss_end'].map(at);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,returns=0,overflowPositive=0,overflowNegative=0,minCycles=Infinity,maxCycles=0;
function until(predicate){const deadline=cpu.cycles+2000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'Mean timeout');const opcode=cpu.progMem[cpu.pc];
 if(cpu.pc*2===entry){
  assert.equal(active,null);const original=saved.map(reg=>cpu.data[reg]);
  const patterns=saved.map(reg=>(returns*73+reg*19)&255);saved.forEach((reg,i)=>{cpu.data[reg]=patterns[i];});
  active={sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end,'Stack collision');
 if(opcode===0x9508&&active&&cpu.SP===active.sp+2){
  assert.deepEqual(saved.map(reg=>cpu.data[reg]),active.patterns,'Callee-saved ABI');assert.equal(cpu.data[1],0,'r1');
  assert.equal(active.muls,4,'One full signed16 product');
  const cycles=cpu.cycles-active.start;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
  saved.forEach((reg,i)=>{cpu.data[reg]=active.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function check(a,b){
 const expected=Number((26214n*BigInt(a)+6554n*BigInt(b)+16384n)>>15n);
 for(const kind of [1,2]){
  cpu.dataView.setInt16(old,a,true);cpu.dataView.setInt16(value,b,true);
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(result,true),expected,`${a},${b},backend ${kind}`);
  assert.equal(cpu.dataView.getInt16(old,true),a);assert.equal(cpu.dataView.getInt16(value,true),b);
  assert.equal(cpu.data[1],0);
 }
 if(b-a>32767)++overflowPositive;if(b-a< -32768)++overflowNegative;++cases;
}
const edges=[-32768,-32767,-16384,-1,0,1,16383,32766,32767];
for(const a of edges){for(let b=-32768;b<=32767;b++)check(a,b);console.log('All values with old',a);}
for(const b of edges){for(let a=-32768;a<=32767;a++)if(!edges.includes(a))check(a,b);console.log('All old values with value',b);}
let seed=0x3c812fda;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let i=0;i<32768;i++)check((random()>>>16)-32768,(random()>>>16)-32768);
assert.equal(returns,cases);assert.ok(overflowPositive>0&&overflowNegative>0);
const report={scope:'Scalar C/ASM only; C decoder not executed or timed',binarySha256:meta.binarySha256,
 cases,cAndAsmExact:true,calleeSavedAndR1Returns:returns,arbitraryRegisterPatterns:true,
 completeWordSweepsPerOperand:edges.length,randomPairs:32768,overflowPositive,overflowNegative,
 hardwareMultipliesPerCall:4,asmFunctionMinCycles:minCycles,asmFunctionMaxCycles:maxCycles,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
