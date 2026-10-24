import {readFileSync,writeFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {AVRCore as Reference} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';

const [input,output]=process.argv.slice(2),spec=JSON.parse(readFileSync(input,'utf8'));
const bytes=readFileSync(spec.image),results=[];
for(const [name,cpu] of [['reference',new Reference(bytes)],['wasm',new Wasm(bytes)],
 ['wasm-unoptimized',new Wasm(bytes,undefined,{fastIdle:false,fastBlocks:false})]]){
 const result={engine:name,checked:0,irqChecked:0,minimumCycles:Infinity,maximumCycles:0,maximumStack:0};
 for(let area=-112;area<=112;area++)for(let lag=0;lag<16;lag++)for(const interrupt of [false,true]){
  const initial=Array.from({length:32},(_,i)=>(i*53+17)&255);cpu.r.set(initial);
  cpu.r[18]=area&255;cpu.r[19]=lag;
  cpu.pc=spec.symbols.balanced_tail_q1/2;cpu.sp=0x9f;cpu.sreg=interrupt?0xc1:0x41;
  cpu.io[0x39]=interrupt?2:0;cpu.pending=false;cpu.irqDelay=0;
  cpu.pushPC(511);const before=cpu.cyc,irqs=cpu.irqCount;let steps=0,injected=false,minsp=cpu.sp;
  while(cpu.pc!==511&&steps++<100){
   if(interrupt&&!injected&&cpu.pc===spec.symbols.balanced_tail_compare/2){cpu.pending=true;cpu.interrupt();injected=true;}
   cpu.step();minsp=Math.min(minsp,cpu.sp);
  }
  assert.equal(cpu.pc,511);
  // Independent scalar signed quotient/remainder specification.
  const magnitude=Math.abs(area),tap=Math.trunc(magnitude/16)+(lag>=16-magnitude%16?1:0);
  assert.equal(cpu.r[24],(area<0?-tap:tap)&255,JSON.stringify({name,area,lag,interrupt}));
  for(let i=0;i<32;i++)if(![18,19,20,24].includes(i))assert.equal(cpu.r[i],initial[i]);
  assert.equal(cpu.r[18],area&255);assert.equal(cpu.r[19],lag);assert.equal(cpu.sp,0x9f);
  assert.equal(cpu.sreg&0xc0,interrupt?0xc0:0x40);
  result.maximumStack=Math.max(result.maximumStack,0x9f-minsp);
  if(interrupt){assert.ok(injected);assert.equal(cpu.irqCount-irqs,1);result.irqChecked++;}
  else{const elapsed=cpu.cyc-before;result.minimumCycles=Math.min(result.minimumCycles,elapsed);result.maximumCycles=Math.max(result.maximumCycles,elapsed);result.checked++;}
 }
 results.push(result);
}
for(const result of results.slice(1))assert.deepEqual({...result,engine:null},{...results[0],engine:null});
const report={pass:true,scope:'Every Q1 head area -112..112 and every tail position 0..15',kernelBytes:spec.kernelBytes,
 checked:results.reduce((n,r)=>n+r.checked,0),irqChecked:results.reduce((n,r)=>n+r.irqChecked,0),engines:results,
 timingScope:'Entry through RET; excludes caller RCALL, descriptor load, head reader, gain and pitch control',
 fullDecoderImplemented:false,hardwareTested:false};
writeFileSync(output,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
