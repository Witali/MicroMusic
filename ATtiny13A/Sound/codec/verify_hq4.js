'use strict';
const fs=require('fs'),path=require('path');
const {AVRCore}=require('./avr_emulator.js');
const names=['chego','otvechaesh','vinni'];let result={};
for(const name of names){
  const base=path.join(__dirname,name);
  let program=fs.readFileSync(path.join(base,'firmware.bin'));
  let expected=fs.readFileSync(path.join(base,'expected.raw'));
  const core=new AVRCore(program);let mismatch=0;let firstMismatch=-1;
  for(let j=0;j<expected.length;j++){
    let got=core.takeSample();
    if(got!==expected[j]){mismatch++;if(firstMismatch<0)firstMismatch=j;}
  }
  let valid={samples:expected.length,mismatches:mismatch,first_mismatch:firstMismatch,
    timer_misses:core.missedOverflows,irq_count:core.irqCount,max_isr:core.maxISR};
  if(mismatch||core.missedOverflows||core.irqCount!==expected.length*5)process.exitCode=1;
  result[name]=valid;
  console.log(name,JSON.stringify(valid));
}
console.log('AUDIT_JSON='+JSON.stringify(result));
