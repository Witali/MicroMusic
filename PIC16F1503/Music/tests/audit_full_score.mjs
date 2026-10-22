import fs from 'node:fs';
import {PIC16F1503,readPIC16Hex} from '../web/pic16-core.mjs';
const root=new URL('../',import.meta.url);
const words=readPIC16Hex(fs.readFileSync(new URL('firmware/micromusic_with_config.hex',root),'utf8'));
const l=JSON.parse(fs.readFileSync(new URL('reports/assembly.json',root))).sections;
const cpu=new PIC16F1503(words);
const start=Date.now(),seconds=230,target=4e6*seconds;
const unique=new Set([0]);let edges=[],old=0,wrap=-1,maxStack=0,off=0,events=0,irq=0,nextLog=120e6,overrun=0;
while(cpu.cycle<target){
  if(cpu.PC===l.event_note_off)off++;
  if(cpu.PC===l.read_event)events++;
  cpu.step();
  maxStack=Math.max(maxStack,cpu.stack.length);
  const sec=cpu.mem[0x3e];
  if(sec!==old){if(sec===0 && (old===14 || old===15) && wrap<0)wrap=cpu.cycle/4e6;
    unique.add(sec);edges.push([+(cpu.cycle/4e6).toFixed(2),old,sec]);old=sec;}
  if(cpu.mem[0x60]!==0){throw Error(`Queue underrun at ${cpu.cycle/4e6}s: ${cpu.mem[0x60]}`)}
  if(cpu.samples.length>2000)cpu.samples.length=0;
  if(cpu.cycle>=nextLog){console.log('audited',Math.floor(cpu.cycle/4e6),'sec; sections',unique.size,'noteOff',off,'maxStack',maxStack);
    nextLog+=120e6;}
}
const report={simulatedSeconds:cpu.cycle/4e6,wallSeconds:(Date.now()-start)/1000,sectionsVisited:[...unique].filter(x=>x<15).sort((a,b)=>a-b),
  transientSectionValue15Seen:unique.has(15),
  sectionTransitions:edges,firstFullPlaylistWrapSec:wrap,processedEvents:events,noteOffCommands:off,
  interrupts:cpu.irqCount,underruns:cpu.mem[0x60],maxHardwareStackDepth:maxStack,scoreOffset:cpu.mem[0x3d]};
fs.writeFileSync(new URL('reports/full_score_audit.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
