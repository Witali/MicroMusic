import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=resolve(root,'../../build/codec2/fifth-kernel');
const meta=JSON.parse(readFileSync(join(build,'build.json'))),memory=meta.memory,hash=b=>createHash('sha256').update(b).digest('hex');
const inputs=readFileSync(join(build,'inputs.bin'));assert.equal(hash(inputs),meta.inputs_sha256);
const results=[];
for(const name of ['float','fixed']){
  const binary=readFileSync(join(build,name+'.bin')),expected=readFileSync(join(build,name+'.expected.bin'));
  assert.equal(hash(binary),meta.images[name].binary_sha256);assert.equal(hash(expected),meta.images[name].expected_sha256);
  const symbols=new Map(readFileSync(join(build,name+'.symbols'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
  const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
  const top=address('__stack'),end=address('__bss_end'),status=address('codec2_root_status'),command=address('codec2_root_command'),input=address('codec2_root_input'),out=address('codec2_root_output');
  assert.equal(top,memory.RAMEND);
  if(name==='fixed'){assert.ok(!symbols.has('pow')&&!symbols.has('powf')&&!symbols.has('__muldi3'));}
  const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff);new Uint8Array(program.buffer).set(binary);
  const cpu=new CPU(program,top-memory.RAMSTART+1);cpu.SP=top;let minimum=top;
  function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}}
  until(()=>cpu.data[status]!==0);const cycles=[],output=Buffer.alloc(inputs.length);
  for(let i=0;i<4096;++i){cpu.data.set(inputs.subarray(4*i,4*i+4),input);cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;until(()=>cpu.data[status]!==1);cycles.push(cpu.cycles-before);output.set(cpu.data.subarray(out,out+4),4*i);}
  if(name==='fixed')assert.deepEqual(output,expected,'Fixed scalar outputs must match native integer C bit-for-bit');
  let maxRelativeError=0,nonfiniteMismatches=0;
  for(let i=0;i<output.length;i+=4){const a=output.readFloatLE(i),b=expected.readFloatLE(i);if(Number.isFinite(a)&&Number.isFinite(b)){if(b!==0)maxRelativeError=Math.max(maxRelativeError,Math.abs(a/b-1));}else if(a!==b)++nonfiniteMismatches;}
  const record={name,inputs:4096,binarySha256:hash(binary),expectedSha256:hash(expected),outputSha256:hash(output),maximumRelativeErrorToNative:maxRelativeError,nonfiniteMismatches,
    flashBytes:binary.length,staticSramBytes:end-memory.RAMSTART,stackBytes:top-minimum,freeSramAtPeak:minimum-end+1,meanCycles:cycles.reduce((a,b)=>a+b,0)/cycles.length,maximumCycles:Math.max(...cycles),perInputCycles:cycles,includesInterrupts:false};
  results.push(record);console.log(JSON.stringify({...record,perInputCycles:undefined}));
}
writeFileSync(join(build,'execution.json'),JSON.stringify({simulator:'avr8js 0.21.1',mcu:'ATmega64A',results,meanCycleReductionPercent:100*(1-results[1].meanCycles/results[0].meanCycles),
  scope:'4096 identical binary32 scalar inputs; fixed output byte-identical to native C. Standalone timings without IRQ, not full decoder admission.'},null,2)+'\n');
