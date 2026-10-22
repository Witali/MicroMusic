import fs from 'node:fs';
import {PIC16F1503,readPIC16Hex} from '../web/pic16-core.mjs';
const root = new URL('../',import.meta.url);
const hex=fs.readFileSync(new URL('firmware/micromusic.hex',root),'utf8');
const pic=new PIC16F1503(readPIC16Hex(hex));
let snap=0, vals=[];
const STOP=12500*2*5;
for(let n=0;n<4e6;n++){
  pic.step();
  if(pic.samples.length>=STOP)break;
  if(pic.samples.length>=snap+5){snap=pic.samples.length;vals.push(pic.samples[snap-1]);}
}
const min=Math.min(...vals),max=Math.max(...vals),avg=vals.reduce((a,b)=>a+b,0)/vals.length;
const report={pwmSamples:pic.samples.length,outputSamples:vals.length,irqCount:pic.irqCount,
  machineCycles:pic.cycle, instructions:pic.totalInstructions, mean:avg,min,max,
  first32:vals.slice(0,32),scoreOffset:pic.mem[0x3D],section:pic.mem[0x3E],readIdx:pic.mem[0x44],writeIdx:pic.mem[0x45],
  noteSteps:[pic.mem[0x22]+256*pic.mem[0x23],pic.mem[0x2A]+256*pic.mem[0x2B],pic.mem[0x32]+256*pic.mem[0x33]],
  timer:pic.mem[0x1c],pwmControl:pic.mem[0x619],pr2:pic.mem[0x1b],underruns:pic.mem[0x60],unusedQueueDelta:((pic.mem[0x45]-pic.mem[0x44])&15)};
fs.writeFileSync(new URL('reports/emulator_smoke.json',root),JSON.stringify(report,null,2)+'\n');
console.log(report);
