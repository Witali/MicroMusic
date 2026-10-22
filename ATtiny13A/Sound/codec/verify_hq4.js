'use strict';
const fs=require('fs'),path=require('path');const{AVRCore}=require('./avr_emulator.js');
let failures=0;
for(const name of ['chego','otvechaesh','vinni']){
 const dir=path.join(__dirname,'HQ4',name);const bin=fs.readFileSync(path.join(dir,'firmware.bin'));const exp=fs.readFileSync(path.join(dir,'expected_pcm.raw'));
 const core=new AVRCore(bin);let diffs=0;let late=0;let prev=0;const pcm=Buffer.alloc(exp.length);
 for(let j=0;j<exp.length;j++){
  const v=core.takeSample();pcm[j]=v;
  if(v!==exp[j])diffs++;
  if(j&&core.cycles-prev>1300)late++;
  prev=core.cycles;
 }
 fs.writeFileSync(path.join(dir,'verified_pcm.raw'),pcm);
 const res={samples:exp.length,differences:diffs,missed_timer:core.missedOverflows,late_samples:late,flash_bytes:bin.length};
 console.log(name,res);if(diffs||late||core.missedOverflows||bin.length>1024)failures++;
}
if(failures)process.exit(1);
