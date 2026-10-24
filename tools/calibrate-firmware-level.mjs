// Measure every emitted PWM code of the exact calibration firmware, without resampling.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-core.js';
const folder=process.argv[2],seconds=Number(process.argv[3]);
if(!folder||!(seconds>0&&seconds<=300))throw Error('Usage: node calibrate-firmware-level.mjs folder seconds');
const rom=fs.readFileSync(path.join(folder,'synth.bin')),ep=fs.readFileSync(path.join(folder,'eeprom.bin'));
const core=new AVRCore(rom,ep);let minimum=128,maximum=128,samples=0;
while(core.cyc<seconds*9600000){const value=core.nextDuty();minimum=Math.min(minimum,value);maximum=Math.max(maximum,value);samples++;}
if(core.lost||core.workLost)throw Error('Calibration firmware lost timer events');
minimum-=128;maximum-=128;
if(minimum>=0||maximum<=0)throw Error('Calibration needs a non-silent bipolar waveform');
const gain=Math.min(128/-minimum,127/maximum);
const table=Array.from({length:maximum-minimum+1},(_,i)=>Math.round(128+(minimum+i)*gain));
if(table.some(v=>v<0||v>255)||table[-minimum]!==128)throw Error('Invalid normalization table');
console.log(JSON.stringify({minimum,maximum,gain,gainDb:20*Math.log10(gain),table,seconds,samples,
 calibrationFlashSha256:createHash('sha256').update(rom).digest('hex'),
 method:'Linear peak normalization around PWM 128; common gain for both parts; nearest integer output; no limiter or automatic gain changes.'}));
