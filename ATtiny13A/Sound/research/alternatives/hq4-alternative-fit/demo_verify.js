'use strict';
const fs=require('fs'),path=require('path');const {AVRCore}=require('./avr_emulator.js');
const d=path.join(__dirname,'synthetic_demo');
const b=fs.readFileSync(path.join(d,'firmware.bin')),samples=fs.readFileSync(path.join(d,'expected.raw'));
const m=new AVRCore(b);let diffs=0;
for(let j=0;j<samples.length;j++)if(m.takeSample()!==samples[j])diffs++;
console.log('Demo',JSON.stringify({flash:b.length,pcm:samples.length,diffs,missed:m.missedOverflows,irq:m.irqCount}));
if(diffs||m.missedOverflows)process.exitCode=1;
