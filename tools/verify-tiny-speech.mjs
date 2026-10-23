// Compare the real ATtiny13 Flash+EEPROM image with the integer speech oracle.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore as Reference} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';

const positional=[],options={};
for(let i=2;i<process.argv.length;i++){
  const arg=process.argv[i];
  if(arg.startsWith('--')){
    if(i+1===process.argv.length)throw new Error(`Missing value for ${arg}`);
    options[arg.slice(2)]=process.argv[++i];
  }else positional.push(arg);
}
const [imagePath,expectedPath,reportPath]=positional;
if(!imagePath||!expectedPath||!options.eeprom)
  throw new Error('Usage: node tools/verify-tiny-speech.mjs firmware.bin expected.raw [report.json] --eeprom eeprom.bin [--phrase-samples N --loops N --minimum-sp N --actual-raw path]');
const image=readFileSync(imagePath),expected=readFileSync(expectedPath),eeprom=readFileSync(options.eeprom);
if(!image.length||image.length>1024)throw new Error('ATtiny13 Flash must contain 1..1024 bytes');
if(eeprom.length!==64)throw new Error('ATtiny13 EEPROM image must contain exactly 64 bytes');
const phraseSamples=Number(options['phrase-samples']||expected.length);
const loops=Number(options.loops||1),minimumSP=Number(options['minimum-sp']||0x60);
if(!Number.isInteger(phraseSamples)||phraseSamples<1||!Number.isInteger(loops)||loops<1||expected.length!==phraseSamples*loops)
  throw new Error('Expected PCM length does not match phrase samples/loops');
if(!Number.isInteger(minimumSP)||minimumSP<0x60||minimumSP>0x9f)
  throw new Error('Required stack floor must be in the ATtiny13 SRAM address range');
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const diagnostic=cpu=>({pcBytes:cpu.pc*2,cycles:cpu.cyc,irqCount:cpu.irqCount,writes:cpu.writes,
  registers:Array.from(cpu.r),sram:Buffer.from(cpu.sram).toString('hex')});
const engines=[['reference',new Reference(image,eeprom)],['wasm',new Wasm(image,eeprom)],
  ['wasm-unoptimized',new Wasm(image,eeprom,{fastIdle:false,fastBlocks:false})]];
const reference=engines[0][1],wasm=engines[1][1],actualPcm=Buffer.alloc(expected.length);
let minPeriod=Infinity,maxPeriod=0,previous=0,completed=0,error=null,firstMismatch=null;
try{
  for(let i=0;i<expected.length;i++){
    for(const [name,cpu] of engines){
      const before=cpu.writes,actual=cpu.nextDuty();
      if(cpu.writes!==before+1)throw new Error(`${name}: expected exactly one PWM register write at sample ${i}`);
      if(name==='wasm')actualPcm[i]=actual;
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
      if(!eeprom.every((value,index)=>value===cpu.eeprom[index]))
        throw new Error(`${name}: EEPROM was modified at sample ${i}`);
    }
    if(i){minPeriod=Math.min(minPeriod,wasm.cyc-previous);maxPeriod=Math.max(maxPeriod,wasm.cyc-previous);}
    previous=wasm.cyc;
    completed++;
  }
  if(wasm.lost||wasm.workLost)throw new Error(`Missed overflows=${wasm.lost}, samples=${wasm.workLost}`);
  if(wasm.irqCount!==expected.length*5)throw new Error(`Expected five Timer0 IRQs per PCM sample, got ${wasm.irqCount}`);
  if(minPeriod<1279||maxPeriod>1281)throw new Error(`Sample intervals ${minPeriod}..${maxPeriod} cycles exceed 1280 +/- 1`);
  if(wasm.minSP<minimumSP)throw new Error(`Stack 0x${wasm.minSP.toString(16)} collides with data below 0x${minimumSP.toString(16)}`);
}catch(cause){error=String(cause.message||cause);}
const report={schema:'micromusic-tiny-speech-verification-v1',pass:error===null,hardwareTested:false,
  engines:engines.map(([name])=>name),cpuHz:9600000,sampleHz:7500,flashBytes:image.length,eepromBytes:eeprom.length,
  expectedSamples:expected.length,verifiedSamples:completed,phraseSamples,verifiedLoops:error===null?loops:0,
  imageSha256:hash(image),eepromSha256:hash(eeprom),expectedPcmSha256:hash(expected),
  actualPcmSha256:completed===expected.length?hash(actualPcm):null,
  mismatches:firstMismatch?1:0,firstMismatch,error,
  irqCount:wasm.irqCount,lostOverflows:wasm.lost,missedSamples:wasm.workLost,maxISRCycles:wasm.maxIRQ,
  minimumSamplePeriod:Number.isFinite(minPeriod)?minPeriod:null,maximumSamplePeriod:maxPeriod||null,
  minimumSP:wasm.minSP,requiredMinimumSP:minimumSP,
  staticSramSpanBytes:minimumSP-0x60,stackHighWaterBytes:0x9f-wasm.minSP,
  maximumSramSpanBytes:minimumSP-0x60+0x9f-wasm.minSP,
  stackSpareBytes:wasm.minSP-minimumSP,totalCycles:wasm.cyc};
if(reportPath)writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
if(options['actual-raw']&&completed===expected.length)writeFileSync(options['actual-raw'],actualPcm);
console.log(JSON.stringify(report,null,2));
if(error)process.exitCode=1;
