// Independent equations, pinned codebooks, ABI and actual SRAM/Flash accesses.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]);
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
const hash=b=>createHash('sha256').update(b).digest('hex');assert.equal(hash(binary),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [out,indices,scale,gain,mode,command,status,end]=['low_fuse_out','low_fuse_indices','low_fuse_scale',
 'low_fuse_gain','low_fuse_mode','low_fuse_command','low_fuse_status','__bss_end'].map(at);
const entries=new Map([[at('low_fuse_before'),'before'],[at('low_fuse_after'),'after'],
 [at('speex_wb_excitation_nb2_40_avr'),'leaf'],[at('speex_wb_excitation_nb8_40_avr'),'leaf']]);
const tables={};for(const [m,name,width,rows] of [[2,'exc_10_16_table',10,16],[8,'exc_20_32_table',20,32]]){
 const text=readFileSync(join(root,'vendor/speex-1.2.1/libspeex',name+'.c'),'utf8');
 const values=text.match(/\[\d+\]\s*=\s*\{([^}]+)\}/)[1].split(',').map(s=>s.trim()).filter(Boolean).map(Number);
 assert.equal(values.length,width*rows);assert.ok(at(name)+values.length<=32768);
 assert.ok(binary.subarray(at(name),at(name)+values.length).equals(Buffer.from(values.map(v=>v&255))),'Pinned Flash codebook');
 tables[m]={name,width,rows,values,address:at(name)};
}
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,current=null,cases=0,returns=0,minSP=2303;
const stats=Object.fromEntries([2,8].map(m=>[m,Object.fromEntries(['before','after','leaf'].map(k=>[k,
 {calls:0,muls:0,mulMin:Infinity,mulMax:0,minCycles:Infinity,maxCycles:0,cycles:0,outputReads:0,outputWrites:0}]))]));
for(let p=out+2;p<out+82;p++){
 cpu.readHooks[p]=a=>{if(active)++active.reads;return cpu.data[a];};
 cpu.writeHooks[p]=()=>{if(active)++active.writes;return false;};
}
for(let p=indices;p<indices+6;p++)cpu.readHooks[p]=a=>{
 if(active){assert.ok(a>=indices+1&&a<indices+1+current.codes.length,'Read indices bounds');active.indexReads.push(a);}
 return cpu.data[a];
};
function until(done){const limit=cpu.cycles+100000;while(!done()){
 assert.ok(cpu.cycles<limit,'Low fusion timeout');const opcode=cpu.progMem[cpu.pc],label=entries.get(cpu.pc*2);
 if(label&&!active){
  const original=saved.map(r=>cpu.data[r]),argumentsInSaved=new Set(label==='leaf'?[14,15,16,17]:[12,14,15,16,17]);
  const patterns=saved.map((r,i)=>argumentsInSaved.has(r)?original[i]:(returns*73+r*29)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={label,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0,reads:0,writes:0,indexReads:[],flashReads:[]};
 }
 if(active){
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++active.muls;
  if((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)active.flashReads.push(cpu.dataView.getUint16(30,true));
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[current.mode][a.label],cycles=cpu.cycles-a.start;
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'Callee-saved ABI');assert.equal(cpu.data[1],0,'r1');
  assert.deepEqual(a.flashReads,current.flash,'Exactly forty expected Flash reads');
  assert.deepEqual(a.indexReads,current.codes.map((_,i)=>indices+1+i),'Read each valid index once');
  assert.equal(a.reads,a.label==='before'?80:0,'Intermediate output loads removed');
  assert.equal(a.writes,a.label==='before'?160:80,'Single final output store');
  if(a.label!=='before')assert.equal(a.muls,600+current.codes.length,'Same exact products and one table address MUL/vector');
  ++s.calls;s.muls+=a.muls;s.mulMin=Math.min(s.mulMin,a.muls);s.mulMax=Math.max(s.mulMax,a.muls);
  s.cycles+=cycles;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);s.outputReads+=a.reads;s.outputWrites+=a.writes;
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function check(m,s,g,row,randomCodes=null){
 const t=tables[m],codes=randomCodes??Array.from({length:40/t.width},(_,i)=>(row+7*i)%t.rows);
 const expected=Buffer.alloc(84,0x5a),flash=[];
 for(let i=0;i<40;i++){
  const offset=t.width*codes[Math.floor(i/t.width)]+i%t.width,shape=BigInt(t.values[offset]);flash.push(t.address+offset);
  const innovation=(shape*BigInt(s)+262144n)>>19n;
  const q15=(29491n*innovation)>>15n;
  const rounded=BigInt.asUintN(32,q15*BigInt(g)+256n)>>9n;
  const value=BigInt.asIntN(16,(i&1)?-rounded:rounded);expected.writeInt16LE(Number(value),2+2*i);
 }
 const rawCodes=Buffer.alloc(6,0x96);rawCodes.set(codes,1);current={mode:m,codes,flash};
 for(const kind of [1,2,3,4]){
  cpu.data.fill(0x5a,out,out+84);cpu.data.set(rawCodes,indices);cpu.dataView.setInt32(scale,s,true);cpu.dataView.setInt32(gain,g,true);cpu.data[mode]=m;
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.ok(Buffer.from(cpu.data.subarray(out,out+84)).equals(expected),`PCM/guards ${cases}/${m}/${s}/${g}/${kind}`);
  assert.ok(Buffer.from(cpu.data.subarray(indices,indices+6)).equals(rawCodes),'Readonly indices/guards');
  assert.equal(cpu.dataView.getInt32(scale,true),s);assert.equal(cpu.dataView.getInt32(gain,true),g);assert.equal(cpu.data[mode],m);assert.equal(cpu.data[1],0);
 }
 ++cases;
}
const scales=new Set([0,1,255,256,4095,4096,8191,8192,16383,16384,262143,262144,262145,524287,524288,524289,120988612,121000000]);
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const callerScales=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(g=>Number((28406n*BigInt(g))/32768n));callerScales.forEach(s=>scales.add(s));
const gainEdges=[0,1,255,256,511,512,513,32767,32768,65535,65536,904448,2147483647,-2147483648,-1];
const structured=new Set([-2147483648,2147483647,-65537,-1,0,1,904447,904448]);
for(let bit=0;bit<31;bit++)for(const d of [-1,0,1]){structured.add((2**bit+d)|0);structured.add((-(2**bit)+d)|0);}
let seed=0x39ac4187;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(const m of [2,8]){
 const t=tables[m],ss=[...scales];
 for(const s of ss)for(const g of gainEdges)for(let row=0;row<t.rows;row++)check(m,s,g,row);
 for(const g of structured)for(let row=0;row<t.rows;row++)check(m,ss[(cases+row)%ss.length],g,row);
 for(let i=0;i<4096;i++)check(m,random()%121000001,random()|0,0,Array.from({length:40/t.width},()=>random()%t.rows));
 console.log('PASS mode',m,'cases so far',cases);
}
for(const modeStats of Object.values(stats))for(const s of Object.values(modeStats))s.meanCycles=s.cycles/s.calls;
assert.equal(returns,3*cases);
const report={scope:'Isolated vector C/ASM arithmetic only; C decoder not executed or timed',binarySha256:meta.binarySha256,
 cases,fourPathsExact:true,independentBigInt:true,pinnedCodebooksExact:true,allRowsAtEveryVectorSlot:true,
 callerScales:callerScales.length,scales:scales.size,gainEdges:gainEdges.length,structuredGains:structured.size,randomCasesPerMode:4096,
 calleeSavedAndR1Returns:returns,arbitraryNonArgumentRegisterPatterns:true,argumentRegistersPreserved:true,
 readOnlyIndicesAndBounds:true,exactFlashAddresses:true,intermediateLoadsAndStoresObserved:true,outputGuards:true,
 asm:stats,includesInterrupts:false,physicalBoardTested:false,peakStack:2303-minSP,freeSram:minSP-end+1};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
