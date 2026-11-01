// Four scalar paths and independent original-equation arithmetic; no C decoder.
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
const at=name=>{const matches=[...symbols].filter(([key])=>key===name||key.startsWith(name+'.'));assert.equal(matches.length,1,name);return matches[0][1];};
const [scale,out,command,status,end]=['values_scale','values_output','values_command','values_status','__bss_end'].map(at);
const entries=new Map([[at('speex_low_noise_values5'),'after'],[at('noise_values5_before'),'before']]);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,returns=0;
const stats={before:{minCycles:Infinity,maxCycles:0,cycles:0,muls:0,calls:0},after:{minCycles:Infinity,maxCycles:0,cycles:0,muls:0,calls:0}};
function until(predicate){const deadline=cpu.cycles+10000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'Noise-table timeout');const opcode=cpu.progMem[cpu.pc],label=entries.get(cpu.pc*2);
 if(label){
  assert.equal(active,null);const original=saved.map(reg=>cpu.data[reg]);
  const patterns=saved.map(reg=>(returns*73+reg*19)&255);saved.forEach((reg,i)=>{cpu.data[reg]=patterns[i];});
  active={label,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0};
 }
 if(active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++active.muls;
 avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  assert.deepEqual(saved.map(reg=>cpu.data[reg]),active.patterns,'Callee-saved ABI');assert.equal(cpu.data[1],0,'r1');
  assert.equal(active.muls,active.label==='after'?0:32,'Actual hardware MULs');
  const s=stats[active.label],cycles=cpu.cycles-active.start;
  s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  s.cycles+=cycles;s.muls+=active.muls;++s.calls;
  saved.forEach((reg,i)=>{cpu.data[reg]=active.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function expected(s){
 return [-2,-1,0,1,2].map(n=>{
  const a=BigInt(n*128),b=BigInt(s),p=BigInt.asIntN(32,a*(b>>14n)+((a*(b&16383n))>>14n));
  return Number(BigInt.asIntN(16,(BigInt.asIntN(32,p<<7n)+8192n)>>14n));
 });
}
function check(s){
 const reference=expected(s);
 for(const kind of [1,2,3,4]){
  cpu.dataView.setInt32(scale,s,true);cpu.data.fill(0x5a,out,out+14);
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.deepEqual(Array.from({length:5},(_,i)=>cpu.dataView.getInt16(out+2+2*i,true)),reference,`${s} backend ${kind}`);
  assert.equal(cpu.dataView.getUint16(out,true),0x5a5a);assert.equal(cpu.dataView.getUint16(out+12,true),0x5a5a);
  assert.equal(cpu.dataView.getInt32(scale,true),s);assert.equal(cpu.data[1],0);
 }
 ++cases;
}
const values=new Set(),maximum=121000000;
function add(n){if(n>=0&&n<=maximum)values.add(n);}
for(const quotient of [0,1,2,255,1023,4095,7384])for(let residue=0;residue<16384;residue++)add(quotient*16384+residue);
const residues=[0,4095,4096,4097,8191,8192,8193,12287,12288,12289,16383];
for(let q=0;q<=Math.floor(maximum/16384);q++)for(const residue of residues)add(q*16384+residue);
for(const delta of [-1,0,1]){add(maximum+delta);add(65536+delta);add(2**20+delta);}
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const gains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const actual=gains.map(g=>Number((28406n*BigInt(g))/32768n));actual.forEach(add);
assert.equal(actual.length,32);assert.ok(Math.max(...actual)<=maximum);
let seed=0xab52cf13;for(let i=0;i<32768;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;add(seed%(maximum+1));}
for(const s of values){check(s);if((cases&32767)===0)console.log('Checked',cases,'scales');}
assert.equal(returns,2*cases);for(const s of Object.values(stats)){assert.equal(s.calls,cases);s.meanCycles=s.cycles/cases;}
const report={scope:'Isolated old/new ASM and explicit C scalar paths; C decoder not executed or timed',
 binarySha256:meta.binarySha256,baselineNoiseSourceSha256:meta.baselineNoiseSourceSha256,cases,
 fourPathsExact:true,calleeSavedAndR1Returns:returns,arbitraryRegisterPatterns:true,outputGuards:true,readonlyScale:true,
 scaleMin:0,scaleMax:maximum,callerTableScales:actual.length,callerScaleMax:Math.max(...actual),
 fullResidueSweeps:7,residuePeriod:16384,boundaryResidues:residues,asm:stats,
 includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
