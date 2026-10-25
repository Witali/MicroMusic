// Instruction-level cycle ledger; profiling does not replace the audio oracle.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-reference.js';

export function profile(folder){
 const json=name=>JSON.parse(fs.readFileSync(path.join(folder,name)));
 const meta=json('build-report.json'),verification=json('verification.json');
 const rom=fs.readFileSync(path.join(folder,'synth.bin'));
 assert.equal(createHash('sha256').update(rom).digest('hex'),meta.flashSha256);
 assert.equal(verification.flashSha256,meta.flashSha256);assert.equal(verification.passed,true);
 assert.equal(meta.pwmBufferLayout,'mono');
 const c=new AVRCore(rom,null,{target:'attiny88',cpuHz:meta.cpuHz,fastIdle:false,fastBlocks:false});
 const functions=['um_render','um_scale_wave','__vector_'+c.profile.timer.vector,'um_word',
  'command','read_events','refresh','um_init','um_tick','um_output','main','__mulhi3','_exit'];
 const starts=functions.filter(n=>meta.labels[n]!==undefined).map(name=>({name,pc:meta.labels[name]/2})).sort((a,b)=>a.pc-b.pc);
 const owner=Array(c.words).fill('startup');
 const entry=new Uint8Array(c.words);starts.forEach(s=>entry[s.pc]=1);
 starts.forEach((s,i)=>{for(let pc=s.pc;pc<(starts[i+1]?.pc??meta.engineBytes/2);pc++)owner[pc]=s.name;});
 const at=name=>meta.labels[name]-0x800000,render=meta.labels.um_render/2;
 const pollStart=c.op.findIndex((op,pc)=>pc>meta.labels.main/2&&op===37&&c.k[pc]===at('um_read'));
 const pollEnd=c.op.findIndex((op,pc)=>pc>pollStart&&op===8&&pc+1+c.k[pc]===pollStart);
 assert.ok(pollStart>0&&pollEnd>pollStart,'Recognizable cursor polling loop');
 const samples=Math.ceil((meta.controlTicks+Math.min(2,meta.controlTicks))*meta.cpuHz/75000);
 const cycles={},calls={},multiplyCallers={};
 const add=(name,n)=>{cycles[name]=(cycles[name]||0)+n;};
 let entries=0,start=null,pollCycles=0,idle=0,minQueue=meta.pwmBufferFrames;
 const beginning=performance.now();
 while(c.cyc<meta.cpuHz*(meta.controlTicks/(18750/256)+2)){
  if(!c.inIRQ&&c.pc===render){if(entries++===samples)break;if(start===null)start=c.cyc;}
  if(start===null){c.step();continue;}
  const pc=c.pc,inIRQ=c.inIRQ,op=c.op[pc],name=owner[pc],before=c.cyc,irqs=c.irqCount;
  if(!inIRQ&&pc===pollStart)pollCycles=0;
  if(!inIRQ&&entry[pc])calls[name]=(calls[name]||0)+1;
  if(!inIRQ&&op===6){
   const target=pc+1+c.k[pc];
   if(target===meta.labels.__mulhi3/2)multiplyCallers[name]=(multiplyCallers[name]||0)+1;
  }
  const rejected=!inIRQ&&pc===pollEnd&&((c.sreg>>c.d[pc])&1)===c.s[pc];
  if(inIRQ&&pc===meta.labels['__vector_'+c.profile.timer.vector]/2){
   const queued=(c.data[at('um_write')]-c.data[at('um_read')]+meta.pwmBufferFrames)%meta.pwmBufferFrames;
   minQueue=Math.min(minQueue,queued);assert.ok(queued>0);
  }
  c.step();
  const entryCycles=(c.irqCount-irqs)*4,elapsed=c.cyc-before-entryCycles;
  add(inIRQ?'PWM_IRQ':name,elapsed);if(entryCycles)add('PWM_IRQ',entryCycles);
  if(!inIRQ&&name==='main')pollCycles+=elapsed;
  if(rejected){cycles.main-=pollCycles;idle+=pollCycles;pollCycles=0;}
 }
 assert.equal(entries,samples+1);assert.equal(c.data[at('um_underruns')],0);assert.equal(c.lost,0);assert.equal(c.workLost,0);
 cycles.idle_poll=idle;
 assert.equal(Object.values(cycles).reduce((a,b)=>a+b,0),c.cyc-start,'Complete cycle ledger including IRQ entry');
 const elapsed=c.cyc-start;
 return {schema:'micromusic-um88-cycle-profile',version:1,variant:meta.variant,cpuHz:meta.cpuHz,
  flashSha256:meta.flashSha256,engineSha256:meta.engineSha256,engineBytes:meta.engineBytes,
  samples,profileSeconds:elapsed/meta.cpuHz,hardwareTested:false,
  method:'AVR instruction stepping with IRQ active; exclusive function cycles; IRQ entry attributed separately; rejected FIFO polls separated',
  measuredCycles:elapsed,busyCyclesPerSample:(elapsed-idle)/samples,idlePercent:100*idle/elapsed,
  exclusive:Object.fromEntries(Object.entries(cycles).map(([name,n])=>[name,{cycles:n,perSample:n/samples,percent:100*n/elapsed,calls:calls[name]||0}])),
  multiplyCallers,minimumQueuedFrames:minQueue,maxISRCycles:c.maxIRQ,minimumStackPointer:c.minSP,
  fifoUnderruns:c.data[at('um_underruns')],lostInterrupts:c.lost,wallSeconds:(performance.now()-beginning)/1000};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const result=profile(path.resolve(process.argv[2]));
 if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));
}
