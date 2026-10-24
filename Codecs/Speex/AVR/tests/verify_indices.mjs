// Independent bit-by-bit oracle plus actual AVR load-address/ABI checks.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=join(root,'build/indices');
const headerMode=process.argv.includes('--header'),widths=headerMode?[7,5,1]:[5,5,5,5];
const blockBits=widths.reduce((a,b)=>a+b,0);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function addr(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const entries=new Set((headerMode?['header_before','header_after']:['indices_before','speex_nb3_unpack_indices']).map(n=>{
 const entry=[...symbols].find(([s])=>s===n||s.startsWith(n+'.'));assert.ok(entry,n);return entry[1];}));
const binary=readFileSync(join(dir,'indices.bin')),program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),status=addr('indices_status'),command=addr('indices_command');
const input=addr('indices_input'),output=addr('indices_output');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];
const timing=Array.from({length:8},(_,offset)=>({offset,before:{min:Infinity,max:0,total:0,calls:0},after:{min:Infinity,max:0,total:0,calls:0}}));
let active=null,cycles=0,reads=[],cases=0,seed=0x4285ea19;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
for(let i=0;i<42;i++)cpu.readHooks[input+i]=a=>{reads.push(a-input-1);return cpu.data[a];};
function until(p){const end=cpu.cycles+20000;while(!p()){
 assert.ok(cpu.cycles<end,'Reader timeout');
 if(entries.has(cpu.pc*2)){assert.equal(active,null);active={sp:cpu.SP,c:cpu.cycles,r:regs.map(r=>cpu.data[r])};}
 avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=addr('__bss_end'));
 if(active&&cpu.SP===active.sp+2){assert.deepEqual(regs.map(r=>cpu.data[r]),active.r);assert.equal(cpu.data[1],0);
  cycles=cpu.cycles-active.c;active=null;}
}}
until(()=>cpu.data[status]===1);
function check(position,offset,available,overflow,values=null){
 const data=new Uint8Array(40);for(let i=0;i<40;i++)data[i]=random();
 const start=position*8+offset,limit=start+available;
 if(values){let p=start;for(let i=0;i<widths.length;i++)for(let k=widths[i]-1;k>=0;k--,p++){
  const value=(values[i]>>k)&1;
  data[p>>>3]=(data[p>>>3]&~(1<<(7-p%8)))|(value<<(7-p%8));
 }}
 let bit=start,of=overflow;const expected=[];
 for(const width of widths){
  if(of||bit+width>limit){of=1;expected.push(0);continue;}
  let value=0;for(let j=0;j<width;j++,bit++)value=(value<<1)|((data[bit>>>3]>>(7-bit%8))&1);
  expected.push(value);
 }
 const guarded=Uint8Array.from([0x39,...data,0x93]);cpu.data.set(guarded,input);
 for(const [name,value] of [['position',position],['offset',offset],['limit',limit],['overflow',overflow]])
  cpu.dataView.setInt16(addr('indices_'+name),value,true);
 for(let variant=1;variant<=2;variant++){
  reads=[];cpu.data[status]=1;cpu.data[command]=variant+(headerMode?2:0);until(()=>cpu.data[status]===2);assert.equal(active,null);
  assert.deepEqual([...cpu.data.slice(output,output+6)],[0xa5,...expected,...(headerMode?[0xcc]:[]),0x5a]);
  assert.equal(cpu.dataView.getInt16(addr('indices_result_position'),true),bit>>>3);
  assert.equal(cpu.dataView.getInt16(addr('indices_result_offset'),true),bit&7);
  assert.equal(cpu.dataView.getInt16(addr('indices_result_overflow'),true),of);
  assert.equal(cpu.data[addr('indices_metadata_ok')],1);assert.equal(cpu.data[addr('indices_zero')],0);
  assert.deepEqual(cpu.data.slice(input,input+42),guarded,'Read-only input/guards');
  for(const a of reads)assert.ok(!overflow&&available>=widths[0]&&a>=position&&a<=((limit-1)>>>3),'Read past valid input bytes');
  if(!overflow&&available>=blockBits){const t=timing[offset][variant===1?'before':'after'];t.calls++;t.total+=cycles;t.min=Math.min(t.min,cycles);t.max=Math.max(t.max,cycles);}
 }cases++;
}
for(let offset=0;offset<8;offset++)for(let n=0;n<=blockBits+7;n++)for(let i=0;i<64;i++)check(i%32,offset,n,0);
if(headerMode){
 for(let offset=0;offset<8;offset++)for(let h=0;h<8192;h++)check(h%32,offset,13,0,[h>>6,(h>>1)&31,h&1]);
} else for(let offset=0;offset<8;offset++)for(let pair=0;pair<3;pair++)for(let a=0;a<32;a++)for(let b=0;b<32;b++){
 const values=[random()&31,random()&31,random()&31,random()&31];values[pair]=a;values[pair+1]=b;
 check(random()%32,offset,20,0,values);
}
for(let i=0;i<32768;i++)check(random()%32,random()%8,blockBits+random()%8,0);
const overflowValues=[1,2,-1,32767,-32768];
for(let i=0;i<512;i++)check(random()%32,random()%8,random()%(blockBits+8),overflowValues[i%overflowValues.length]);
assert.equal(cases,headerMode?109568:72192);
for(const r of timing)for(const v of ['before','after'])r[v].mean=Number((r[v].total/r[v].calls).toFixed(4));
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0 mixed Os/O3, LTO, fwrapv, fno-strict-aliasing',
 simulator:'avr8js 0.21.1',binarySha256:createHash('sha256').update(binary).digest('hex'),
 asmEnabled:false,casesPerImplementation:cases,indicesPerImplementation:headerMode?undefined:cases*4,
 fieldsPerImplementation:cases*widths.length,fieldWidths:widths,all8192Headers:headerMode,
 offsets:[0,1,2,3,4,5,6,7],availableBits:[0,blockBits+7],allAdjacentIndexPairs:!headerMode,randomCases:32768,stickyOverflowCases:512,overflowValues,
 oracle:'Independent bit-by-bit MSB-first reader with partial/sticky overflow',exact:true,
 inputReadAddressesChecked:true,noReadsOutsideValidInputBytes:true,inputAndGuardsIntact:true,metadataPreserved:true,
 calleeSavedRegistersPreserved:true,zeroRegisterRestored:true,validBlockTiming:timing,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,headerMode?'header-verification.json':'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
