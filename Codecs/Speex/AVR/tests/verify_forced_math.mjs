// Isolated scalar primitives only. Exhaustive ASM domain and explicit C control.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]);
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/))
 .filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [x,c,code,result,command,status,end]=['forced_math_x','forced_math_c','forced_math_code','forced_math_result',
 'forced_math_command','forced_math_status','__bss_end'].map(at);
const names=['forced_math_selected','forced_math_c_reference','forced_math_original','forced_math_coefficient','forced_math_original_coefficient'];
const selectedAliasesExplicitC=at(names[0])===at(names[1]);
assert.equal(selectedAliasesExplicitC,meta.backend==='c','Disabled ASM selects the identical explicit C body');
const entries=new Map(names.map((name,i)=>[at(name),i]));
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const stats=names.map(name=>({name,calls:0,muls:0,minCycles:Infinity,maxCycles:0}));
let active=null,abi=true,returns=0,allReturns=0,cases=0,minSP=2303;
function until(done){const limit=cpu.cycles+2000;while(!done()){
 assert.ok(cpu.cycles<limit,'Scalar timeout');const opcode=cpu.progMem[cpu.pc],entry=entries.get(cpu.pc*2);
 if(entry!==undefined){
  assert.equal(active,null);const original=abi?saved.map(r=>cpu.data[r]):null;
  const patterns=abi?saved.map(r=>(returns*73+r*19)&255):null;
  if(abi)saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={entry,sp:cpu.SP,start:cpu.cycles,muls:0,original,patterns};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.entry],cycles=cpu.cycles-a.start;
  assert.equal(cpu.data[1],0,'r1 clear on every return');
  if(abi){assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'GNU saved registers');saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});++returns;}
  ++s.calls;s.muls+=a.muls;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  if(meta.backend==='asm'&&a.entry===0){assert.equal(a.muls,2);assert.equal(cycles,24);}
  active=null;++allReturns;
 }
}}
until(()=>cpu.data[status]===1);
function run(kind,value,coefficient,encoded){
 cpu.dataView.setInt16(x,value,true);cpu.data[c]=coefficient;cpu.data[code]=encoded;
 cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
 assert.equal(cpu.dataView.getInt16(x,true),value);assert.equal(cpu.data[c],coefficient);assert.equal(cpu.data[code],encoded);
 return cpu.dataView.getInt16(result,true);
}
for(let encoded=0;encoded<16;encoded++){
 const expected=Math.floor((2185*(encoded<<6)+16384)/32768);
 assert.equal(run(4,0,0,encoded),expected);assert.equal(run(5,0,0,encoded),expected);
}
function check(value,coefficient){
 const expected=Number((BigInt(value)*BigInt(coefficient)+32n)>>6n);
 assert.equal(expected,Number((BigInt(value)*BigInt(coefficient<<7)+4096n)>>13n));
 for(const kind of [1,2,3])assert.equal(run(kind,value,coefficient,0),expected,`${kind}/${value}/${coefficient}`);
 ++cases;
}
const edges=[-32768,-32767,-16385,-16384,-257,-256,-65,-64,-33,-32,-31,-1,0,1,31,32,33,63,64,65,255,256,16383,16384,32766,32767];
for(let coefficient=0;coefficient<64;coefficient++)for(const value of edges)check(value,coefficient);
let seed=0x892ac136;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let i=0;i<8192;i++)check((random()&65535)-32768,random()%64);
const structuredCases=cases;let exhaustiveCases=0;
if(meta.backend==='asm'){
 for(let coefficient=0;coefficient<64;coefficient++){
  for(let value=-32768;value<=32767;value++){
   abi=(value&1023)===0;
   const expected=Math.floor((value*coefficient+32)/64);
   assert.equal(expected,Math.floor((value*(coefficient<<7)+4096)/8192));
   assert.equal(run(1,value,coefficient,0),expected,`Exhaustive ${value}/${coefficient}`);++exhaustiveCases;
  }
  if((coefficient&7)===7)console.log('Passed exhaustive coefficients 0..'+coefficient);
 }
 assert.equal(exhaustiveCases,65536*64);
}
const report={scope:'Isolated C/ASM arithmetic; no C decoder execution or timing',backend:meta.backend,binarySha256:meta.binarySha256,
 structuredCases,randomCases:8192,all16CoefficientCodes:true,all64Q6Coefficients:true,exhaustiveCases,
 selectedAliasesExplicitC,
 exhaustiveSigned16ByUnsigned6:meta.backend==='asm',originalAndCAndIndependentExact:true,negativeTiesPreserved:true,
 checkedCalleeSavedReturns:returns,checkedR1Returns:allReturns,peakStack:2303-minSP,statistics:stats,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
