// Exact finite composition, portable C control, actual LPM and GNU ABI.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/))
 .filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [code,result,command,status,end]=['nb1_gain_code','nb1_gain_result','nb1_gain_command','nb1_gain_status','__bss_end'].map(at);
const tableNames=[...symbols.keys()].filter(n=>n==='speex_nb1_gain_table'||n.startsWith('speex_nb1_gain_table.'));assert.equal(tableNames.length,1);
const table=at(tableNames[0]);assert.ok(table+16<32768);
const names=['nb1_gain_original','nb1_gain_coefficient','nb1_gain_factored','nb1_gain_lookup','nb1_gain_bounded_lookup'];
const entries=new Map(names.map((n,i)=>[at(n),i]));assert.equal(entries.size,5);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];let active=null,returns=0,minSP=2303;
const stats=names.map(name=>({name,calls:0,muls:0,lpm:0,minCycles:Infinity,maxCycles:0}));
function until(done){const limit=cpu.cycles+2000;while(!done()){
 assert.ok(cpu.cycles<limit);const opcode=cpu.progMem[cpu.pc],entry=entries.get(cpu.pc*2);
 if(entry!==undefined){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});active={entry,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0,flash:[]};
 }
 if(active){
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++active.muls;
  if((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)active.flash.push(cpu.dataView.getUint16(30,true));
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end);
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.entry],cycles=cpu.cycles-a.start;
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns);assert.equal(cpu.data[1],0);
  assert.deepEqual(a.flash,a.entry>=3?[table+cpu.data[code]]:[]);
  if(a.entry>=3)assert.equal(a.muls,0);
  ++s.calls;s.muls+=a.muls;s.lpm+=a.flash.length;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);const gains=[],coefficients=[];
for(let encoded=0;encoded<16;encoded++){
 const c=Number((2185n*BigInt(encoded<<6)+16384n)>>15n);
 const rounded=Number((24576n*BigInt(c-13)+8192n)>>14n),expected=Math.max(0,Math.min(64,rounded));
 coefficients.push(c);gains.push(expected);assert.equal(binary[table+encoded],expected);
 for(let kind=1;kind<=5;kind++){
  cpu.data[code]=encoded;cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.equal(cpu.data[result],expected);assert.equal(cpu.data[code],encoded);
 }
}
assert.equal(coefficients[15],64);
const report={scope:'Isolated scalar C arithmetic; no C decoder execution/timing',backend:meta.backend,binarySha256:meta.binarySha256,
 all16Codes:true,originalNarrowAndFactoredAndTableExact:true,code15Coefficient64:true,coefficients,gains,
 tableInFlash:true,exactFlashAddresses:true,lookupHasNoMuls:true,calleeSavedAndR1Returns:returns,statistics:stats,
 peakStack:2303-minSP,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
