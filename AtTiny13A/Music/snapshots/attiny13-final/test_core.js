const fs=require('fs'); const {AVRCore}=require('./avr_core.js');
const core=new AVRCore(new Uint8Array(fs.readFileSync('./synth.bin')),new Uint8Array(fs.readFileSync('./eeprom.bin')));
const start=Date.now();
let n=+process.argv[2]||37500, min=255,max=0, sum=0, means=[];
for(let i=0;i<n;i++){
 const v=core.nextDuty();min=Math.min(min,v);max=Math.max(max,v);sum+=v;
 if((i+1)%3750===0){ means.push({t:(i+1)/37500,mean:sum/(i+1),irq:core.irqCount,maxISR:core.maxIRQ,lost:core.lost}); }
}
console.log({s:n/37500,cyc:core.cyc,irq:core.irqCount,lost:core.lost,maxISR:core.maxIRQ,range:[min,max],mean:sum/n,spentMs:Date.now()-start,means:means.slice(0,5),end:means.slice(-3),peakInfo:core.peakInfo});
