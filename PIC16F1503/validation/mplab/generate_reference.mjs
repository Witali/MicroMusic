import fs from 'node:fs';
import {PIC16F1503,readPIC16Hex} from './pic16-core.mjs';
const program = readPIC16Hex(fs.readFileSync('./micromusic_with_config.hex','utf8'));
const emu = new PIC16F1503(program);
const cps = [1,2,3,4,5,8,12,24,50,100,256,1024,4096];
const names = {PCL:()=>emu.PC&255,WREG:()=>emu.W,STATUS:()=>emu.mem[3],BSR:()=>emu.bsr,
 FSR0L:()=>emu.mem[4],FSR0H:()=>emu.mem[5],OSCCON:()=>emu.mem[0x099],
 PIR1:()=>emu.mem[0x011],PIE1:()=>emu.mem[0x091],INTCON:()=>emu.mem[0x00b],
 TMR2:()=>emu.mem[0x01a],PR2:()=>emu.mem[0x01b],T2CON:()=>emu.mem[0x01c],
 PWM3DCH:()=>emu.mem[0x618],PWM3DCL:()=>emu.mem[0x617],PWM3CON:()=>emu.mem[0x619]};
const snapshots=[];
let n=0;
for(const target of cps){while(n<target){emu.step();n++;}
 const registers=Object.fromEntries(Object.entries(names).map(([k,v])=>[k,v()]));
 snapshots.push({instructionCount:n,programCounter:emu.PC,machineCycles:emu.cycle,timeSeconds:emu.seconds,
   irqCount:emu.irqCount,pwmPeriods:emu.pwmPeriodCount,registers});}
fs.writeFileSync('reference_our_emulator.json',JSON.stringify({source:'Local JavaScript emulator, NOT Microchip MPLAB SIM',
 inputHex:'micromusic_with_config.hex',checkpoints:snapshots},null,2)+'\n');
console.log(snapshots.map(s=>`step=${s.instructionCount} PC=${s.programCounter.toString(16).padStart(3,'0')} cycles=${s.machineCycles} OSCCON=${s.registers.OSCCON.toString(16)} TMR2=${s.registers.TMR2}`).join('\n'));
