#!/usr/bin/env node
/* Render audio entirely by interpreting the exact ROM and EEPROM in AVRCore. */
'use strict';
const fs=require('node:fs');const {AVRCore}=require('./avr_core.js');
const seconds=Math.min(60,Math.max(1,Number(process.argv[2]||14)));
const samplerate=48000, cpu=AVRCore.fromHex(fs.readFileSync('synth.hex','utf8'),fs.readFileSync('eeprom.hex','utf8'));
const len=seconds*samplerate;const pcm=Buffer.alloc(44+2*len);let v0=cpu.nextDuty(),v1=cpu.nextDuty(),phase=0;
let hpPrevX=0,hpPrevY=0,lpPrevY=0,maxAmplitude=0;
const dt=1/samplerate,highFreq=35,lowFreq=9000;
const aHP=(1/(2*Math.PI*highFreq))/(1/(2*Math.PI*highFreq)+dt),aLP=dt/(dt+1/(2*Math.PI*lowFreq));
let ptr=44;
for(let i=0;i<len;i++){
 let raw=(v0+(v1-v0)*phase-128)/128;
 phase+=37500/samplerate;
 if(phase>=1){phase-=1;v0=v1;v1=cpu.nextDuty()}
 const hp=aHP*(hpPrevY+raw-hpPrevX);hpPrevX=raw;hpPrevY=hp;
 const lp=lpPrevY+aLP*(hp-lpPrevY);lpPrevY=lp;
 let sample=Math.max(-1,Math.min(1,lp*1.15));maxAmplitude=Math.max(maxAmplitude,Math.abs(sample));
 pcm.writeInt16LE(Math.round(sample*32767),ptr);ptr+=2;
}
// PCM WAVE RIFF header.
pcm.write('RIFF',0);pcm.writeUInt32LE(pcm.length-8,4);pcm.write('WAVE',8);
pcm.write('fmt ',12);pcm.writeUInt32LE(16,16);pcm.writeUInt16LE(1,20);pcm.writeUInt16LE(1,22);
pcm.writeUInt32LE(samplerate,24);pcm.writeUInt32LE(samplerate*2,28);pcm.writeUInt16LE(2,32);pcm.writeUInt16LE(16,34);
pcm.write('data',36);pcm.writeUInt32LE(len*2,40);
fs.writeFileSync('preview.wav',pcm);
console.log(`Rendered ${seconds}s from AVR machine code / EEPROM at ${samplerate}Hz; peak ${maxAmplitude.toFixed(3)}, lost Timer0 overflows: ${cpu.lost}, worst ISR ${cpu.maxIRQ}`);
if(cpu.lost || cpu.maxIRQ>=512)process.exitCode=1;
