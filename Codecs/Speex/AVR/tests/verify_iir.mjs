import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/iir');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(readFileSync(join(build,'iir.bin')));
const cpu=new CPU(program,2048),status=address('iir_status'),command=address('iir_command');
const samples=address('iir_samples'),coef=address('iir_coef'),zero=address('iir_zero');
function until(predicate){const end=cpu.cycles+30000;while(!predicate()){
  assert.ok(cpu.cycles<end,'LPC mailbox timeout');avrInstruction(cpu);cpu.tick();
}}
let seed=0x8b271e4d;
function next(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
const mem=new Int32Array(10),den=new Int16Array(10),expected=new Int16Array(40);
until(()=>cpu.data[status]===1);
let minCycles=Infinity,maxCycles=0,clipped=0,wraps=0;
for(let block=0;block<4096;block++){
  for(let j=0;j<10;j++){
    den[j]=block%3?next():next()%1001-500;
    cpu.dataView.setInt16(coef+2*j,den[j],true);
  }
  for(let i=0;i<40;i++){
    const input=(next()<<16)>>16;
    cpu.dataView.setInt16(samples+2*i,input,true);
    const raw=input+(((mem[0]+4096)|0)>>13),y=Math.max(-32767,Math.min(32767,raw));
    clipped+=y!==raw;expected[i]=y;
    for(let j=0;j<9;j++){
      const value=mem[j+1]-den[j]*y;mem[j]=value;
      wraps+=value!==mem[j];
    }
    mem[9]=-den[9]*y;
  }
  cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;
  until(()=>cpu.data[status]===2);
  for(let i=0;i<40;i++)assert.equal(cpu.dataView.getInt16(samples+2*i,true),expected[i],`block ${block}, sample ${i}`);
  assert.equal(cpu.data[zero],0,'GCC zero register');
  const cycles=cpu.cycles-before;minCycles=Math.min(minCycles,cycles);maxCycles=Math.max(maxCycles,cycles);
}
assert.ok(clipped>10000&&wraps>1000,'Exercise saturation and overflow');
const report={mcu:'ATmega328P',simulator:'avr8js 0.21.1',compiler:'AVR GCC 7.3.0 -O3 -flto -fwrapv',
  blocks:4096,samples:4096*40,clipped,wraps,exact:true,inPlace:true,zeroRegisterRestored:true,
  minMailboxCycles:minCycles,maxMailboxCycles:maxCycles,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
