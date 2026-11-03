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
const replayAt=process.argv.indexOf('--replay'),replayPath=replayAt<0?null:resolve(process.argv[replayAt+1]);
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
const generic=meta.api==='generic';assert.ok(!generic||replayPath,'Generic controls use this checker only for replay');
const entries=new Map([[at(generic?'speex_wb_ratio_div_avr':'speex_wb_ratio_hb_div_avr'),'asm'],[at('ratio_reference'),'c']]);
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);new AVRTimer(cpu,timer2Config);
const saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const selectedEntry=at('ratio_selected');let selectedActive=null,lastAsmCycles=0,lastSelectedCycles=0;const timingCases=[],timingGroups={};
const stats={selected:{calls:0,minCycles:Infinity,maxCycles:0,totalCycles:0},asm:{calls:0,minCycles:Infinity,maxCycles:0},c:{calls:0,minCycles:Infinity,maxCycles:0}};
let active=null,returns=0,cases=0,negative=0,saturated=0,zero=0,minSP=2303,lastAsm=false;
let insideIrq=false,irqVector=-1,irqEntries=0,irqReturns=0,timerEvents=0;
const setFlag=cpu.setInterruptFlag.bind(cpu);
cpu.setInterruptFlag=interrupt=>{if(interrupt.address===timer2Config.compAInterrupt)++timerEvents;setFlag(interrupt);};
function until(done){const deadline=cpu.cycles+30000;while(!done()){
 assert.ok(cpu.cycles<deadline,'Ratio timeout');const pc=cpu.pc*2,opcode=cpu.progMem[cpu.pc];
 if(pc===irqVector){assert.equal(insideIrq,false);insideIrq=true;++irqEntries;}
 if(pc===selectedEntry){assert.equal(selectedActive,null);selectedActive={sp:cpu.SP,cycles:0};}
 const name=entries.get(pc);
 if(name){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]);
  const patterns=saved.map(r=>(returns*73+r*29)&255);
  if(name==='asm')saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});
  active={name,original,patterns,sp:cpu.SP,cycles:0};
 }
 const returning=active&&opcode===0x9508&&cpu.SP===active.sp;
 const selectedReturning=selectedActive&&opcode===0x9508&&cpu.SP===selectedActive.sp;
 const before=cpu.cycles,enabled=cpu.interruptsEnabled;avrInstruction(cpu);
 if(active&&!insideIrq)active.cycles+=cpu.cycles-before;
 if(selectedActive&&!insideIrq)selectedActive.cycles+=cpu.cycles-before;
 if(returning){
  const a=active,s=stats[a.name];assert.equal(cpu.SP,a.sp+2);
  if(a.name==='asm'){
   assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns,'Callee-saved ABI');
   saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});lastAsm=true;lastAsmCycles=a.cycles;++returns;
  }
  assert.equal(cpu.data[1],0,'r1 at primitive return');++s.calls;
  s.minCycles=Math.min(s.minCycles,a.cycles);s.maxCycles=Math.max(s.maxCycles,a.cycles);active=null;
 }
 if(selectedReturning){const s=stats.selected,a=selectedActive;++s.calls;s.totalCycles+=a.cycles;s.minCycles=Math.min(s.minCycles,a.cycles);s.maxCycles=Math.max(s.maxCycles,a.cycles);lastSelectedCycles=a.cycles;selectedActive=null;}
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
 assert.ok(a>=1&&a<=335949&&d>=111&&d<=31849);
 const expected=oracle(a,d);
 if(expected.numerator<0n)++negative;if(expected.value===32767)++saturated;if(expected.value===0)++zero;
 for(const kind of [1,2,3]){
  cpu.dataView.setInt32(low,a,true);cpu.dataView.setInt32(high,d,true);
  cpu.data[status]=1;cpu.data[command]=kind;lastAsm=false;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(result,true),expected.value,`Ratio ${a}/${d} kind${kind}`);
  assert.equal(cpu.dataView.getInt32(low,true),a);assert.equal(cpu.dataView.getInt32(high,true),d);
  assert.equal(lastAsm,kind===1||(kind===3&&meta.backend==='asm'),'Explicit backend selection');
 }
 timingCases.push(lastAsmCycles,lastSelectedCycles);
 const group=expected.numerator<0n?'negative':(expected.numerator/BigInt(d)>=32768n?'saturated':d<=32767?'narrow':d<=65535?'wide16':'wide24');
 const g=timingGroups[group]??={cases:0,asmTotal:0,selectedTotal:0};++g.cases;g.asmTotal+=lastAsmCycles;g.selectedTotal+=lastSelectedCycles;
 ++cases;
}
// Sweep the complete positive validated-HB1 divisor range, then rounding,
// saturation and coefficient-derived boundaries. Generic API replay stays
// inside this same validated input subset; its wider domain has separate tests.
let sweep=0,boundaries=0,coefficientCases=0;
if(replayPath){
 const replay=JSON.parse(readFileSync(replayPath,'utf8'));
 for(const [a,d,n] of replay.captured){assert.equal(oracle(a,d).numerator,BigInt(n));check(a,d);}
}else{
const stride=quick?997:1;
for(let d=111;d<=31849;d+=stride){for(const a of [1,8192,335949])check(a,d);++sweep;
 if(!quick&&(d&32767)===0)console.log('Checked LPC-response divisors through',d);
}
const divisors=new Set([111,112,113,127,128,129,255,256,257,31847,31848,31849]);
for(let bit=1;bit<=18;bit++)for(const delta of [-2,-1,0,1,2]){
 const d=2**bit+delta;if(d>=111&&d<=31849)divisors.add(d);
}

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
while(coefficientCases<(quick?256:10000)){
 let a=8274,d=8274;for(let i=0;i<5;i++)a+=signed()-signed();for(let i=0;i<4;i++)d+=signed()-signed();
 if(a>0&&d>=111&&d<=31849){check(a,d);++coefficientCases;}
}
}
if(irq){
 cpu.writeData(clockAddress,0);until(()=>!insideIrq&&cpu.dataView.getUint32(irqCount,true)===timerEvents&&cpu.interruptsEnabled);
 assert.ok(timerEvents>0);assert.equal(irqEntries,timerEvents);assert.equal(irqReturns,timerEvents);
 let sum=0;for(let i=0;i<timerEvents;i++)sum=(sum+(((i+37)&255)*((i+129)&255)))&65535;
 assert.equal(cpu.dataView.getUint16(irqSum,true),sum,'ISR multiply/accumulator state');
}else assert.equal(timerEvents,0);
assert.equal(returns,cases*(meta.backend==='asm'?2:1));assert.equal(stats.c.calls,cases*(meta.backend==='asm'?1:2));
const report={scope:'Isolated validated-HB1 C/ASM scalar and ABI checks; no complete C decoder execution or timing',
 api:meta.api,replayInputSha256:replayPath?hash(readFileSync(replayPath)):null,
 backend:meta.backend,binarySha256:meta.binarySha256,sourceHashMode:meta.sourceHashMode,sourceSha256:meta.sourceSha256,
 deviceHeadersSha256:meta.deviceHeadersSha256,cases,allValidatedHbDivisors:!quick&&!replayPath,validatedHbDivisorBounds:[111,31849],divisorsSwept:sweep,
 sweepResponses:[1,8192,335949],boundaryCases:boundaries,coefficientDerivedCases:coefficientCases,
 negativeRoundedNumerators:negative,saturatedCases:saturated,zeroQuotients:zero,
 independentBigIntExact:true,signed16DivisorHalfCastPreserved:true,explicitBackendSelectionVerified:true,
 calleeSavedAndR1Returns:returns,arbitraryCalleeSavedPatterns:true,readonlyInputs:true,
 stats,includesInterrupts:irq,completedTimerInterrupts:irqReturns,timerCompareEvents:timerEvents,
 noLostTimerInterrupts:irq?irqReturns===timerEvents:null,peakStack:2303-minSP,physicalBoardTested:false};
const mode=replayPath?'replay':quick?'quick':'full',suffix=irq?'-irq':'';
report.timingGroups=timingGroups;writeFileSync(join(dir,`timing-${mode}${suffix}.bin`),Buffer.from(Uint16Array.from(timingCases).buffer));
writeFileSync(join(dir,`verification-${mode}${suffix}.json`),JSON.stringify(report,null,2)+'\n');
console.log('PASS LPC-response ratio',JSON.stringify(report));
