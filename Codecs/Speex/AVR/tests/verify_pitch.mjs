// Independent exact product/MAC oracle for all signed8 gains, including values
// outside the NB3 table subset. Check empty/write/add and all short vector ends.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/pitch-math');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(readFileSync(join(build,'pitch.bin')));
const cpu=new CPU(program,2048),status=address('pitch_status'),command=address('pitch_command');
const input=address('pitch_input'),output=address('pitch_output'),zero=address('pitch_zero');
function until(predicate){const end=cpu.cycles+10000;while(!predicate()){
  assert.ok(cpu.cycles<end,'Pitch mailbox timeout');avrInstruction(cpu);cpu.tick();
}}
let seed=0x587bc921;
function next(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
const edges=[-32768,-32767,-256,-255,-129,-128,-127,-1,0,1,127,128,129,255,256,32766,32767];
const sums=[-8388608,-8388607,-2048000,-1,0,1,2048000,8388606,8388607];
function wrap24(value){return (value<<8)>>8;}
function write24(address,value){for(let i=0;i<3;i++)cpu.data[address+i]=(value>>>(8*i))&255;}
function read24(address){return wrap24(cpu.data[address]|(cpu.data[address+1]<<8)|(cpu.data[address+2]<<16));}
until(()=>cpu.data[status]===1);
let cases=0,checked=0,minCycles=Infinity,maxCycles=0;
for(let gain=-128;gain<=127;gain++)for(const add of [0,1,2,255])for(let vector=0;vector<48;vector++){
  const count=Math.min(vector,40);
  assert.ok(count<=40);
  cpu.dataView.setInt8(address('pitch_gain'),gain);
  cpu.data[address('pitch_count')]=count;cpu.data[address('pitch_accumulate')]=add;
  const expected=[];
  for(let i=0;i<40;i++){
    const value=i<edges.length?edges[i]:(next()<<16)>>16;
    const initial=i<sums.length?sums[i]:wrap24(next());
    cpu.dataView.setInt16(input+2*i,value,true);write24(output+3*i,initial);
    expected.push(i<count?wrap24(gain*value+(add?initial:0)):initial);
  }
  cpu.data.set([137,74,225,58],output+120);
  cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;
  until(()=>cpu.data[status]===2);
  for(let i=0;i<40;i++)assert.equal(read24(output+3*i),expected[i],`gain ${gain}, add ${add}, count ${count}, sample ${i}`);
  assert.deepEqual([...cpu.data.subarray(output+120,output+124)],[137,74,225,58],'Packed output canary');
  assert.equal(cpu.data[zero],0,'GCC zero register');
  const cycles=cpu.cycles-before;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
  checked+=40;cases++;
}
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',
  gains:256,gainUnscaledMin:-128,gainUnscaledMax:127,vectors:cases,samplesChecked:checked,
  outputFormat:'signed24le unscaled, modulo24 accumulation',
  counts:[0,40],everyCountVerified:true,
  accumulateFlags:[0,1,2,255],
  exact:true,emptyAndZeroPaths:true,tailSentinelsIntact:true,zeroRegisterRestored:true,
  minMailboxCycles:minCycles,maxMailboxCycles:maxCycles,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
