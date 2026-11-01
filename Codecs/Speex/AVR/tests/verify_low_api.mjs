// Variable-size calls, all enabled modes, error guards, padding and reset.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),input=resolve(process.argv[3]);
const meta=JSON.parse(readFileSync(join(dir,'backend.json'))),data=JSON.parse(readFileSync(join(input,'input.json')));
const binary=readFileSync(join(dir,'api.bin')),raw=readFileSync(join(input,'packets32.bin')),expected=readFileSync(join(input,'oracle.pcm'));
const hash=b=>createHash('sha256').update(b).digest('hex');
assert.equal(hash(binary),meta.binarySha256);assert.equal(hash(raw),data.inputSha256);assert.equal(hash(expected),data.pcmSha256);
assert.equal(meta.wideband,data.wideband);assert.equal(raw.length,data.frames*32);
const size=meta.wideband?640:320;assert.equal(expected.length,data.frames*size);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const address=name=>{assert.ok(symbols.has(name),name);return symbols.get(name);};
const [packet,bytes,flags,command,status,result,pcm,end]=['low_api_packet','low_api_bytes','low_api_flags','low_api_command','low_api_status','low_api_result','low_api_pcm','__bss_end'].map(address);
const chunks=meta.wideband?address('low_api_chunks'):-1;
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);let output=[],lastChunk=0,minSP=2303,rejected=0;
function until(predicate){const deadline=cpu.cycles+3000000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'API timeout');avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(meta.wideband&&cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const at=cpu.dataView.getUint16(pcm,true);output.push(Buffer.from(cpu.data.subarray(at,at+160)));}
}}
until(()=>cpu.data[status]===1);
function decode(payload,width,invalidFlags=0){
 cpu.data.set(payload,packet);cpu.data[bytes]=width;cpu.data[flags]=invalidFlags;
 output=[];cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.ok(Buffer.from(cpu.data.subarray(packet,packet+32)).equals(payload),'Read-only packet');
 const code=cpu.dataView.getInt8(result);
 return {code,pcm:meta.wideband?Buffer.concat(output):Buffer.from(cpu.data.subarray(pcm,pcm+320)),callbacks:output.length};
}
function reject(payload,width,badFlags=0){const answer=decode(payload,width,badFlags);assert.equal(answer.code,-1);assert.equal(answer.callbacks,0);rejected++;}
for(let f=0;f<data.frames;f++){
 const payload=Buffer.from(raw.subarray(f*32,(f+1)*32)),width=data.packetLengths[f];
 reject(payload,0);reject(payload,width-1);reject(payload,width+1);reject(payload,width,1);reject(payload,width,2);
 const bad=Buffer.from(payload);bad[0]|=248;reject(bad,width);
 if(meta.wideband){const broken=Buffer.from(payload),bit=data.meaningfulBits[f]-36;broken[bit>>3]^=1<<(7-(bit&7));reject(broken,width);}
 if(f&1){const padding=width*8-data.meaningfulBits[f];if(padding)payload[width-1]^=(1<<padding)-1;}
 const answer=decode(payload,width);assert.equal(answer.code,0,'valid mixed frame '+f);
 assert.ok(answer.pcm.equals(expected.subarray(f*size,(f+1)*size)),'Mixed PCM after rejected calls '+f);
 if(meta.wideband)assert.equal(answer.callbacks,4);
}
cpu.data[command]=2;cpu.data[status]=0;until(()=>cpu.data[status]===1);
const fresh=decode(Buffer.from(raw.subarray(0,32)),data.packetLengths[0]);assert.equal(fresh.code,0);assert.ok(fresh.pcm.equals(expected.subarray(0,size)),'Reset first frame');
const report={backend:'asm',wideband:meta.wideband,binarySha256:meta.binarySha256,inputSha256:data.inputSha256,pcmSha256:data.pcmSha256,
 frames:data.frames,rejectedCalls:rejected,mixedEnabledModes:[1,2,8,3,4],paddingIgnored:true,resetExact:true,pcmExact:true,
 includesInterrupts:false,physicalBoardTested:false,flashBytes:binary.length,staticSramBytes:end-256,peakStack:2303-minSP,freeSram:minSP-end+1};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS mixed API',JSON.stringify(report));
