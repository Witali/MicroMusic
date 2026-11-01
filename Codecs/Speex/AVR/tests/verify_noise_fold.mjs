// Compare original forty-value fold, five-value lookup and explicit C.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]);
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=name=>{const rows=[...symbols].filter(([n])=>n===name||n.startsWith(name+'.'));assert.equal(rows.length,1,name);return rows[0][1];};
const [cache,out,scratch,gain,sub,command,status,end]=['fold_cache','fold_output','fold_scratch','fold_gain','fold_sub','fold_command','fold_status','__bss_end'].map(at);
const entries=new Map([[at('speex_wb_noise_fold40_avr'),'after'],[at('fold_before'),'before'],
 [at('speex_wb_fold5_avr'),'leaf'],[at('speex_wb_noise_scale5_avr'),'scaleLeaf']]);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,returns=0,cases=0,minSP=2303;
const stats=Object.fromEntries(['before','after','leaf','scaleLeaf'].map(n=>[n,{calls:0,muls:0,minCycles:Infinity,maxCycles:0,cycles:0}]));
function until(predicate){const deadline=cpu.cycles+50000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'Fold timeout');const opcode=cpu.progMem[cpu.pc],label=entries.get(cpu.pc*2);
 if(label&&!active){
  const original=saved.map(r=>cpu.data[r]);
  // AVR's later arguments overlap call-saved registers: preserve valid
  // g/scratch inputs while randomizing the non-argument saved registers.
  const argumentsInSaved=new Set(label==='after'?[14,15,16,17]:label==='before'?[16,17]:[]);
  const patterns=saved.map((r,i)=>argumentsInSaved.has(r)?original[i]:(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});active={label,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  assert.deepEqual(saved.map(r=>cpu.data[r]),active.patterns,'Callee-saved ABI');assert.equal(cpu.data[1],0,'r1');
  // Both controllers also multiply the byte subframe index by 40 once.
  assert.equal(active.muls,{before:441,after:29,leaf:55,scaleLeaf:28}[active.label],'Actual hardware multiplies');
  const s=stats[active.label],cycles=cpu.cycles-active.start;
  s.calls++;s.muls+=active.muls;s.cycles+=cycles;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=active.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function folded(v,g){const t=BigInt.asIntN(16,(29491n*BigInt(v))>>15n);
 return Number(BigInt.asIntN(16,BigInt.asUintN(32,t*BigInt(g)+256n)>>9n));}
function check(values,g,which=cases&3){
 values[2]=0; // NB1's middle noise class is an exact zero at every scale.
 const data=Buffer.alloc(212,0x96),classes=Array.from({length:160},(_,i)=>(i*3+(i>>4)+cases)%5);
 classes.forEach((v,i)=>{data[2+i]=v;});values.forEach((v,i)=>data.writeInt16LE(v,162+2*i));
 values.forEach((v,i)=>data.writeInt16LE(Number((29491n*BigInt(v))>>15n),200+2*i));
 const table=values.map(v=>folded(v,g));
 const answer=Array.from({length:40},(_,i)=>{const v=table[classes[40*which+i]];return (i&1)?Number(BigInt.asIntN(16,-BigInt(v))):v;});
 for(const kind of [1,2,3,4,5,6,7]){
  cpu.data.set(data,cache);cpu.data.fill(0x5a,out,out+84);cpu.data.fill(0xa6,scratch,scratch+14);
  cpu.dataView.setInt32(gain,g,true);cpu.data[sub]=which;cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  const expected=Buffer.alloc(84,0x5a);(kind<=3?answer:table).forEach((v,i)=>expected.writeInt16LE(v,2+2*i));
  assert.ok(Buffer.from(cpu.data.subarray(out,out+84)).equals(expected),`Output/guards ${cases},${g},${kind}`);
  assert.ok(Buffer.from(cpu.data.subarray(cache,cache+212)).equals(data),'Readonly workspace and guards');
  const expectedScratch=Buffer.alloc(14,0xa6);if(kind<=2)table.forEach((v,i)=>expectedScratch.writeInt16LE(v,2+2*i));
  assert.ok(Buffer.from(cpu.data.subarray(scratch,scratch+14)).equals(expectedScratch),'Five-word scratch and guards');
  assert.equal(cpu.dataView.getInt32(gain,true),g);assert.equal(cpu.data[sub],which);assert.equal(cpu.data[1],0);
 }
 ++cases;
}
let seed=0xc345b19f;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let word=0;word<65536;word++){
 check(Array.from({length:5},(_,i)=>((word+i*13107)&65535)-32768),random()|0);
 if((cases&16383)===0)console.log('Complete-word cases',cases);
}
const gains=new Set([-2147483648,2147483647,-65537,-1,0,1,904447,904448]);
for(let bit=0;bit<31;bit++)for(const delta of [-1,0,1]){gains.add((2**bit+delta)|0);gains.add((-(2**bit)+delta)|0);}
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const scales=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(g=>Number((28406n*BigInt(g))/32768n));
for(const s of scales){
 const values=[Math.floor((-s+4096)/8192),Math.floor((-s+8192)/16384),0,Math.floor((s+8192)/16384),Math.floor((s+4096)/8192)];
 for(const g of gains)for(let which=0;which<4;which++)check(values,g,which);
}
for(const s of Object.values(stats)){assert.equal(s.calls,cases);s.meanCycles=s.cycles/cases;}
assert.equal(returns,4*cases);
const report={scope:'Vector/scalar arithmetic and table lookup; C decoder not executed or timed',binarySha256:meta.binarySha256,
 cases,sevenPathsExact:true,fullSigned16SweepAtNonzeroClassSlots:true,zeroClass2:true,callerScales:scales.length,structuredGains:gains.size,
 allFourSubframes:true,independentBigInt:true,arbitraryNonArgumentRegisterPatterns:true,
 argumentRegistersPreserved:true,allLeafCalleeSavedRegisterPatterns:true,calleeSavedAndR1Returns:returns,
 readonlyCache:true,readonlyWorkspaceBytes:208,outputAndScratchGuards:true,actualMulsPerSubframeBefore:441,actualMulsPerSubframeAfter:29,
 foldMulsPerSubframeBefore:440,foldMulsPerSubframeAfter:28,addressMulsPerSubframe:1,
 asm:stats,peakStack:2303-minSP,freeSram:minSP-end+1,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
