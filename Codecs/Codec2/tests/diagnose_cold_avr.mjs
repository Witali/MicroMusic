// Diagnostic 16-KB target only; not an ATmega64A memory or playback claim.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=resolve(root,'../../build/codec2/cold-diagnostic');
const meta=JSON.parse(readFileSync(join(build,'build.json'))),memory=meta.memory,hash=b=>createHash('sha256').update(b).digest('hex');
const binary=readFileSync(join(build,'decoder.bin')),input=readFileSync(meta.packet_path),expected=readFileSync(join(build,'native.trace'));
assert.equal(hash(binary),meta.binary_sha256);assert.equal(hash(input),meta.packet_sha256);assert.equal(hash(expected),meta.native_trace_sha256);
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/).map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
const address=n=>{assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;};
const top=address('__stack'),end=address('__bss_end'),status=address('codec2_decode_status'),command=address('codec2_decode_command'),packet=address('codec2_decode_packet'),trace=address('codec2_decoder_trace'),pcm=address('codec2_decode_pcm');assert.equal(top,memory.RAMEND);
const program=new Uint16Array((memory.FLASHEND+1)/2).fill(0xffff);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,top-memory.RAMSTART+1);cpu.SP=top;let minimum=top;
function until(predicate){const deadline=cpu.cycles+150000000;while(!predicate()){assert.ok(cpu.cycles<deadline);avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end-1&&cpu.SP<=top);minimum=Math.min(minimum,cpu.SP);}}
until(()=>cpu.data[status]!==0);assert.equal(cpu.data[status],1);const output=Buffer.alloc(640),actual=Buffer.alloc(1024),differences=[];
for(let frame=0;frame<2;++frame){
  cpu.data.set(input.subarray(frame*8,frame*8+8),packet);cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]!==1);assert.equal(cpu.data[status],2);
  actual.set(cpu.data.subarray(trace,trace+512),frame*512);output.set(cpu.data.subarray(pcm,pcm+320),frame*320);
  for(let half=0;half<2;++half){const fields=[];for(let i=0;i<64;++i){const offset=frame*512+half*256+i*4;if(actual.readUInt32LE(offset)!==expected.readUInt32LE(offset))fields.push({index:i,native:expected.readFloatLE(offset),avr:actual.readFloatLE(offset),nativeBits:expected.readUInt32LE(offset).toString(16),avrBits:actual.readUInt32LE(offset).toString(16)});}differences.push({frame,half,fields});}
}
writeFileSync(join(build,'avr.trace'),actual);writeFileSync(join(build,'avr.pcm'),output);
const record={mcu:'ATmega1284P',frames:2,binarySha256:hash(binary),stackBytes:top-minimum,differences,scope:'Frozen full float reference stage diagnostic only, larger SRAM target, no IRQ. Field indices: Wo0 energy1 voiced2 harmonics3 LSP4..13 LPC14..24 amplitudes25..32 phases33..40 spectrum41..56 state57..63.'};
writeFileSync(join(build,'diagnostic.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({mcu:record.mcu,differences:differences.map(d=>({...d,fields:d.fields.filter(f=>f.index<25)}))}));
