#!/usr/bin/env node
'use strict';
// Independently execute the actual Intel-HEX-derived AVR machine image,
// checking its PWM output against the bit-exact C training decoder.
const fs = require('fs'),path=require('path');
const {AVRCore}=require('./avr_emulator.js');
const root=process.argv[2]||'outputs';
const cases=process.argv.slice(3).length?process.argv.slice(3):['chego','otvechaesh','vinni'];
for(const name of cases){
  const dir=path.resolve(root,name);
  const image=fs.readFileSync(path.join(dir,'firmware.bin'));
  const expected=fs.readFileSync(path.join(dir,'expected_pcm.raw'));
  const cpu=new AVRCore(image);
  let diffs=0,examples=[];
  for(let i=0;i<expected.length;i++){
    const got=cpu.takeSample();if(got!==expected[i]){diffs++;if(examples.length<5)examples.push([i,got,expected[i]])}
  }
  const result={voice:name,flash_bytes:image.length,pcm_samples:expected.length,mismatches:diffs,
    missed_timer_overflows:cpu.missedOverflows,max_isr_cycles:cpu.maxISR,irq_count:cpu.irqCount,sample_examples:examples};
  console.log(JSON.stringify(result));
  if(diffs||cpu.missedOverflows||image.length>1024)process.exitCode=1;
}
