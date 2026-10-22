/** Repeatable instruction-level validation of actual assembled ATtiny13A firmware. */
'use strict';
const fs=require('fs');
const path=require('path');
const {AVRCore}=require('./release/avr_emulator.js');
const root=path.join(__dirname,'release');
const report={};let failures=0;
for(const phrase of ['chego','otvechaesh','vinni']){
 for(const version of ['hq3','stoi','timbre']){
  const d=path.join(root,phrase,version);
  const binary=fs.readFileSync(path.join(d,'firmware.bin'));
  const target=fs.readFileSync(path.join(d,'pcm.u8'));
  const core=new AVRCore(binary);
  let diff=0,late=0,first=null,last=null;
  let prevIRQ=0;
  for(let i=0;i<target.length;i++){
   let v=core.takeSample();
   if(v!==target[i]){diff++;if(first===null)first=[i,v,target[i]];last=[i,v,target[i]];}
   let delta=core.irqCount-prevIRQ;
   if(i>0&&(delta<4||delta>6))late++;
   prevIRQ=core.irqCount;
  }
  const r={pcm_samples:target.length,pcm_mismatches:diff,first_mismatch:first,last_mismatch:last,timer_irq:core.irqCount,missed_overflows:core.missedOverflows,non5_irq_intervals:late,max_isr_cycles:core.maxISR,max_stack:core.maxStack};
  report[phrase+'_'+version]=r;
  console.log(phrase,version,JSON.stringify(r));
  if(diff||core.missedOverflows||late||core.maxStack>64)failures++;
 }
}
fs.writeFileSync(path.join(root,'verification.json'),JSON.stringify(report,null,2));
process.exitCode=failures?1:0;
