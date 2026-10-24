// Exact PCM of the compact WB profile; no timer/ISR in this decoder harness.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url));
function option(name,fallback){const i=process.argv.indexOf(name);return i<0?fallback:resolve(process.argv[i+1]);}
const bi=process.argv.indexOf('--backend'),backend=bi<0?'asm':process.argv[bi+1];
assert.ok(['asm','c'].includes(backend));
const dir=option('--firmware',join(root,'build/wb-'+backend+'-decoder'));
const streams=option('--streams',join(root,'build/wb-corpus/streams'));
const oracle=option('--oracle',join(root,'build/wb-corpus/oracle'));
const fi=process.argv.indexOf('--frames'),limit=fi<0?Infinity:Number(process.argv[fi+1]);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const names=['speex_test_packet','speex_test_status','speex_test_command','speex_test_result','speex_test_chunks','speex_test_pcm','__bss_end'];
const [packet,status,command,result,chunks,pcm,end]=names.map(address);
const binary=readFileSync(join(dir,'wb.bin')),metadata=JSON.parse(readFileSync(join(dir,'backend.json')));
assert.equal(metadata.backend,backend);assert.ok(binary.length<=32768);
assert.equal(createHash('sha256').update(binary).digest('hex'),metadata.binarySha256);
for(const table of ['high_lsp_cdbk','high_lsp_cdbk2','nb3_gain_table'])assert.ok(symbols.get(table)<32768,table+' in Flash');
for(const name of ['malloc','calloc','realloc','free'])assert.ok(!symbols.has(name),'No heap');
if(backend==='c')for(const name of ['speex_wb_iir40_avr','speex_wb_fold40_avr','speex_wb_qmf40_avr','speex_avr_iir40','speex_avr_long_innovation40'])assert.ok(!symbols.has(name),'No ASM in C build');
const report={backend,binarySha256:metadata.binarySha256,includesInterrupts:false,physicalBoardTested:false,flashBytes:binary.length,staticSramBytes:end-256,frames:0,maxCycles:0,minSP:2303,streams:[]};
let totalCycles=0;
for(const name of readdirSync(streams).filter(s=>s.endsWith('.spxraw')).sort()){
 const raw=readFileSync(join(streams,name));assert.equal(raw.length%25,0);
 const expected=readFileSync(join(oracle,name.replace('.spxraw','.pcm')));assert.equal(expected.length,raw.length/25*640);
 const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
 const cpu=new CPU(program,2048);let minSP=2303,lastChunk=0,output=[],hits=new Map();
 function until(predicate){const deadline=cpu.cycles+3000000;while(!predicate()){
   assert.ok(cpu.cycles<deadline,'timeout '+cpu.pc.toString(16));
   if(process.argv.includes('--profile'))hits.set(cpu.pc*2,(hits.get(cpu.pc*2)||0)+1);
   avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
   if(cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const ptr=cpu.dataView.getUint16(pcm,true);output.push(Buffer.from(cpu.data.subarray(ptr,ptr+160)));}
 }}
 until(()=>cpu.data[status]===1);
 const cycles=[];const frames=Math.min(raw.length/25,limit);
 for(let f=0;f<frames;f++){
   output=[];cpu.data.set(raw.subarray(f*25,f*25+25),packet);cpu.data[status]=1;cpu.data[command]=1;
   const start=cpu.cycles;until(()=>cpu.data[status]===2);cycles.push(cpu.cycles-start);
   assert.equal(cpu.data[result],0,name+' result');assert.equal(output.length,4);
   const actual=Buffer.concat(output),exp=expected.subarray(f*640,(f+1)*640);
   if(!actual.equals(exp)){
     const i=[...actual].findIndex((v,i)=>v!==exp[i])&~1;
     throw Error(`${name} frame ${f} sample ${i/2}: ${actual.readInt16LE(i)} != ${exp.readInt16LE(i)}`);
   }
 }
 cpu.data[command]=2;cpu.data[status]=0;until(()=>cpu.data[status]===1);
 output=[];cpu.data.set(raw.subarray(0,25),packet);cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.ok(Buffer.concat(output).equals(expected.subarray(0,640)),'reset '+name);
 const row={name,frames,minCycles:Math.min(...cycles),maxCycles:Math.max(...cycles),meanCycles:Math.round(cycles.reduce((a,b)=>a+b,0)/frames),peakStack:2303-minSP,freeSram:minSP-end+1,reset:true,pcmExact:true};
 report.streams.push(row);report.frames+=frames;report.maxCycles=Math.max(report.maxCycles,row.maxCycles);report.minSP=Math.min(report.minSP,minSP);totalCycles+=cycles.reduce((a,b)=>a+b,0);
 console.log(JSON.stringify(row));
 if(process.argv.includes('--profile'))writeFileSync(join(dir,'profile.json'),JSON.stringify([...hits]));
}
report.meanCycles=totalCycles/report.frames;report.peakStack=2303-report.minSP;report.freeSram=report.minSP-end+1;
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
