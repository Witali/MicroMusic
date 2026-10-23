import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/math');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(readFileSync(join(build,'math.bin')));
const cpu=new CPU(program,2048),status=address('math_status'),command=address('math_command');
const a=address('math_a'),b=address('math_b'),result=address('math_result'),zero=address('math_zero');
const value=address('math_value');
function until(predicate){const end=cpu.cycles+10000;while(!predicate()){
  assert.ok(cpu.cycles<end,'Arithmetic mailbox timeout');avrInstruction(cpu);cpu.tick();
}}
until(()=>cpu.data[status]===1);
let count=0,minCycles=Infinity,maxCycles=0;
for(const rhs of [0,1,-1,32767,-32768,0x1234,-5678])for(let lhs=-32768;lhs<=32767;lhs++){
  cpu.dataView.setInt16(a,lhs,true);cpu.dataView.setInt16(b,rhs,true);
  cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;
  until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt32(result,true),(lhs*rhs)|0,`multiply ${lhs} * ${rhs}`);
  assert.equal(cpu.data[zero],0,'GCC zero-register contract');
  const cycles=cpu.cycles-before;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);count++;
}
let shiftCases=0,seed=0x31415926;
const edges=[-2147483648,2147483647,-1,0,1,4095,4096,-4096,-4097,8191,8192,-8192,-8193,
  16383,16384,-16384,-16385,32767,32768,-32768,-32769,65535,65536,-65536,-65537];
for(const commandValue of [13,14,15,114,115])for(let i=0;i<131072+edges.length;i++){
  const shift=commandValue>100?commandValue-100:commandValue;
  seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;
  // Exhaust all sign-extended s16 values, plus
  // independent full-width random operands. This catches byte boundaries.
  const v=i>=131072?edges[i-131072]:i<65536?(i&0x8000?i|0xffff0000:i):seed;
  cpu.dataView.setInt32(value,v,true);cpu.data[status]=1;cpu.data[command]=commandValue;
  until(()=>cpu.data[status]===2);
  const expected=commandValue>100?((v>>shift)<<16)>>16:v>>shift;
  assert.equal(cpu.dataView.getInt32(result,true),expected,`shift ${v} >> ${shift}, output ${commandValue>100?16:32} bits`);
  assert.equal(cpu.data[zero],0,'GCC zero-register contract after shift');shiftCases++;
}
let q14Cases=0,q14BoundedCases=0,q14CCases=0;
function q14(lhs,rhs){
  cpu.dataView.setInt16(a,lhs,true);cpu.dataView.setInt32(value,rhs,true);
  cpu.data[status]=1;cpu.data[command]=100;until(()=>cpu.data[status]===2);
  const high=(rhs>>14)<<16>>16;
  const expected=lhs*high+((lhs*(rhs&16383))>>14);
  assert.equal(cpu.dataView.getInt32(result,true),expected,`Q14 ${lhs}, ${rhs}`);
  assert.equal(cpu.data[zero],0,'GCC zero-register contract after Q14');q14Cases++;
  cpu.dataView.setInt32(value,(rhs<<2)>>2,true);
  cpu.data[status]=1;cpu.data[command]=101;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt32(result,true),expected,'Bounded signed30 Q14');
  assert.equal(cpu.data[zero],0,'GCC zero register after bounded Q14');q14BoundedCases++;
  cpu.dataView.setInt32(value,rhs,true);
  cpu.data[status]=1;cpu.data[command]=102;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt32(result,true),expected,'Portable C generic Q14');
  assert.equal(cpu.data[zero],0,'GCC zero register after C Q14');q14CCases++;
}
for(const rhs of [0,1,-1,16383,16384,536870911,536870912,1073741823,-2147483648,2147483647,0x12345678,-0x12345678])
  for(let lhs=-32768;lhs<=32767;lhs++)q14(lhs,rhs);
for(let i=0;i<131072;i++){
  seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;const lhs=seed<<16>>16;
  seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;q14(lhs,seed);
}
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',
  multiplyCases:count,shiftCases,q14Cases,q14BoundedCases,q14CCases,exact:true,zeroRegisterRestored:true,minMailboxCycles:minCycles,maxMailboxCycles:maxCycles,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
