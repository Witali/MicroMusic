const fs=require('fs'),path=require('path');
const {AVRCore}=require(path.join(__dirname,'avr_emulator.js'));
const root=path.join(__dirname,'baseline');
const alt=__dirname;
const cases={chego:9216,otvechaesh:7936,vinni:22272};
for(let [name,N] of Object.entries(cases)){
 let a=new AVRCore(fs.readFileSync(path.join(root,name,'firmware.bin')));
 let b=new AVRCore(fs.readFileSync(path.join(alt,name,'firmware.bin')));
 let diffs=0,first=-1,maxDelta=0;
 for(let i=0;i<N;i++){
  const av=a.takeSample(),bv=b.takeSample();
  const d=Math.abs(av-bv); if(d){diffs++;if(first<0)first=i;maxDelta=Math.max(maxDelta,d)}
 }
 let c={name,N,diffs,first,maxDelta,original:{irq:a.irqCount,miss:a.missedOverflows,maxISR:a.maxISR,cycles:a.cycles},optimized:{irq:b.irqCount,miss:b.missedOverflows,maxISR:b.maxISR,cycles:b.cycles}};
 console.log(JSON.stringify(c));
 if(diffs||a.missedOverflows||b.missedOverflows)process.exitCode=1;
}
