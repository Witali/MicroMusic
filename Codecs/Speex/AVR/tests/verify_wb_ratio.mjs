// Bounded LPC-response arithmetic against independent BigInt; no C decoder.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction,AVRTimer,timer2Config} from 'avr8js';
import {tickAvr} from './avr_tick.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)),dir=resolve(process.argv[2]);
const quick=process.argv.includes('--quick'),irq=process.argv.includes('--irq');
const binary=readFileSync(join(dir,'unit.bin')),meta=JSON.parse(readFileSync(join(dir,'input.json')));
const hash=x=>createHash('sha256').update(x).digest('hex');
assert.equal(hash(binary),meta.binarySha256);
assert.equal(meta.sourceHashMode,'UTF-8 text normalized to LF');
for(const [p,h] of Object.entries(meta.sourceSha256))
 assert.equal(hash(Buffer.from(readFileSync(join(root,p),'utf8').replace(/\r\n/g,'\n'))),h,p);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [low,high,result,command,status,end,config,irqCount,irqSum]=['ratio_low','ratio_high','ratio_result',
 'ratio_command','ratio_status','__bss_end','ratio_device','ratio_irq_count','ratio_irq_sum'].map(at);
const entries=new Map([[at('speex_wb_ratio_div_avr'),'asm'],[at('ratio_reference'),'c']]);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);new AVRTimer(cpu,timer2Config);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const stats={asm:{calls:0,minCycles:Infinity,maxCycles:0},c:{calls:0,minCycles:Infinity,maxCycles:0}};
let active=null,returns=0,cases=0,negative=0,saturated=0,zero=0,minSP=2303,lastAsm=false;
let insideIrq=false,irqVector=-1,irqEntries=0,irqReturns=0,timerEvents=0;
const setFlag=cpu.setInterruptFlag.bind(cpu);
cpu.setInterruptFlag=interrupt=>{if(interrupt.address===timer2Config.compAInterrupt)++timerEvents;setFlag(interrupt);};
function until(done){const deadline=cpu.cycles+30000;while(!done()){
 assert.ok(cpu.cycles<deadline,'Ratio timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(pc===irqVector){assert.equal(insideIrq,false);insideIrq=true;++irqEntries;}
 const name=entries.get(pc);
 if(name){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]);
  const patterns=saved.map(r=>(returns*73+r*29)&255);
  if(name==='asm')saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={name,original,patterns,sp:cpu.SP,cycles:0};
 }
 const returning=active&&opcode===0x9508&&cpu.SP===active.sp;
 const before=cpu.cycles,enabled=cpu.interruptsEnabled;avrInstruction(cpu);
 if(active&&!insideIrq)active.cycles+=cpu.cycles-before;
 if(returning){
  const a=active,s=stats[a.name];assert.equal(cpu.SP,a.sp+2);
  if(a.name==='asm'){
   assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'Callee-saved ABI');
   saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});lastAsm=true;++returns;
  }
  assert.equal(cpu.data[1],0,'r1 at primitive return');++s.calls;
  s.minCycles=Math.min(s.minCycles,a.cycles);s.maxCycles=Math.max(s.maxCycles,a.cycles);active=null;
 }
 if(opcode===0x9518){assert.equal(insideIrq,true);insideIrq=false;++irqReturns;}
 tickAvr(cpu,enabled);minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Stack collision');
}}
until(()=>cpu.data[status]===1);
const clockAddress=cpu.dataView.getUint16(config,true),clockValue=cpu.dataView.getUint16(config+2,true);
irqVector=2*cpu.dataView.getUint16(config+4,true);
assert.equal(irqVector,2*timer2Config.compAInterrupt,'Manufacturer vector matches timer model');
if(irq)cpu.writeData(clockAddress,clockValue);
function oracle(a,d){
 const divisor=BigInt(d),half=BigInt.asIntN(16,divisor)>>1n;
 const numerator=BigInt(a)*128n+half,q=numerator/divisor;
 return {value:Number(q>32767n?32767n:q< -32767n? -32767n:q),numerator};
}
function check(a,d){
 assert.ok(a>=1&&a<=335949&&d>=1&&d<=270414);
 const expected=oracle(a,d);
 if(expected.numerator<0n)++negative;if(expected.value===32767)++saturated;if(expected.value===0)++zero;
 for(const kind of [1,2,3]){
  cpu.dataView.setInt32(low,a,true);cpu.dataView.setInt32(high,d,true);
  cpu.data[status]=1;cpu.data[command]=kind;lastAsm=false;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(result,true),expected.value,`Ratio ${a}/${d} kind${kind}`);
  assert.equal(cpu.dataView.getInt32(low,true),a);assert.equal(cpu.dataView.getInt32(high,true),d);
  assert.equal(lastAsm,kind===1||(kind===3&&meta.backend==='asm'),'Explicit backend selection');
 }
 ++cases;
}
// All positive divisors with tiny/ordinary/maximal responses. Tiny a exercises
// negative rounded numerators at every signed16 half-divisor wrap interval.
const stride=quick?997:1;let sweep=0;
for(let d=1;d<=270414;d+=stride){for(const a of [1,8192,335949])check(a,d);++sweep;
 if(!quick&&(d&32767)===0)console.log('Checked LPC-response divisors through',d);
}
const divisors=new Set([1,2,3,7,17,127,255,256,257,270413,270414]);
for(let bit=1;bit<=18;bit++)for(const delta of [-2,-1,0,1,2]){
 const d=2**bit+delta;if(d>=1&&d<=270414)divisors.add(d);
}
for(let wrap=32768;wrap<=270414;wrap+=32768)for(const delta of [-2,-1,0,1,2])divisors.add(wrap+delta);
let boundaries=0;
for(const d of divisors){
 for(const a of [1,2,127,128,255,256,8191,8192,8193,335948,335949]){check(a,d);++boundaries;}
 const half=Number(BigInt.asIntN(16,BigInt(d))>>1n);
 for(const q of [0,1,2,127,128,255,256,32766,32767,32768]){
  const near=Math.floor((q*d-half)/128);
  for(const a of [near-1,near,near+1])if(a>=1&&a<=335949){check(a,d);++boundaries;}
 }
}
let seed=0x6f192b8c;
const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
const signed=()=>((random()>>>16)<<16)>>16;
let coefficientCases=0;
while(coefficientCases<(quick?256:10000)){
 let a=8274,d=8274;for(let i=0;i<5;i++)a+=signed()-signed();for(let i=0;i<4;i++)d+=signed()-signed();
 if(a>0&&d>0){check(a,d);++coefficientCases;}
}
if(irq){
 cpu.writeData(clockAddress,0);until(()=>!insideIrq&&cpu.dataView.getUint32(irqCount,true)===timerEvents&&cpu.interruptsEnabled);
 assert.ok(timerEvents>0);assert.equal(irqEntries,timerEvents);assert.equal(irqReturns,timerEvents);
 let sum=0;for(let i=0;i<timerEvents;i++)sum=(sum+(((i+37)&255)*((i+129)&255)))&65535;
 assert.equal(cpu.dataView.getUint16(irqSum,true),sum,'ISR multiply/accumulator state');
}else assert.equal(timerEvents,0);
assert.equal(returns,cases*(meta.backend==='asm'?2:1));assert.equal(stats.c.calls,cases*(meta.backend==='asm'?1:2));
const report={scope:'Isolated C/ASM LPC-response primitive; no C decoder execution or timing',
 backend:meta.backend,binarySha256:meta.binarySha256,sourceHashMode:meta.sourceHashMode,sourceSha256:meta.sourceSha256,
 deviceHeadersSha256:meta.deviceHeadersSha256,cases,allPositiveDivisors:!quick,divisorsSwept:sweep,
 sweepResponses:[1,8192,335949],boundaryCases:boundaries,coefficientDerivedCases:coefficientCases,
 negativeRoundedNumerators:negative,saturatedCases:saturated,zeroQuotients:zero,
 independentBigIntExact:true,signed16DivisorHalfCastPreserved:true,explicitBackendSelectionVerified:true,
 calleeSavedAndR1Returns:returns,arbitraryCalleeSavedPatterns:true,readonlyInputs:true,
 stats,includesInterrupts:irq,completedTimerInterrupts:irqReturns,timerCompareEvents:timerEvents,
 noLostTimerInterrupts:irq?irqReturns===timerEvents:null,peakStack:2303-minSP,physicalBoardTested:false};
writeFileSync(join(dir,irq?'verification-irq.json':quick?'verification-quick.json':'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log('PASS LPC-response ratio',JSON.stringify(report));
