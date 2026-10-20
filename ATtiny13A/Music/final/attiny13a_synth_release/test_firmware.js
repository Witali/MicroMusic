#!/usr/bin/env node
/* Regression tests for the assembled HEX + 64-byte EEPROM, not JS sound synthesis. */
'use strict';
const fs=require('node:fs'), assert=require('node:assert/strict'), {AVRCore}=require('./avr_core.js');
const flashText=fs.readFileSync('synth.hex','utf8');
const eepromText=fs.readFileSync('eeprom.hex','utf8');
const rom=fs.readFileSync('synth.bin');const ep=fs.readFileSync('eeprom.bin');
assert.equal(rom.length,1024);assert.equal(ep.length,64);
function cpu(){return AVRCore.fromHex(flashText,eepromText)}
const fromHex=cpu();
assert.deepEqual(Buffer.from(fromHex.rom),rom);
assert.deepEqual(Buffer.from(fromHex.eeprom),ep);
for(let i=0;i<8;i++){
 const x=Array.from(ep.subarray(i*8,i*8+8)).flatMap(v=>[(v>>4)-8,(v&15)-8]);
 assert.equal(x.reduce((a,b)=>a+b,0),0);
}
let min=255,max=0,sum=0,worst=0,loss=0,changes=0,last=128;
const full=cpu(), s=14*37500;
for(let i=0;i<s;i++){
 const duty=full.nextDuty();min=Math.min(duty,min);max=Math.max(duty,max);sum+=duty;
 if(duty!==last)changes++;
 last=duty;
}
worst=full.maxIRQ;loss=full.lost;
assert.equal(loss,0,'Lost a Timer0 overflow');
assert.ok(worst<512,`ISR worst ${worst} >= 512 clocks`);
assert.equal(full.irqCount,s);
assert.ok(min>=64 && max<=191,`Sample clipping or extremely high duty ${min} .. ${max}`);
assert.ok(Math.abs(sum/s-128)<4,`Moving digital baseline ${sum/s}`);
assert.ok(changes>1000,'No useful waveform');
// Command parser test: point the existing score cursor to an injected F0|mask.
// The interpreter still executes exactly the AVR instructions, down to cycles.
function release(mask){
 const c=cpu();
 while(c.irqCount<30) c.step();
 while(c.inIRQ) c.step();
 c.r[1]=0x8f;c.r[19]=0x8f;c.r[20]=0x8f;c.r[21]=0;
 c.r[22]=1;c.r[15]=255;c.r[23]=255;
 c.r[30]=0xf0;c.r[31]=3;
 c.rom[0x3f0]=0xf0|mask;
 let steps=0, seen=false;
 while(steps++<1000){
  if(c.pc===0xe0/2){seen=true;break}
  c.step();
 }
 assert.ok(seen,'Injected note-off instruction did not run');
 return {regs:[c.r[1],c.r[19],c.r[20],c.r[21]],cycles:c.cyc};
}
const baseline=release(0).regs;
for(const [mask,index] of [[1,0],[2,1],[4,2],[8,3]]){
 const out=release(mask).regs;
 assert.notEqual(out[index],baseline[index],`Voice ${index}: no note-off`);
 for(let i=0;i<4;i++)if(i!==index)assert.equal(out[i],baseline[i],`Voice ${i} changed on note-off ${mask}`);
}
// Exercise compressed section transitions and explicit note-off events without
// needing to emulate the entire 3+ minute song in real time. This also checks
// worst-case instruction timing on every unique section.
const fast=cpu(), sections=new Set(), special=new Set();
while(fast.irqCount<2) fast.step();
let nEvents=0;
for(let k=0;k<950;k++){
 while(fast.inIRQ)fast.step();
 fast.r[15]=255;fast.r[23]=255;fast.r[22]=1;
 const goal=fast.irqCount+4;
 while(fast.irqCount<goal || fast.inIRQ){
  if(fast.pc===0xc0/2){
   const ptr=fast.r[30]|fast.r[31]<<8;
   const token=fast.rom[ptr];if(token>=240)special.add(token);
   nEvents++;
  }
  fast.step();
 }
 sections.add(fast.r[28]);
}
assert.equal(fast.lost,0,'Overflow lost in section stress pass');
assert.ok(fast.maxIRQ<512,'Heavy ISR exceeded two PWM periods');
for(let i=0;i<15;i++)assert.ok(sections.has(i),`No visit to playlist entry ${i}`);
for(const code of [0xf2,0xf4,0xf6,0xf8,0xff])assert.ok(special.has(code),`Missing control token ${code.toString(16)}`);
const msg={flash_bytes:rom.length,eeprom_bytes:ep.length,irqs:full.irqCount,seconds:14,max_isr_cycles:worst,
       lost_overflows:loss,duty_min:min,duty_max:max,duty_average:sum/s,duty_changes:changes,
       masks_tested:['F1','F2','F4','F8'],score_entries_checked:sections.size,score_events_checked:nEvents,stress_max_isr:fast.maxIRQ,status:'PASS'};
fs.writeFileSync('test-results.json',JSON.stringify(msg,null,2)+'\n');
console.log(JSON.stringify(msg,null,2));
