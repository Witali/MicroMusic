'use strict';
const fs=require('fs'),path=require('path');const {AVRCore}=require('./avr_emulator.js');
const info={chego:9216,otvechaesh:7936,vinni:22272};
const report={};
for(const [name,N] of Object.entries(info)){
 const a=new AVRCore(fs.readFileSync(path.join(name,'reference.bin')));
 const b=new AVRCore(fs.readFileSync(path.join(name,'firmware.bin')));
 let errors=0,first=-1;
 const sound=Buffer.alloc(N);
 for(let i=0;i<N;i++){
  const x=a.takeSample(),y=b.takeSample();sound[i]=y;
  if(x!==y){errors++;if(first<0)first=i}
 }
 const row={samples:N,pcmMismatch:errors,firstMismatch:first,
    flashOriginal:fs.statSync(path.join(name,'reference.bin')).size,
    flashOptimized:fs.statSync(path.join(name,'firmware.bin')).size,
    irqsOriginal:a.irqCount,irqsOptimized:b.irqCount,
    missedOriginal:a.missedOverflows,missedOptimized:b.missedOverflows,
    maxIsrCyclesOriginal:a.maxISR,maxIsrCyclesOptimized:b.maxISR,
    peakStackOriginal:a.maxStack,peakStackOptimized:b.maxStack,
    format:'8-bit unsigned PWM duty; 7500 output samples/second'};
 console.log(name,JSON.stringify(row));report[name]=row;
 fs.writeFileSync(path.join(name,'emulated.pcm'),sound);
 if(errors||a.missedOverflows||b.missedOverflows||a.irqCount!==b.irqCount) process.exitCode=1;
}
fs.writeFileSync('report.json',JSON.stringify(report,null,2)+'\n');
