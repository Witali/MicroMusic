import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=resolve(root,'../../build/codec2/lpc-math');
const meta=JSON.parse(readFileSync(join(build,'build.json'))),memory=meta.memory,hash=b=>createHash('sha256').update(b).digest('hex');
const binary=readFileSync(join(build,'kernel.bin')),inputs=readFileSync(join(build,'inputs.bin')),expected=readFileSync(join(build,'expected.bin'));
assert.equal(inputs.length,4499*5);assert.equal(expected.length,4499*4);assert.equal(hash(binary),meta.binary_sha256);assert.equal(hash(inputs),meta.inputs_sha256);assert.equal(hash(expected),meta.expected_sha256);
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
for(const name of ['cos','cosf','__mulsf3','__addsf3','__divsf3','malloc','calloc'])assert.ok(!symbols.has(name),name);
const top=address('__stack'),end=address('__bss_end'),status=address('codec2_math_status'),command=address('codec2_math_command'),word=address('codec2_math_word'),mode=address('codec2_math_mode'),out=address('codec2_math_output');assert.equal(top,memory.RAMEND);
const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,top-memory.RAMSTART+1);cpu.SP=top;let minimum=top;
function until(predicate){const deadline=cpu.cycles+1000000;while(!predicate()){assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}}
until(()=>cpu.data[status]!==0);const cycles=[],output=Buffer.alloc(expected.length);
for(let i=0;i<4499;++i){cpu.data[mode]=inputs[i*5];cpu.data.set(inputs.subarray(i*5+1,i*5+5),word);cpu.data[status]=1;cpu.data[command]=1;const before=cpu.cycles;until(()=>cpu.data[status]!==1);cycles.push(cpu.cycles-before);output.set(cpu.data.subarray(out,out+4),i*4);}
assert.deepEqual(output,expected,'All cosine, grid and initialization results must match checked native C byte-for-byte');
const stats=(first,last)=>{const v=cycles.slice(first,last);return {inputs:v.length,meanCycles:v.reduce((a,b)=>a+b,0)/v.length,maximumCycles:Math.max(...v)};};
const record={mcu:'ATmega64A',simulator:'avr8js 0.21.1',binarySha256:hash(binary),outputSha256:hash(output),flashBytes:binary.length,staticSramBytes:end-memory.RAMSTART,stackBytes:top-minimum,freeSramAtPeak:minimum-end+1,cosine:stats(0,4096),grid:stats(4096,4489),initialization:stats(4489,4499),perInputCycles:cycles,includesInterrupts:false,scope:'4499 identical scalar requests; integer cosine/grid/initialization kernel, native/AVR output byte equality. No floating arithmetic or cos library routine links. No full decoder/IRQ admission.'};
writeFileSync(join(build,'execution.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({...record,perInputCycles:undefined}));
