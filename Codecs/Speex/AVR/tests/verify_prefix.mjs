// The independent oracle executes untouched Xiph quant_lsp/bits with RAM tables.
// The production helper uses the real AVR Flash read backend, with ASM disabled.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=join(root,'build/prefix-unit');
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const entry=[...symbols].find(([n])=>n==='prefix_new'||n.startsWith('prefix_new.'))?.[1];assert.ok(entry!==undefined);
const binary=readFileSync(join(dir,'prefix.bin')),program=new Uint16Array(16384).fill(65535);
assert.ok(binary.length<=32768);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),status=address('prefix_status'),command=address('prefix_command');
const input=address('prefix_packet'),out=address('prefix_quarters'),reference=address('prefix_reference');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,reads=[],seed=0x74b1e263,cases=0,minRaw=32767,maxRaw=-32768;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
for(let i=0;i<22;i++)cpu.readHooks[input+i]=a=>{if(active)reads.push(a-input-1);return cpu.data[a];};
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'prefix mailbox timeout');
  if(cpu.pc*2===entry){assert.equal(active,null);active={sp:cpu.SP,r:regs.map(r=>cpu.data[r])};}
  const ret=cpu.progMem[cpu.pc]===0x9508;
  avrInstruction(cpu);cpu.tick();
  if(active&&ret&&cpu.SP===active.sp+2){assert.deepEqual(regs.map(r=>cpu.data[r]),active.r);assert.equal(cpu.data[1],0);active=null;}
  assert.ok(cpu.SP>=address('__bss_end'),'Stack/static collision');
}}
until(()=>cpu.data[status]===1);
const oracleTables=[['reference_cdbk_nb',640],['reference_cdbk_nb_low1',320],['reference_cdbk_nb_high1',320]]
  .map(([name,length])=>({address:address(name),data:cpu.data.slice(address(name),address(name)+length)}));
for(const n of ['malloc','calloc','realloc','free'])assert.ok(!symbols.has(n),'No oracle heap needed');
function check(code,gain){
  const data=Uint8Array.from({length:20},()=>random()&255);let bit=0;
  for(const [width,value] of [[5,3],[18,code],[5,gain]])for(let k=width-1;k>=0;k--,bit++)
    data[bit>>>3]=(data[bit>>>3]&~(1<<(7-bit%8)))|(((value>>>k)&1)<<(7-bit%8));
  const guarded=Uint8Array.from([0x39,...data,0x93]);cpu.data.set(guarded,input);
  for(const base of [out,reference]){
    cpu.dataView.setUint16(base,0x1357,true);cpu.dataView.setUint16(base+22,0x2468,true);
    cpu.data.fill(0x55,base+2,base+22);
  }
  reads=[];cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);assert.equal(active,null);
  for(let i=1;i<=10;i++){
    const quarter=cpu.dataView.getInt16(out+2*i,true),expected=cpu.dataView.getInt16(reference+2*i,true);
    assert.equal(quarter*4,expected,`code ${code} gain ${gain} angle ${i}`);
    assert.equal(expected&15,0);minRaw=Math.min(minRaw,expected);maxRaw=Math.max(maxRaw,expected);
  }
  assert.equal(cpu.data[address('prefix_gain')],gain);assert.equal(cpu.data[address('prefix_reference_gain')],gain);
  assert.equal(cpu.data[address('prefix_char')],3);assert.equal(cpu.data[address('prefix_bit')],4);
  assert.equal(cpu.data[address('prefix_overflow')],0);
  assert.deepEqual(cpu.data.slice(input,input+22),guarded);
  for(const a of reads)assert.ok(a>=0&&a<4,'Read outside the prefix: '+a);
  assert.equal(new Set(reads).size,4);
  for(const base of [out,reference]){assert.equal(cpu.dataView.getUint16(base,true),0x1357);assert.equal(cpu.dataView.getUint16(base+22,true),0x2468);}
  cases++;
}
for(let code=0;code<(1<<18);code++)check(code,code&31);
for(let i=0;i<8192;i++)check(random()&0x3ffff,random()&31);
assert.equal(cases,270336);
for(const t of oracleTables)assert.deepEqual(cpu.data.slice(t.address,t.address+t.data.length),t.data,'Read-only original tables');
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',arithmeticAsmEnabled:false,
  compiler:'AVR GCC 7.3.0 -O2 -mcall-prologues -mrelax -fwrapv; separate non-LTO oracle objects',
  binarySha256:createHash('sha256').update(binary).digest('hex'),cases,
  all262144CodeTriples:true,randomCases:8192,angleComparisons:10*cases,minRaw,maxRaw,
  oracle:'Untouched Xiph quant_lsp.c/bits.c and original RAM tables; production Flash tables separate',
  quartersAndGainExact:true,onlyFirstFourPacketBytesRead:true,inputAndGuardsPreserved:true,
  originalTablesPreserved:true,calleeSavedRegistersAtRet:true,zeroRegisterAtRet:true,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
