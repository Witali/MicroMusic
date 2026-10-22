'use strict';
const fs=require('fs');const {AVRCore}=require('./avr_emulator.js');
const root=__dirname+'/synthetic/';
const rom=fs.readFileSync(root+'firmware.bin'),expected=fs.readFileSync(root+'expected_pcm.raw');
const core=new AVRCore(rom);let errors=0;
for(let i=0;i<expected.length;i++)errors+=core.takeSample()!==expected[i]?1:0;
const passed=errors===0&&core.missedOverflows===0;
console.log({passed,errors,missedOverflows:core.missedOverflows,samples:expected.length,maxISR:core.maxISR});
if(!passed)process.exit(1);
