// Complete signed16 unity quantizer, bounded specialization and real GNU ABI.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/))
 .filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [input,result,command,status,end]=['unity_input','unity_result','unity_command','unity_status','__bss_end'].map(at);
const names=['unity_original','unity_generic','unity_noise'],entries=new Map(names.map((n,i)=>[at(n),i]));assert.equal(entries.size,3);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29],stats=names.map(name=>({name,calls:0,muls:0,minCycles:Infinity,maxCycles:0}));
let active=null,returns=0,minSP=2303;
function until(done){const limit=cpu.cycles+2000;while(!done()){
 assert.ok(cpu.cycles<limit);const opcode=cpu.progMem[cpu.pc],entry=entries.get(cpu.pc*2);
 if(entry!==undefined){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});active={entry,start:cpu.cycles,sp:cpu.SP,original,patterns,muls:0};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end);
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.entry],cycles=cpu.cycles-a.start;
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns);assert.equal(cpu.data[1],0);if(a.entry)assert.equal(a.muls,0);
  ++s.calls;s.muls+=a.muls;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
for(let n=-32768;n<=32767;n++){
 const expected=Number((32767n*BigInt(n))>>15n);
 for(const kind of n===-32768?[1,2]:[1,2,3]){
  cpu.dataView.setInt16(input,n,true);cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(result,true),expected);assert.equal(cpu.dataView.getInt16(input,true),n);
 }
}
const report={scope:'Isolated C scalar primitives; no C decoder execution/timing',backend:meta.backend,binarySha256:meta.binarySha256,
 fullSigned16Inputs:65536,boundedInputsExcludingMin:65535,negativeEndpointAndFloorsExact:true,originalAndIndependentExact:true,
 calleeSavedAndR1Returns:returns,noMulsInSimplifications:true,statistics:stats,peakStack:2303-minSP,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
