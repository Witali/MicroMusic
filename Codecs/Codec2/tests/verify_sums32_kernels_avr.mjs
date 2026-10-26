import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=resolve(root,'../../build/codec2/sums32-kernels');
const meta=JSON.parse(readFileSync(join(build,'build.json'))),memory=meta.memory,hash=b=>createHash('sha256').update(b).digest('hex'),results=[];
for(const [name,image] of Object.entries(meta.images)){
  const folder=join(build,name),binary=readFileSync(join(folder,'kernel.bin')),inputs=readFileSync(join(folder,'reference.inputs')),expected=readFileSync(join(folder,'reference.expected'));
  assert.equal(hash(binary),image.binary_sha256);assert.equal(hash(inputs),image.inputs_sha256);assert.equal(hash(expected),image.expected_sha256);assert.equal(inputs.length,image.vectors*44);assert.equal(expected.length,image.vectors*image.output_bytes);
  const symbols=new Map(readFileSync(join(folder,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
  const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
  for(const n of ['malloc','calloc','realloc'])assert.ok(!symbols.has(n));
  const top=address('__stack'),end=address('__bss_end'),status=address(image.prefix+'_status'),command=address(image.prefix+'_command'),input=address(image.prefix+'_input'),out=address(image.prefix+'_output');assert.equal(top,memory.RAMEND);
  const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,top-memory.RAMSTART+1);cpu.SP=top;let minimum=top;
  function until(predicate){const deadline=cpu.cycles+250000000;while(!predicate()){assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}}
  until(()=>cpu.data[status]!==0);const output=Buffer.alloc(expected.length),cycles=[];
  for(let i=0;i<image.vectors;++i){cpu.data.set(inputs.subarray(i*44,i*44+44),input);cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;until(()=>cpu.data[status]!==1);cycles.push(cpu.cycles-before);output.set(cpu.data.subarray(out,out+image.output_bytes),i*image.output_bytes);}
  assert.deepEqual(output,expected,'New native C and AVR must equal the frozen wide reference bytes');
  const mean=cycles.reduce((a,b)=>a+b,0)/cycles.length,record={name,vectors:image.vectors,binsPerVector:image.output_bytes/8,binarySha256:hash(binary),outputSha256:hash(output),flashBytes:binary.length,staticSramBytes:end-memory.RAMSTART,stackBytes:top-minimum,freeSramAtPeak:minimum-end+1,meanCycles:mean,maximumCycles:Math.max(...cycles),meanCycleReductionPercent:100*(1-mean/image.reference_execution.meanCycles),perVectorCycles:cycles,includesInterrupts:false};results.push(record);console.log(JSON.stringify({...record,perVectorCycles:undefined}));
}
writeFileSync(join(build,'execution.json'),JSON.stringify({simulator:'avr8js 0.21.1',mcu:'ATmega64A',results,scope:'Same deterministic inputs/harnesses as the frozen reference reports; all output bytes identical. Standalone integer-kernel timings, no IRQ or full-decoder admission.'},null,2)+'\n');
