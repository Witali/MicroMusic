// Original Q14 decomposition, widened vector bounds, Flash/SRAM access and GNU ABI.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]);
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [out,scale,row,count,command,status,end,table,variable,fixed]=['zero20_output','zero20_scale','zero20_row','zero20_count',
 'zero20_command','zero20_status','__bss_end','exc_20_32_table','speex_avr_zero_innovation_n','speex_avr_zero_innovation10'].map(at);
const source=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/exc_20_32_table.c'),'utf8');
const shapes=source.match(/\[640\]\s*=\s*\{([^}]+)\}/)[1].split(',').map(s=>s.trim()).filter(Boolean).map(Number);
assert.equal(shapes.length,640);assert.ok(table+640<=32768);
assert.ok(binary.subarray(table,table+640).equals(Buffer.from(shapes.map(v=>v&255))),'Pinned Flash table');
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,returns=0,minSP=2303;
const originalRead=cpu.readData.bind(cpu),originalWrite=cpu.writeData.bind(cpu);
cpu.readData=a=>{if(active&&active.n===0)assert.ok(a>=32,'Null input/output dereference');return originalRead(a);};
cpu.writeData=(a,v,mask)=>{if(active&&active.n===0)assert.ok(a>=32,'Null output dereference');return originalWrite(a,v,mask);};
const stats=Array.from({length:21},(_,n)=>({count:n,calls:0,muls:0,minCycles:Infinity,maxCycles:0}));
let fixedCalls=0,fixedMin=Infinity,fixedMax=0;
for(let p=out;p<out+44;p++){
 cpu.readHooks[p]=a=>{if(active)assert.fail('Zero vector must not read output SRAM');return cpu.data[a];};
 cpu.writeHooks[p]=()=>{if(active)++active.writes;return false;};
}
function until(done){const limit=cpu.cycles+100000;while(!done()){
 assert.ok(cpu.cycles<limit,'Zero20 timeout');const opcode=cpu.progMem[cpu.pc],pc=cpu.pc*2;
 if(pc===variable||pc===fixed){
  assert.equal(active,null);const isVariable=pc===variable,n=isVariable?cpu.data[16]:10;
  const target=cpu.dataView.getUint16(24,true),shape=cpu.dataView.getUint16(22,true);
  if(!n){assert.equal(target,0);assert.equal(shape,0);}
  const original=saved.map(r=>cpu.data[r]),patterns=saved.map((r,i)=>isVariable&&r===16?original[i]:(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={variable:isVariable,n,target,shape,sp:cpu.SP,start:cpu.cycles,original,patterns,writes:0,muls:0,flash:[]};
 }
 if(active){
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++active.muls;
  if((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)active.flash.push(cpu.dataView.getUint16(30,true));
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,cycles=cpu.cycles-a.start;assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'GNU callee-saved ABI');assert.equal(cpu.data[1],0);
  assert.equal(a.muls,4*a.n);assert.equal(a.writes,2*a.n);assert.deepEqual(a.flash,Array.from({length:a.n},(_,i)=>a.shape+i));
  if(a.variable){const s=stats[a.n];++s.calls;s.muls+=a.muls;s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);if(!a.n)assert.equal(cycles,6);}
  else{++fixedCalls;fixedMin=Math.min(fixedMin,cycles);fixedMax=Math.max(fixedMax,cycles);}
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
function check(s,r,n){
 const expected=Buffer.alloc(44,0xa5);
 for(let i=0;i<n;i++){
  const a=BigInt(4*shapes[20*r+i]),b=BigInt(s),q=a*(b>>14n)+((a*(b&16383n))>>14n);
  const original=(q*128n+8192n)>>14n,collapsed=(BigInt(shapes[20*r+i])*b+262144n)>>19n;
  assert.equal(original,collapsed);expected.writeInt16LE(Number(original),2+2*i);
 }
 for(const kind of [1,2,...([10,20].includes(n)?[3]:[])]){
  cpu.data.fill(0xa5,out,out+44);cpu.dataView.setInt32(scale,s,true);cpu.data[row]=r;cpu.data[count]=n;
  cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.ok(Buffer.from(cpu.data.subarray(out,out+44)).equals(expected),'Exact samples/untouched tail/guards');
  assert.equal(cpu.dataView.getInt32(scale,true),s);assert.equal(cpu.data[row],r);assert.equal(cpu.data[count],n);assert.equal(cpu.data[1],0);
 }
 ++cases;
}
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const caller=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(g=>Number((28406n*BigInt(g))/32768n));
const scales=[...new Set([0,1,255,256,4095,4096,8191,8192,16383,16384,262143,262144,262145,524287,524288,524289,120988612,121000000,...caller])];
for(const s of scales)for(let r=0;r<32;r++)for(let n=0;n<=20;n++)check(s,r,n);
let seed=0x3924a76b;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
for(let i=0;i<4096;i++)check(random()%121000001,random()%32,random()%21);
assert.equal(fixedMin,501);assert.equal(fixedMax,501);assert.ok(stats.every(s=>s.calls>0));
const report={scope:'Isolated C/ASM zero-vector primitives; C decoder not executed or timed',binarySha256:meta.binarySha256,
 cases,originalQ14AndCollapsedFormulaExact:true,cAndAsmExact:true,counts0Through20:true,all32Rows:true,callerScales:32,uniqueScales:scales.length,
 randomCases:4096,zeroNullPointersAndNoDataAccess:true,outputGuardsAndTail:true,exactFlashAddresses:true,outputNotRead:true,
 calleeSavedAndR1Returns:returns,arbitraryNonArgumentRegisterPatterns:true,countArgumentPreserved:true,variable:stats,
 fixedTen:{calls:fixedCalls,minCycles:fixedMin,maxCycles:fixedMax},includesInterrupts:false,physicalBoardTested:false,peakStack:2303-minSP};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
