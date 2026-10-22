import fs from 'node:fs';
import {PIC16F1503,readPIC16Hex} from '../web/pic16-core.mjs';
const root=new URL('../',import.meta.url);
const words=readPIC16Hex(fs.readFileSync(new URL('firmware/micromusic_with_config.hex',root),'utf8'));
const cpu=new PIC16F1503(words);
const seconds=Number(process.argv[2]||14),sampleRate=12500,pwmRate=62500,target=Math.ceil(seconds*pwmRate);
const audio=new Uint8Array(Math.ceil(seconds*sampleRate));
let outCount=0,queueMin=15,queueMax=0,noteoffs=0,sectionChanges=0,flags=0,samplesAt=0,recordedMs=[];
const readEventPc=Number(JSON.parse(fs.readFileSync(new URL('reports/assembly.json',root))).sections.read_event);
let lastSection=0;
const start=performance.now();
const chunk=7500000;let j=0;
while(cpu.samples.length<target){
  const old=cpu.samples.length;
  for(let i=0;i<chunk && cpu.samples.length<target;i++){
    const pc=cpu.PC;
    if(pc===readEventPc)flags++;
    cpu.step();
    if(cpu.mem[0x3E]!==lastSection){sectionChanges++;lastSection=cpu.mem[0x3E];}
    if(cpu.samples.length>samplesAt){
      samplesAt=cpu.samples.length;
      if(samplesAt%5===0 && outCount<audio.length)audio[outCount++]=cpu.samples[samplesAt-1];
    }
  }
  j++;
  console.log(`render ${cpu.samples.length}/${target} PWM periods, underruns ${cpu.mem[0x60]}, sections ${sectionChanges}`);
  if(j>30)throw Error('Long run unexpectedly slow or stuck');
}
function wave16(v){
  const b=Buffer.alloc(44+v.length*2);
  b.write('RIFF',0);b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);
  b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(sampleRate,24);b.writeUInt32LE(sampleRate*2,28);
  b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(v.length*2,40);
  for(let i=0;i<v.length;i++)b.writeInt16LE((v[i]-128)*256,44+i*2);
  return b;
}
const produced=audio.subarray(0,outCount);
fs.writeFileSync(new URL('reference/preview_pic16_asm.wav',root),wave16(produced));
fs.writeFileSync(new URL('reference/preview_pic16_asm.pcm8',root),produced);
let sum=0,min=255,max=0;const hist=new Array(256).fill(0);
for(const n of produced){sum+=n;min=Math.min(min,n);max=Math.max(max,n);hist[n]++;}
const report={device:'PIC16F1503',source:'actual PIC16F1503 Intel HEX instruction execution',durationSeconds:seconds,
  timing:{fosc:16000000,carrierRate:62500,sampleRate},
  cpu:{cycles:cpu.cycle,instructions:cpu.totalInstructions,interrupts:cpu.irqCount,pwmPeriods:cpu.pwmPeriodCount,
    underruns:cpu.mem[0x60],scoreReads:flags,sections:sectionChanges,maxStackDepth:cpu.maxStackDepth??null},
  audio:{samples:produced.length,mean:sum/produced.length,min,max,nonSilenceFraction:1-hist[128]/produced.length},
  peripheral:{oscc:cpu.mem[0x099],timer2:cpu.mem[0x1c],pr2:cpu.mem[0x1b],pwm3control:cpu.mem[0x619]},
  queue:{remaining:((cpu.mem[0x45]-cpu.mem[0x44])&15),readIdx:cpu.mem[0x44],writeIdx:cpu.mem[0x45]},
  wallTimeSeconds:(performance.now()-start)/1000};
fs.writeFileSync(new URL('reports/long_run.json',root),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
