// Exhaustive caller-domain arithmetic/ABI checks; no C decoder execution.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]);
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');assert.equal(hash(binary),meta.binarySha256);
const source=readFileSync(join(root,'src/speex_wb1.c'),'utf8');
const energies=source.match(/exp_gain\[32\][^{]*\{([^}]+)\}/)[1].split(',').map(Number);
assert.equal(energies.length,32);assert.ok(energies.every(n=>Number.isInteger(n)&&n>0&&n<=904448));
assert.ok(Math.max(...energies)+16383<2**20);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=name=>{assert.ok(symbols.has(name),name);return symbols.get(name);};
const [energy,ratio,result,command,status,entry,end]=['gain_energy','gain_ratio','gain_result','gain_command','gain_status','speex_wb_gain_div_avr','__bss_end'].map(at);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,returns=0,minCycles=Infinity,maxCycles=0,cases=0,edges=0;
function until(predicate){const deadline=cpu.cycles+10000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'Divider timeout');const opcode=cpu.progMem[cpu.pc];
 if(cpu.pc*2===entry){
  assert.equal(active,null);const original=saved.map(reg=>cpu.data[reg]);
  const values=saved.map(reg=>(returns*73+reg*19)&255);saved.forEach((reg,i)=>{cpu.data[reg]=values[i];});
  active={sp:cpu.SP,start:cpu.cycles,original,values};
 }
 avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end,'Stack collision');
 if(opcode===0x9508&&active&&cpu.SP===active.sp+2){
  assert.deepEqual(saved.map(reg=>cpu.data[reg]),active.values,'Callee-saved ABI');assert.equal(cpu.data[1],0,'r1');
  const cycles=cpu.cycles-active.start;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
  saved.forEach((reg,i)=>{cpu.data[reg]=active.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function check(n,d){
 const expected=Number((BigInt(n)+BigInt(d>>1))/BigInt(d));
 for(const kind of [1,2]){
  cpu.dataView.setInt32(energy,n,true);cpu.dataView.setInt16(ratio,d,true);
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt32(result,true),expected,'Gain '+n+' / '+d+' backend '+kind);
  assert.equal(cpu.dataView.getInt32(energy,true),n);assert.equal(cpu.dataView.getInt16(ratio,true),d);
  assert.equal(cpu.data[1],0);
 }
 ++cases;
}
for(let d=1;d<=32767;d++){
 for(const n of energies)check(n,d);
 if((d&4095)===0)console.log('Checked divisors through',d);
}
const divisors=new Set([1,2,3,7,15,16,17,31,127,255,256,257,32766,32767]);
for(let bit=1;bit<15;bit++)for(const delta of [-1,0,1])divisors.add((1<<bit)+delta);
for(const d of divisors)for(const n of [0,1,2,32767,32768,65535,65536,65537,524287,524288,904447,904448]){check(n,d);++edges;}
assert.equal(returns,cases);
const report={binarySha256:meta.binarySha256,scope:'Isolated C/ASM gain primitive; C decoder not executed or timed',
 tableValues:32,allPositiveDivisors:32767,tableDivisorPairs:32*32767,additionalBoundaryCases:edges,cases,
 cAndAsmExact:true,calleeSavedAndR1Returns:returns,arbitraryRegisterPatterns:true,
 energyMax:Math.max(...energies),roundedNumeratorMax:Math.max(...energies)+16383,remainderBits:16,
 quotientLowSteps:16,asmFunctionMinCycles:minCycles,asmFunctionMaxCycles:maxCycles,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS gain divider',JSON.stringify(report));
