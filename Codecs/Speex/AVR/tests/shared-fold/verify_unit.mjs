import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction,AVRTimer,timer2Config} from 'avr8js';
import {tickAvr} from '../../tests/avr_tick.mjs';
const folder=resolve(process.argv[2]),binary=readFileSync(join(folder,'wb.bin'));
const symbols=new Map(readFileSync(join(folder,'symbols.txt'),'utf8').split(/\r?\n/).map(x=>x.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [output,codes,scale,gain,irqs,command,status,kind,end]=['unit_out','unit_codes','unit_scale','unit_gain','unit_irqs','unit_command','unit_status','unit_kind','__bss_end'].map(at);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);new AVRTimer(cpu,timer2Config);
const callee=[...Array.from({length:16},(_,i)=>i+2),28,29],inject=callee.filter(r=>r<14||r>=28);
const families=[['speex_wb_excitation40_avr','exc_10_32_table',32,10,4],['speex_wb_excitation8_40_avr','exc_8_128_table',128,8,5],['speex_wb_excitation_nb2_40_avr','exc_10_16_table',16,10,4],['speex_wb_excitation_nb8_40_avr','exc_20_32_table',32,20,2]];
let active=null,returns=0,minSP=2303;const stats=families.map(f=>({kernel:f[0],calls:0,cycles:0,minCycles:Infinity,maxCycles:0}));
const entries=new Map(families.map((f,i)=>[at(f[0]),i]));
function until(done){const deadline=cpu.cycles+200000;while(!done()){
 assert.ok(cpu.cycles<deadline,'Timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc],before=cpu.cycles,enabled=cpu.interruptsEnabled;
 if(entries.has(pc)){
  assert.equal(active,null);const original=callee.map(r=>cpu.data[r]);inject.forEach(r=>{cpu.data[r]=(returns*73+r*19)&255;});
  active={family:entries.get(pc),sp:cpu.SP,original,values:callee.map(r=>cpu.data[r]),ownCycles:0,flash:[]};
 }
 if(active&&((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8))active.flash.push(cpu.dataView.getUint16(30,true));
 avrInstruction(cpu);if(active&&enabled)active.ownCycles+=cpu.cycles-before;
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.family];assert.deepEqual(callee.map(r=>cpu.data[r]),a.values,'Callee registers');assert.equal(cpu.data[1],0,'r1');
  const [,table,,width,vectors]=families[a.family];const addr=at(table),expected=[];
  for(let v=0;v<vectors;v++)for(let j=0;j<width;j++)expected.push(addr+width*cpu.data[codes+2+v]+j);
  assert.deepEqual(a.flash,expected,'Exact table read addresses');++s.calls;s.cycles+=a.ownCycles;s.minCycles=Math.min(s.minCycles,a.ownCycles);s.maxCycles=Math.max(s.maxCycles,a.ownCycles);
  callee.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
 tickAvr(cpu,enabled);minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
}}
until(()=>cpu.data[status]===1);
const scales=[0,1,255,256,4095,4096,262143,262144,524287,524288,120988612,121000000],gains=[0,1,255,256,511,512,513,32767,32768,65535,65536,904448,2147483647,-2147483648,-1];
let cases=0,totalIrqs=0;const rows=[];
for(let family=0;family<4;family++){
 const [name,table,size,width,vectors]=families[family],addr=at(table);
 for(let code=0;code<size;code++)for(const s of scales)for(const g of gains){
  const indices=Array.from({length:5},(_,v)=>(code+7*v)%size),expected=[];
  for(let i=0;i<40;i++){
   const shape=(binary[addr+width*indices[Math.floor(i/width)]+i%width]<<24)>>24;
   const innovation=(BigInt(shape)*BigInt(s)+262144n)>>19n;
   const t=(29491n*innovation)>>15n,word=BigInt.asIntN(16,(t*BigInt(g)+256n)>>9n);
   expected.push(Number(BigInt.asIntN(16,(i&1)?-word:word)));
  }
  for(let backend=0;backend<2;backend++){
   cpu.data.fill(165,output,output+84);cpu.data.fill(165,codes,codes+9);cpu.data.set(indices,codes+2);cpu.dataView.setInt32(scale,s,true);cpu.dataView.setInt32(gain,g,true);
   const oldIrqs=cpu.dataView.getUint16(irqs,true);cpu.data[kind]=2*family+backend;cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);
   assert.deepEqual(expected.map((_,i)=>cpu.dataView.getInt16(output+2+2*i,true)),expected,name+' '+code+'/'+s+'/'+g+' backend'+backend);
   assert.deepEqual([...cpu.data.subarray(codes+2,codes+7)],indices,'Read-only indices');for(const k of [0,1,82,83])assert.equal(cpu.data[output+k],165,'Output guard');for(const k of [0,1,7,8])assert.equal(cpu.data[codes+k],165,'Index guard');
   assert.equal(cpu.dataView.getInt32(scale,true),s);assert.equal(cpu.dataView.getInt32(gain,true),g);assert.equal(cpu.data[1],0);
   const ticks=(cpu.dataView.getUint16(irqs,true)-oldIrqs)&65535;assert.ok(ticks>0,'Interrupt progress');totalIrqs+=ticks;
  }
  ++cases;
 }
 rows.push({kernel:name,cases:size*scales.length*gains.length,...stats[family]});console.log('PASS',name,'cases',rows.at(-1).cases);
}
assert.equal(cases,37440);assert.equal(returns,cases);
const report={scope:'Isolated C/ASM/BigInt arithmetic and GNU ABI with active Timer2 interrupts; no complete C decoder',cases,asmReturns:returns,allCodebookRows:true,all40TableAddresses:true,exactOutput:true,calleeSavedAndR1:true,readOnlyInputsAndGuards:true,includesInterrupts:true,interrupts:totalIrqs,physicalBoardTested:false,peakStackBytes:2303-minSP,statistics:rows};
writeFileSync(join(folder,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
