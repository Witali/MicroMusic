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
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',
  multiplyCases:count,exact:true,zeroRegisterRestored:true,minMailboxCycles:minCycles,maxMailboxCycles:maxCycles,
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
