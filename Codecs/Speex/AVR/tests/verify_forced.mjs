// Independent original Q14 arithmetic, old three-tap controls, memory and ABI.
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
const [out,history,scale,row,offset,count,coefficient,command,status,end,table,leaf,old]=['forced_output','forced_history','forced_scale',
 'forced_row','forced_offset','forced_count','forced_coefficient','forced_command','forced_status','__bss_end','exc_20_32_table',
 'speex_avr_forced_innovation_n','speex_avr_long_innovation_n'].map(at);
const source=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/exc_20_32_table.c'),'utf8');
const shapes=source.match(/\[640\]\s*=\s*\{([^}]+)\}/)[1].split(',').map(s=>s.trim()).filter(Boolean).map(Number);
assert.equal(shapes.length,640);assert.ok(binary.subarray(table,table+640).equals(Buffer.from(shapes.map(v=>v&255))));
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,cases=0,returns=0,minSP=2303,kind=0,requested=0,positiveClips=0,negativeClips=0;
let lastNewCycles=0,lastOldCycles=0,pairedTimingCases=0;
const seenShapes=new Set();
const stats=Array.from({length:11},(_,n)=>({count:n,calls:0,newMuls:0,oldMuls:0,newMin:Infinity,newMax:0,oldMin:Infinity,oldMax:0}));
const rd=cpu.readData.bind(cpu),wr=cpu.writeData.bind(cpu);
cpu.readData=a=>{
 if(active&&active.isNew){
  assert.ok(active.n||a>=32,'Null read');
  if(a>=out&&a<out+24)assert.fail('Output read');
  if(a>=history&&a<history+24){assert.ok(a>=history+2&&a<history+2+2*active.n,'History bound');active.reads.push(a);}
 }
 return rd(a);
};
cpu.writeData=(a,v,mask)=>{
 if(active&&active.isNew){
  assert.ok(active.n||a>=32,'Null write');
  if(a>=out&&a<out+24){assert.ok(a>=out+2&&a<out+2+2*active.n,'Output bound');active.writes.push(a);}
  assert.ok(a<history||a>=history+24,'History modified');
 }
 return wr(a,v,mask);
};
function until(done){const limit=cpu.cycles+100000;while(!done()){
 assert.ok(cpu.cycles<limit,'Forced timeout');const opcode=cpu.progMem[cpu.pc],pc=cpu.pc*2;
 if(pc===leaf||pc===old){
  assert.equal(active,null);const isNew=pc===leaf,n=cpu.data[12];assert.equal(n,requested);
  const original=saved.map(r=>cpu.data[r]);
  const patterns=saved.map((r,i)=>[12,14,16,17].includes(r)||!isNew&&r===15?original[i]:(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={isNew,n,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0,flash:[],reads:[],writes:[]};
  if(isNew&&!n)for(const r of [24,22,20])assert.equal(cpu.dataView.getUint16(r,true),0);
 }
 if(active){
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++active.muls;
  if((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)active.flash.push(cpu.dataView.getUint16(30,true));
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,cycles=cpu.cycles-a.start,s=stats[a.n];
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'GNU callee-saved ABI');assert.equal(cpu.data[1],0);
  assert.equal(a.muls,(a.isNew?6:10)*a.n);assert.deepEqual(a.flash,Array.from({length:a.n},(_,i)=>table+20*cpu.data[row]+cpu.data[offset]+i));
  if(a.isNew){
   assert.deepEqual(a.reads,Array.from({length:2*a.n},(_,i)=>history+2+i));
   assert.deepEqual(a.writes,Array.from({length:2*a.n},(_,i)=>out+2+i));
   s.newMuls+=a.muls;s.newMin=Math.min(s.newMin,cycles);s.newMax=Math.max(s.newMax,cycles);++s.calls;
   if(!a.n)assert.equal(cycles,6);
   lastNewCycles=cycles;
  }else{s.oldMuls+=a.muls;s.oldMin=Math.min(s.oldMin,cycles);s.oldMax=Math.max(s.oldMax,cycles);lastOldCycles=cycles;}
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
until(()=>cpu.data[status]===1);
let seed=0x483ab170;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
function check(s,r,c,n,values,off=0){
 assert.ok(off>=0&&off+n<=20);
 const expected=Buffer.alloc(24,0xa5),input=Buffer.alloc(24);
 for(let i=0;i<12;i++)input.writeInt16LE(values?values[i%values.length]:((random()&65535)-32768),2*i);
 for(let i=0;i<n;i++){
  let p=BigInt(c)*BigInt(input.readInt16LE(2+2*i));
  if(p>2048000n){++positiveClips;p=2048000n;}if(p< -2048000n){++negativeClips;p=-2048000n;}
  seenShapes.add(20*r+off+i);
  const a=BigInt(4*shapes[20*r+off+i]),b=BigInt(s),q=a*(b>>14n)+((a*(b&16383n))>>14n);
  let v=BigInt.asIntN(32,(p<<8n)+q*128n+8192n)>>14n;
  if(v>32767n)v=32767n;if(v< -32767n)v= -32767n;
  expected.writeInt16LE(Number(v),2+2*i);
 }
 for(kind of [1,2,3,4]){
  cpu.data.set(input,history);cpu.data.fill(0xa5,out,out+24);cpu.dataView.setInt32(scale,s,true);
  cpu.data[row]=r;cpu.data[offset]=off;cpu.data[count]=requested=n;cpu.data[coefficient]=c;cpu.data[status]=1;cpu.data[command]=kind;
  until(()=>cpu.data[status]===2);
  assert.ok(Buffer.from(cpu.data.subarray(out,out+24)).equals(expected),`Exact output/guards: ${kind}/${s}/${r}/${c}/${n}`);
  assert.ok(Buffer.from(cpu.data.subarray(history,history+24)).equals(input),'History unchanged');assert.equal(cpu.data[1],0);
 }
 assert.equal(lastOldCycles-lastNewCycles,n?32*n+35:0,'Exact matched leaf saving');++pairedTimingCases;
 ++cases;
}
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const caller=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(g=>Number((28406n*BigInt(g))/32768n));
const scales=[...new Set([0,1,255,256,4095,4096,8191,8192,16383,16384,262143,262144,262145,524287,524288,524289,120988612,121000000,...caller])];
for(const s of scales)for(let r=0;r<32;r++)for(let n=0;n<=10;n++)for(const off of [0,10])check(s,r,(r*11+n*7+s)%64,n,undefined,off);
for(let c=0;c<64;c++){
 const bound=c?Math.floor(2048000/c):32768;
 const values=[-32768,-32767,-1,0,1,32766,32767,...[-1,0,1].flatMap(d=>[bound+d,-bound+d])].filter(v=>v>=-32768&&v<=32767);
 for(const x of values)for(const s of [0,262144,121000000])check(s,(c+x)&31,c,10,[x]);
}
for(let i=0;i<8192;i++){const n=random()%11;check(random()%121000001,random()%32,random()%64,n,undefined,random()%(21-n));}
assert.ok(positiveClips&&negativeClips);assert.ok(stats.every(s=>s.calls>0));assert.equal(seenShapes.size,640);
const report={scope:'Isolated one-tap C/ASM and original three-tap controls; no C decoder execution',binarySha256:meta.binarySha256,
 cases,all32Rows:true,all20RowPositions:true,distinctShapePositions:seenShapes.size,uniqueScales:scales.length,callerScales:32,all64Coefficients:true,counts0Through10:true,randomCases:8192,
 cAsmOriginalAndBigIntExact:true,positiveClips,negativeClips,exactHistoryAndFlashAddresses:true,outputNotRead:true,guardsAndTails:true,
 zeroNullPointersAndNoAccess:true,calleeSavedAndR1Returns:returns,argumentRegistersPreserved:true,variable:stats,
 pairedTimingCases,nonemptyLeafSaving:'32 * count + 35 cycles',
 includesInterrupts:false,physicalBoardTested:false,peakStack:2303-minSP};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
