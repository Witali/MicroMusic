// Independent MSB-first reader, actual AVR reads and ABI at RET.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),dir=join(root,'build/subframe-unit');
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const entries=new Set(['subframe_before','speex_nb3_unpack_subframe'].map(n=>{
  const row=[...symbols].find(([s])=>s===n||s.startsWith(n+'.'));assert.ok(row,n);return row[1];}));
const binary=readFileSync(join(dir,'subframe.bin')),program=new Uint16Array(16384).fill(65535);
new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),command=address('subframe_command'),status=address('subframe_status');
const input=address('subframe_packet'),out=address('subframe_indices');
const regs=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,reads=[],seed=0x91c2e3a7,cases=0,cycles=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
for(let i=0;i<22;i++)cpu.readHooks[input+i]=a=>{if(active)reads.push(a-input-1);return cpu.data[a];};
function until(predicate){const deadline=cpu.cycles+30000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'subframe mailbox timeout');
  if(entries.has(cpu.pc*2)){assert.equal(active,null);active={sp:cpu.SP,t:cpu.cycles,r:regs.map(r=>cpu.data[r])};}
  const ret=cpu.progMem[cpu.pc]===0x9508;
  avrInstruction(cpu);cpu.tick();
  if(active&&ret&&cpu.SP===active.sp+2){
    assert.deepEqual(regs.map(r=>cpu.data[r]),active.r,'Callee-saved registers at RET');
    assert.equal(cpu.data[1],0,'Zero register at RET');cycles=cpu.cycles-active.t;active=null;
  }
  assert.ok(cpu.SP>=address('__bss_end'),'Stack collision');
}}
const widths=[7,5,1,5,5,5,5];
const timing=Array.from({length:4},(_,sub)=>({sub,before:{min:Infinity,max:0,total:0,calls:0},after:{min:Infinity,max:0,total:0,calls:0}}));
until(()=>cpu.data[status]===1);
function check(sub,values=null,byte=null){
  const data=Uint8Array.from({length:20},()=>random()&255);data[0]=(data[0]&7)|24;
  let bit=28+33*sub;
  if(values){let p=bit;for(let j=0;j<7;j++)for(let k=widths[j]-1;k>=0;k--,p++)
    data[p>>>3]=(data[p>>>3]&~(1<<(7-p%8)))|(((values[j]>>k)&1)<<(7-p%8));}
  if(byte)data[3+4*sub+byte[0]]=byte[1];
  const expected=[];
  for(const width of widths){let v=0;for(let i=0;i<width;i++,bit++)v=(v<<1)|((data[bit>>>3]>>(7-bit%8))&1);expected.push(v);}
  const header=(expected[0]<<6)|(expected[1]<<1)|expected[2];
  const guarded=Uint8Array.from([0x39,...data,0x93]);cpu.data.set(guarded,input);cpu.data[address('subframe_sub')]=sub;
  for(let kind=1;kind<=2;kind++){
    cpu.data.set([0xa5,0xcc,0xcc,0xcc,0xcc,0x5a],out);
    reads=[];cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);assert.equal(active,null);
    assert.equal(cpu.dataView.getUint16(address('subframe_header'),true),header);
    assert.deepEqual([...cpu.data.slice(out,out+6)],[0xa5,...expected.slice(3),0x5a]);
    assert.deepEqual(cpu.data.slice(input,input+22),guarded,'Read-only packet and guards');
    const first=3+4*sub;
    for(const a of reads)assert.ok(a>=first&&a<first+5,'Read outside five-byte window: '+a);
    assert.equal(new Set(reads).size,5,'Observe all five input bytes');
    if(kind===1){
      assert.equal(cpu.data[address('subframe_char')],bit>>>3);assert.equal(cpu.data[address('subframe_bit')],bit&7);
      assert.equal(cpu.data[address('subframe_overflow')],0);
    }
    const t=timing[sub][kind===1?'before':'after'];t.calls++;t.total+=cycles;t.min=Math.min(t.min,cycles);t.max=Math.max(t.max,cycles);
  }
  cases++;
}
for(let sub=0;sub<4;sub++){
  for(let h=0;h<8192;h++)check(sub,[h>>>6,(h>>>1)&31,h&1,...Array.from({length:4},()=>random()&31)]);
  for(let pair=0;pair<3;pair++)for(let a=0;a<32;a++)for(let b=0;b<32;b++){
    const v=[random()&127,random()&31,random()&1,...Array.from({length:4},()=>random()&31)];v[3+pair]=a;v[4+pair]=b;check(sub,v);
  }
  for(let lane=0;lane<5;lane++)for(let value=0;value<256;value++)check(sub,null,[lane,value]);
}
for(let i=0;i<65536;i++)check(i&3);
assert.equal(cases,115712);
for(const row of timing)for(const k of ['before','after'])row[k].mean=row[k].total/row[k].calls;
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',asmEnabled:false,
  compiler:'AVR GCC 7.3.0 -Os -flto -mcall-prologues -mrelax -fwrapv; reader O2',
  binarySha256:createHash('sha256').update(binary).digest('hex'),casesPerImplementation:cases,
  fieldsPerImplementation:7*cases,fieldWidths:widths,all8192HeadersAtEachSubframe:true,
  allAdjacentIndexPairsAtEachSubframe:true,allByteValuesAtEachWindowPosition:true,
  randomCases:65536,exact:true,inputReadAddressesChecked:true,noReadsBeyond20BytePacket:true,
  fiveByteWindowsOnly:true,packetAndGuardsIntact:true,calleeSavedRegistersAtRet:true,
  zeroRegisterAtRet:true,previousGenericCursorExact:true,timing,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
