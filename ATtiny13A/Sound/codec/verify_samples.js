const fs=require('fs'),path=require('path');
const {AVRCore}=require('./avr_emulator.js');
const cases={chego:9216,otvechaesh:7936,vinni:22272};
for (let [name,N] of Object.entries(cases)) {
 let root=path.join(__dirname,name);
 let a=new AVRCore(fs.readFileSync(path.join(root,'reference_410.bin')));
 let b=new AVRCore(fs.readFileSync(path.join(root,'firmware.bin')));
 let mismatch=0;for(let i=0;i<N;i++)if(a.takeSample()!=b.takeSample())mismatch++;
 console.log(name,JSON.stringify({samples:N,diffs:mismatch,irqA:a.irqCount,irqB:b.irqCount,missedA:a.missedOverflows,missedB:b.missedOverflows,maxISR:b.maxISR}));
 if(mismatch||a.missedOverflows||b.missedOverflows||a.irqCount!==b.irqCount)process.exitCode=1;
}
