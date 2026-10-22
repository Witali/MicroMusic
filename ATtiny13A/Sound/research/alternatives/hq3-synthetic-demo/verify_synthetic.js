const fs=require('fs'),{AVRCore}=require('./avr_emulator');
let c=new AVRCore(fs.readFileSync('firmware.bin'));
for(let i=0;i<54*64;i++)c.takeSample();
console.log('PCM 3456 samples, ISR',c.irqCount,'missed Timer0',c.missedOverflows,'max ISR',c.maxISR);
if(c.missedOverflows)process.exitCode=1;
