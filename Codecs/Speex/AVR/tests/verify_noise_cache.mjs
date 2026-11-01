// Verify actual cache lifetime, one RNG pass, seed progression and mixed PCM.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url));
const dir=resolve(process.argv[2]),input=resolve(process.argv[3]);
const binary=readFileSync(join(dir,'cache.bin')),metadata=JSON.parse(readFileSync(join(dir,'input.json')));
const source=JSON.parse(readFileSync(join(input,'input.json')));
const raw=readFileSync(join(input,'packets32.bin')),expected=readFileSync(join(input,'oracle.pcm'));
const hash=b=>createHash('sha256').update(b).digest('hex');
assert.equal(hash(binary),metadata.binarySha256);assert.equal(hash(raw),source.inputSha256);
assert.equal(hash(expected),source.pcmSha256);assert.equal(source.wideband,true);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const address=name=>{assert.ok(symbols.has(name),name);return symbols.get(name);};
function entry(prefix){const names=[...symbols.keys()].filter(name=>name===prefix||name.startsWith(prefix+'.'));assert.equal(names.length,1,prefix);return address(names[0]);}
const [packet,bytes,command,status,result,chunks,pcm,end]=['cache_packet','cache_bytes','cache_command','cache_status',
 'cache_result','cache_chunks','cache_pcm','__bss_end'].map(address);
const voc=entry('speex_nb1_excitation_frame'),values=entry('speex_low_noise_values5');
const indices=entry('speex_low_noise_indices40'),expand=entry('speex_low_noise_cached40');
assert.ok(!symbols.has('speex_low_noise40')&&!symbols.has('speex_wb_noise_seed'));
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);let base,live,frameBegin,moveBegin,seedAddress;
let oldChunks=0,parts=[],current=null,pending=null,minSP=2303,checkedFrames=0,checkedBlocks=0;
let totalVoc=0,totalValues=0,totalIndices=0,totalExpand=0;
function memory(at,n){return Buffer.from(cpu.data.subarray(at,at+n));}
function cacheIntact(){
 assert.ok(memory(base,170).equals(current.cache),'Read-only classes/values cache');
 assert.ok(memory(base+170,live-base-170).every(value=>value===0xa5),'Dead-prefix guard');
 assert.ok(memory(live,frameBegin-live).equals(current.delayed),'Delayed old history preserved');
}
function until(predicate){const deadline=cpu.cycles+3000000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'Cache mailbox timeout');
 const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(current){
  if(pc===voc){
   assert.equal(current.mode,1);++current.voc;++totalVoc;
   cpu.data.fill(0xa5,base+170,live);current.delayed=memory(live,frameBegin-live);
  }
  if(pc===values){++current.values;++totalValues;}
  if(pc===indices){++current.indices;++totalIndices;}
  if(pc===expand){
   assert.equal(current.mode,1);cacheIntact();
   const sub=cpu.data[20],out=cpu.dataView.getUint16(24,true);
   assert.equal(sub,current.expand);assert.equal(cpu.dataView.getUint16(22,true),base);
   pending={sp:cpu.SP,out,sub,before:memory(out-2,2),after:memory(out+80,2)};
   ++current.expand;++totalExpand;
  }
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(pending&&opcode===0x9508&&cpu.SP===pending.sp+2){
  assert.ok(memory(pending.out,80).equals(current.noise.subarray(80*pending.sub,80*(pending.sub+1))),'Exact cached expansion');
  assert.ok(memory(pending.out-2,2).equals(pending.before)&&memory(pending.out+80,2).equals(pending.after),'Output guards');
  cacheIntact();pending=null;++checkedBlocks;
 }
 if(cpu.data[chunks]!==oldChunks){oldChunks=cpu.data[chunks];parts.push(memory(cpu.dataView.getUint16(pcm,true),160));}
}}
until(()=>cpu.data[status]===1);
const pointer=name=>cpu.dataView.getUint16(address(name),true);
base=pointer('cache_begin');live=pointer('cache_live_begin');frameBegin=pointer('cache_frame_begin');
moveBegin=pointer('cache_move_begin');seedAddress=pointer('cache_seed');
assert.equal(live-base,210);assert.equal(frameBegin-base,290);assert.equal(moveBegin-base,320);
assert.ok(base+170<=live&&base+170<=moveBegin);
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const gains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
function field(payload,bit,n){let value=0;for(let i=0;i<n;i++)value=value*2+((payload[(bit+i)>>3]>>(7-((bit+i)&7)))&1);return value;}
function prepared(payload,seed){
 const mode=payload[0]>>3,row={mode,voc:0,values:0,indices:0,expand:0,cache:Buffer.alloc(170),noise:Buffer.alloc(320),next:seed};
 if(mode!==1)return row;
 const scale=Math.floor(28406*gains[field(payload,34,5)]/32768),table=[];
 for(let n=-2;n<=2;n++){
  const a=BigInt(n*128),b=BigInt(scale);
  const product=a*(b>>14n)+((a*(b&16383n))>>14n);
  const value=Number(BigInt.asIntN(16,(BigInt.asIntN(32,product<<7n)+8192n)>>14n));
  table.push(value);row.cache.writeInt16LE(value,160+2*(n+2));
 }
 for(let i=0;i<160;i++){
  row.next=(Math.imul(1664525,row.next)+1013904223)>>>0;
  const high=(row.next>>>16)-((row.next&0x80000000)?65536:0);
  const index=Math.floor((high-Math.floor(high/8)+8192)/16384)+2;
  row.cache[i]=index;row.noise.writeInt16LE(table[index],2*i);
 }
 return row;
}
let seed=1000;
for(let f=0;f<source.frames;f++){
 const payload=raw.subarray(f*32,(f+1)*32);current=prepared(payload,seed);
 cpu.data.set(payload,packet);cpu.data[bytes]=source.packetLengths[f];cpu.data[status]=1;parts=[];cpu.data[command]=1;
 until(()=>cpu.data[status]===2);assert.equal(cpu.dataView.getInt8(result),0);
 assert.equal(parts.length,4);assert.ok(Buffer.concat(parts).equals(expected.subarray(f*640,(f+1)*640)),'Mixed PCM '+f);
 if(current.mode===1){
  assert.deepEqual([current.voc,current.values,current.indices,current.expand],[1,1,4,4]);cacheIntact();++checkedFrames;
 }else assert.deepEqual([current.voc,current.values,current.indices,current.expand],[0,0,0,0]);
 seed=current.next;assert.equal(cpu.dataView.getUint32(seedAddress,true),seed,'Exactly 160 RNG transitions per NB1 frame');
 current=null;
}
cpu.data[status]=0;cpu.data[command]=2;until(()=>cpu.data[status]===1);
assert.equal(cpu.dataView.getUint32(seedAddress,true),1000);assert.ok(memory(base,170).every(value=>value===0));
const report={binarySha256:metadata.binarySha256,inputSha256:source.inputSha256,pcmSha256:source.pcmSha256,
 frames:source.frames,cacheFrames:checkedFrames,expandedBlocks:checkedBlocks,calls:{vocoder:totalVoc,values5:totalValues,indices40:totalIndices,cached40:totalExpand},
 cacheBytes:170,firstDelayedInputByte:210,nextHistorySourceByte:320,guardBytes:40,cacheAndDelayedHistoryPreserved:true,
 seedAdvancesOnce:true,pcmExact:true,mixedModes:[1,2,8,3,4],resetClearsCache:true,includesInterrupts:false,physicalBoardTested:false,
 flashBytes:binary.length,staticSramBytes:end-256,peakStack:2303-minSP,freeSram:minSP-end+1};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS cache pipeline',JSON.stringify(report));
