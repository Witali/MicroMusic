'use strict';
const fs=require('fs');const path=require('path');const {AVRCore}=require('./avr_emulator.js');
const root=__dirname, metrics=JSON.parse(fs.readFileSync(path.join(root,'metrics.json'),'utf8'));
let fail=false;
for(let name of ['chego','otvechaesh','vinni']){
 const folder=path.join(root,'results',name);
 const rom=fs.readFileSync(path.join(folder,'firmware.bin'));
 const wanted=fs.readFileSync(path.join(folder,'expected.raw'));
 const core=new AVRCore(rom);
 let diff=0;
 for(let i=0;i<wanted.length;i++){
  let x=core.takeSample();if(x!==wanted[i])diff++;
 }
 let result={samples:wanted.length,mismatch:diff,overflowMisses:core.missedOverflows,interrupts:core.irqCount,
             maxISR:core.maxISR,flashBytes:rom.length,pwmWrites:core.pwmWrites,stackMax:core.maxStack};
 console.log(name,JSON.stringify(result));
 if(diff||core.missedOverflows||rom.length>1024||core.irqCount<wanted.length)fail=true;
 metrics[name].avr=result;
}
fs.writeFileSync(path.join(root,'metrics.json'),JSON.stringify(metrics,null,2));
if(fail){process.exitCode=1;console.error('FAIL: AVR output mismatch or overflow')}
