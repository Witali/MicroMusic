import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=resolve(root,'../../build/codec2/adaptive-kernel');
const meta=JSON.parse(readFileSync(join(build,'build.json'))),memory=meta.memory,hash=b=>createHash('sha256').update(b).digest('hex');
const inputs=readFileSync(join(build,'inputs.bin')),expected=readFileSync(join(build,'expected.bin')),binary=readFileSync(join(build,'kernel.bin'));
assert.equal(inputs.length,64*44);assert.equal(expected.length,64*2056);
assert.equal(hash(inputs),meta.inputs_sha256);assert.equal(hash(expected),meta.expected_sha256);assert.equal(hash(binary),meta.binary_sha256);
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
const top=address('__stack'),end=address('__bss_end'),status=address('codec2_analysis_status'),command=address('codec2_analysis_command'),input=address('codec2_analysis_input'),out=address('codec2_analysis_output');
assert.equal(top,memory.RAMEND);for(const name of ['malloc','calloc','realloc'])assert.ok(!symbols.has(name));
for(const name of ['compact_twiddle','compact_super'])assert.ok(symbols.get(name)>=0&&symbols.get(name)<65536);
const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,top-memory.RAMSTART+1);cpu.SP=top;let minimum=top;
function until(predicate){const deadline=cpu.cycles+250000000;while(!predicate()){assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}}
until(()=>cpu.data[status]!==0);const cycles=[],output=Buffer.alloc(expected.length);
for(let i=0;i<64;++i){
  cpu.data.set(inputs.subarray(44*i,44*i+44),input);cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;
  until(()=>cpu.data[status]!==1);cycles.push(cpu.cycles-before);output.set(cpu.data.subarray(out,out+2056),i*2056);
}
assert.deepEqual(output,expected,'Every fixed spectrum bin must match native checked C byte-for-byte');
const record={simulator:'avr8js 0.21.1',mcu:'ATmega64A',vectors:64,binsPerVector:257,binarySha256:hash(binary),outputSha256:hash(output),
  flashBytes:binary.length,staticSramBytes:end-memory.RAMSTART,stackBytes:top-minimum,freeSramAtPeak:minimum-end+1,
  meanCycles:cycles.reduce((a,b)=>a+b,0)/cycles.length,maximumCycles:Math.max(...cycles),perVectorCycles:cycles,includesInterrupts:false,
  scope:'Identical 11-coefficient binary32 vectors, scales 2^-16..2^16; integer narrow main spectrum with selective faithful refinement plus boundary conversions. All output bytes equal native checked C. No IRQ or full-decoder admission.'};
writeFileSync(join(build,'execution.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({...record,perVectorCycles:undefined}));
