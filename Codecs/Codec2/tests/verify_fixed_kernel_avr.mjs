import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)), build=resolve(root,'../../build/codec2/fixed-kernel');
const meta=JSON.parse(readFileSync(join(build,'build.json'))), memory=meta.memory;
const hash=b=>createHash('sha256').update(b).digest('hex');
const inputs=readFileSync(join(build,'inputs.bin'));
assert.equal(hash(inputs),meta.inputs_sha256);
const results=[];
for (const name of ['float','fixed']) {
  const binary=readFileSync(join(build,name+'.bin')), expected=readFileSync(join(build,name+'.expected.bin'));
  assert.equal(hash(binary),meta.images[name].binary_sha256); assert.equal(hash(expected),meta.images[name].expected_sha256);
  const symbols=new Map(readFileSync(join(build,name+'.symbols'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
  const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
  const top=address('__stack'), end=address('__bss_end'); assert.equal(top,memory.RAMEND);
  const status=address('codec2_fft_status'), command=address('codec2_fft_command'), data=address('codec2_fft_buffer');
  const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff); new Uint8Array(program.buffer).set(binary);
  const cpu=new CPU(program,top-memory.RAMSTART+1); cpu.SP=top;
  let minimum=top;
  function until(predicate) {
    const deadline=cpu.cycles+20000000;
    while (!predicate()) {assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}
  }
  until(()=>cpu.data[status]!==0);
  const cycles=[], output=Buffer.alloc(512*2048);
  for (let v=0;v<512;++v) {
    cpu.data.set(inputs.subarray(v*2056,(v+1)*2056),data);
    cpu.data[status]=1;cpu.data[command]=1;
    const before=cpu.cycles;until(()=>cpu.data[status]!==1);cycles.push(cpu.cycles-before);
    output.set(cpu.data.subarray(data,data+2048),v*2048);
    if ((v+1)%128===0) console.log(`${name} inverse: ${v+1}/512 vectors`);
  }
  if (name==='fixed') assert.deepEqual(output,expected,'Integer C and AVR kernel output must be byte-identical');
  else for(let i=0;i<output.length;i+=4) assert.equal(output.readFloatLE(i),expected.readFloatLE(i));
  const result={name,vectors:512,outputSha256:hash(output),expectedSha256:hash(expected),binarySha256:hash(binary),
    flashBytes:binary.length,staticSramBytes:end-memory.RAMSTART,stackBytes:top-minimum,freeSramAtPeak:minimum-end+1,
    meanCycles:cycles.reduce((a,b)=>a+b,0)/512,maximumCycles:Math.max(...cycles),perVectorCycles:cycles,includesInterrupts:false};
  results.push(result);console.log(JSON.stringify({...result,perVectorCycles:undefined}));
}
writeFileSync(join(build,'execution.json'),JSON.stringify({simulator:'avr8js 0.21.1',mcu:'ATmega64A',results,
  meanCycleReductionPercent:100*(1-results[1].meanCycles/results[0].meanCycles),
  scope:'Identical 512 kernel input spectra, no IRQ. Fixed output byte-identical to checked native integer C; float values match original KISS.'},null,2)+'\n');
