// Execute the real <=1 KiB image in three AVR engines against integer PCM.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as Reference} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';

const positional=[],options={};
for(let i=2;i<process.argv.length;i++){
  const arg=process.argv[i];
  if(arg.startsWith('--'))options[arg.slice(2)]=process.argv[++i];
  else positional.push(arg);
}
const [imagePath,expectedPath,reportPath]=positional;
if(!imagePath||!expectedPath)throw new Error('Usage: node tools/verify-fixed-period.mjs firmware.bin expected.raw [report.json] [--phrase-samples N --loops N --minimum-sp N]');
const image=readFileSync(imagePath),expected=readFileSync(expectedPath);
const phraseSamples=Number(options['phrase-samples']||expected.length);
const loops=Number(options.loops||1),minimumSP=Number(options['minimum-sp']||0x80);
if(!Number.isInteger(phraseSamples)||phraseSamples<1||!Number.isInteger(loops)||loops<1||expected.length!==phraseSamples*loops)
  throw new Error('Expected PCM length does not match phrase samples/loops');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const diagnostic=cpu=>({pcBytes:cpu.pc*2,cycles:cpu.cyc,irqCount:cpu.irqCount,writes:cpu.writes,
  registers:Array.from(cpu.r),sram:Buffer.from(cpu.sram).toString('hex')});
const engines=[['reference',new Reference(image)],['wasm',new Wasm(image)],
  ['wasm-unoptimized',new Wasm(image,null,{fastIdle:false,fastBlocks:false})]];
const reference=engines[0][1],wasm=engines[1][1];
let minPeriod=Infinity,maxPeriod=0,previous=0,completed=0,error=null,firstMismatch=null;
try{
  for(let i=0;i<expected.length;i++){
    for(const [name,cpu] of engines){
      const before=cpu.writes,actual=cpu.nextDuty();
      if(cpu.writes!==before+1)throw new Error(`${name}: expected exactly one PWM register write at sample ${i}`);
      if(actual!==expected[i]){
        firstMismatch={engine:name,sample:i,loop:Math.floor(i/phraseSamples),phraseSample:i%phraseSamples,
          expected:expected[i],actual,state:diagnostic(cpu)};
        throw new Error(`${name}: PWM mismatch at sample ${i}: ${actual} != ${expected[i]}`);
      }
    }
    for(const [name,cpu] of engines.slice(1)){
      for(const key of ['cyc','pc','irqCount','lost','workLost','maxIRQ','writes','minSP'])
        if(reference[key]!==cpu[key])throw new Error(`${name}: ${key} differs at sample ${i}`);
      if(!reference.data.every((value,index)=>value===cpu.data[index]))
        throw new Error(`${name}: register/SRAM/I/O state differs at sample ${i}`);
    }
    if(i){minPeriod=Math.min(minPeriod,wasm.cyc-previous);maxPeriod=Math.max(maxPeriod,wasm.cyc-previous);}
    previous=wasm.cyc;
    completed++;
  }
  if(wasm.lost||wasm.workLost)throw new Error(`Missed overflows=${wasm.lost}, samples=${wasm.workLost}`);
  if(wasm.irqCount!==expected.length*5)throw new Error(`Expected five Timer0 IRQs per PCM sample, got ${wasm.irqCount}`);
  if(minPeriod<1276||maxPeriod>1284)throw new Error(`Sample intervals ${minPeriod}..${maxPeriod} cycles exceed 1280 +/- 4`);
  if(wasm.minSP<minimumSP)throw new Error(`Stack 0x${wasm.minSP.toString(16)} collides with data below 0x${minimumSP.toString(16)}`);
}catch(cause){error=String(cause.message||cause);}
const report={schema:'micromusic-fixed-period-verification-v1',pass:error===null,hardwareTested:false,
  engines:engines.map(([name])=>name),cpuHz:9600000,sampleHz:7500,flashBytes:image.length,
  expectedSamples:expected.length,verifiedSamples:completed,phraseSamples,verifiedLoops:error===null?loops:0,
  imageSha256:hash(image),expectedPcmSha256:hash(expected),mismatches:firstMismatch?1:0,firstMismatch,error,
  irqCount:wasm.irqCount,lostOverflows:wasm.lost,missedSamples:wasm.workLost,maxISRCycles:wasm.maxIRQ,
  minimumSamplePeriod:Number.isFinite(minPeriod)?minPeriod:null,maximumSamplePeriod:maxPeriod||null,
  minimumSP:wasm.minSP,requiredMinimumSP:minimumSP,totalCycles:wasm.cyc};
if(reportPath)writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
if(error)process.exitCode=1;
