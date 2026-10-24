// Independent AVR machine-code QMF PCM/timing check against upstream C.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/qmf');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const rows=[];
for(const n of [320,640]){
  const program=new Uint16Array(16384).fill(0xffff);
  new Uint8Array(program.buffer).set(readFileSync(join(build,'qmf.bin')));
  const cpu=new CPU(program,2048),pcm=address('qmf_pcm'),status=address('qmf_status'),command=address('qmf_command');
  const end=address('__bss_end');
  let minSP=0x8ff;
  function until(predicate){const deadline=cpu.cycles+10000000;while(!predicate()){
    assert.ok(cpu.cycles<deadline,'QMF timeout');avrInstruction(cpu);cpu.tick();
    minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
  }}
  until(()=>cpu.data[status]===1);
  cpu.dataView.setUint16(address('qmf_size'),n,true);
  let seed=0x12345678;
  const input=Buffer.alloc(16*n*2);
  for(let i=0;i<16*n;i++){
    seed=(Math.imul(seed,1664525)+1013904223)>>>0;
    // Exercise the entire s16 range, including both signs and clipping.
    input.writeInt16LE((seed>>>16)-32768,2*i);
  }
  for(let f=0;f<5;f++) for(let i=0;i<n;i++){
    const low=i<n/2;
    const v=f===0?0:f===1?32767:f===2?-32768:f===3?(low?32767:-32768):(low?-32768:32767);
    input.writeInt16LE(v,(f*n+i)*2);
  }
  writeFileSync(join(build,'input.pcm'),input);
  execFileSync(join(build,'oracle.exe'),[String(n),join(build,'input.pcm'),join(build,'oracle.pcm')]);
  const expected=readFileSync(join(build,'oracle.pcm')),cycles=[];
  for(let f=0;f<16;f++){
    cpu.data.set(input.subarray(f*n*2,(f+1)*n*2),pcm);
    cpu.data[status]=1;cpu.data[command]=1;
    until(()=>cpu.data[status]===2);const start=cpu.cycles;
    until(()=>cpu.data[status]===3);
    cycles.push(cpu.cycles-start);
    assert.ok(Buffer.from(cpu.data.subarray(pcm,pcm+n*2)).equals(expected.subarray(f*n*2,(f+1)*n*2)),`PCM n=${n}, frame=${f}`);
  }
  rows.push({outputHz:n*50,frames:16,pcmExact:true,minCycles:Math.min(...cycles),maxCycles:Math.max(...cycles),
    frameBudgetCycles:320000,fitsQmfAlone:Math.max(...cycles)<=320000,staticSramBytes:end-0x100,
    peakStackBytes:0x8ff-minSP,freeSramAtPeak:minSP-end+1,
    qmfHistoryBytes:128,eliminatedTemporaryBytes:2*(n/2+32)*2,historySavedBytes:128});
}
const report={scope:'Isolated QMF synthesis only; excludes NB/HB decoding, packet reads, output and interrupts',
  mcu:'ATmega328P',cpuHz:16000000,compiler:'AVR GCC 7.3.0 -O3 -flto',physicalBoardTested:false,streams:rows};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
