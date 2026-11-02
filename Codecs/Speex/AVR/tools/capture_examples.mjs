// Capture the actual ASM decoder's complete s16 output; never run a C decoder.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const [folder,input,target]=process.argv.slice(2,5).map(v=>resolve(v)),wb=process.argv.includes('--wideband');
const hash=b=>createHash('sha256').update(b).digest('hex');
const meta=JSON.parse(readFileSync(join(folder,'backend.json'))),raw=readFileSync(input);
assert.equal(meta.backend,'asm','Only the target ASM decoder is executed');
const binary=readFileSync(join(folder,wb?'wb.bin':'speex-test.bin'));
assert.equal(hash(binary),meta.binarySha256);assert.equal(raw.length%meta.packetBytes,0);
const symbols=new Map(readFileSync(join(folder,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(s=>s.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [packet,status,command,result,pcm,end]=['speex_test_packet','speex_test_status','speex_test_command','speex_test_result','speex_test_pcm','__bss_end'].map(at);
const chunks=wb?at('speex_test_chunks'):-1;
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);let lastChunk=0,parts=[],minSP=2303;
function until(done){const limit=cpu.cycles+3000000;while(!done()){
 assert.ok(cpu.cycles<limit,'Decoder timeout');avrInstruction(cpu);cpu.tick();
 minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(wb&&cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const p=cpu.dataView.getUint16(pcm,true);parts.push(Buffer.from(cpu.data.subarray(p,p+160)));}
}}
until(()=>cpu.data[status]===1);const frames=raw.length/meta.packetBytes,output=[];
function decode(f){
 parts=[];cpu.data.set(raw.subarray(f*meta.packetBytes,(f+1)*meta.packetBytes),packet);
 cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);assert.equal(cpu.data[result],0);
 if(wb){assert.equal(parts.length,4);return Buffer.concat(parts);}
 return Buffer.from(cpu.data.subarray(pcm,pcm+320));
}
for(let f=0;f<frames;f++)output.push(decode(f));
cpu.data[status]=0;cpu.data[command]=2;until(()=>cpu.data[status]===1);
assert.ok(decode(0).equals(output[0]),'Reset reproduces the first frame');
const data=Buffer.concat(output);assert.equal(data.length,frames*(wb?640:320));writeFileSync(target,data);
writeFileSync(target+'.json',JSON.stringify({backend:'asm',binarySha256:meta.binarySha256,inputSha256:hash(raw),pcmSha256:hash(data),
 frames,samples:data.length/2,sampleHz:wb?16000:8000,resetExact:true,staticSramBytes:end-256,peakStack:2303-minSP,
 includesInterrupts:false,physicalBoardTested:false,scope:'Actual linked ASM decoder capture; PWM/IRQ checked separately; no C decoder execution'},null,2)+'\n');
console.log('Captured ASM PCM',frames,'frames',data.length/2,'samples');
