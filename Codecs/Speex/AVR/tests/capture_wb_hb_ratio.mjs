// Read-only ASM mailbox replay: retain scalar arguments after checking PCM.
// No complete C decoder is executable through this capture tool.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync,mkdirSync} from 'node:fs';
import {join,resolve,dirname} from 'node:path';
import {CPU,avrInstruction} from 'avr8js';

function option(name,required=true){const at=process.argv.indexOf(name);assert.ok(at>=0||!required,name);return at<0?null:process.argv[at+1];}
const firmware=resolve(option('--firmware')),streams=resolve(option('--streams')),oracle=resolve(option('--oracle'));
const destination=resolve(option('--out')),limit=Number(option('--frames',false)??Infinity);
assert.ok(limit>0);
const binary=readFileSync(join(firmware,'wb.bin')),metadata=JSON.parse(readFileSync(join(firmware,'backend.json')));
assert.equal(metadata.backend,'asm','Never execute a complete C decoder');
const hash=data=>createHash('sha256').update(data).digest('hex');assert.equal(hash(binary),metadata.binarySha256);
const symbols=new Map(readFileSync(join(firmware,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
function at(name){assert.ok(symbols.has(name),name);return symbols.get(name);}
const privateEntry=symbols.has('speex_wb_ratio_hb_div_avr');
const entry=at(privateEntry?'speex_wb_ratio_hb_div_avr':'speex_wb_ratio_div_avr');
const [packet,status,command,result,chunks,pcm,end]=['speex_test_packet','speex_test_status','speex_test_command',
 'speex_test_result','speex_test_chunks','speex_test_pcm','__bss_end'].map(at);
const captured=[],records=[];let frameCount=0;
for(const name of readdirSync(streams).filter(n=>n.endsWith('.spxraw')).sort()){
 const raw=readFileSync(join(streams,name)),expected=readFileSync(join(oracle,name.replace('.spxraw','.pcm')));
 const width=metadata.packetBytes;assert.ok([10,15,20,25,32].includes(width));assert.equal(raw.length%width,0);
 assert.equal(expected.length,raw.length/width*640);
 const frames=Math.min(limit,raw.length/width);assert.ok(frames>0);
 const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
 const cpu=new CPU(program,2048);let lastChunk=0,output=[],collecting=false;
 function until(done){const deadline=cpu.cycles+3000000;while(!done()){
  assert.ok(cpu.cycles<deadline);if(collecting&&cpu.pc*2===entry){
   const n=cpu.dataView.getInt32(22,true),d=privateEntry?cpu.dataView.getInt16(20,true):cpu.dataView.getInt32(18,true);
   const half=Number(BigInt.asIntN(16,BigInt(d))>>1n),a=(n-half)/128;
   assert.ok(Number.isInteger(a)&&a>=1&&a<=335949&&d>=111&&d<=31849,'Validated HB1 response');
   captured.push([a,d,n]);
  }
  avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=end);
  if(cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const pointer=cpu.dataView.getUint16(pcm,true);output.push(Buffer.from(cpu.data.subarray(pointer,pointer+160)));}
 }}
 until(()=>cpu.data[status]===1);
 for(let frame=0;frame<frames;frame++){
  output=[];cpu.data.set(raw.subarray(frame*width,(frame+1)*width),packet);cpu.data[status]=1;cpu.data[command]=1;
  collecting=true;until(()=>cpu.data[status]===2);collecting=false;
  assert.equal(cpu.data[result],0);assert.equal(output.length,4);
  assert.ok(Buffer.concat(output).equals(expected.subarray(frame*640,(frame+1)*640)),`${name}/${frame} PCM`);
 }
 cpu.data[command]=2;cpu.data[status]=0;until(()=>cpu.data[status]===1);
 output=[];cpu.data.set(raw.subarray(0,width),packet);cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.ok(Buffer.concat(output).equals(expected.subarray(0,640)),`${name} reset`);
 frameCount+=frames;records.push({name,frames,inputSha256:hash(raw),pcmSha256:hash(expected),pcmAndResetExact:true});
}
assert.equal(captured.length,4*frameCount);
mkdirSync(dirname(destination),{recursive:true});
writeFileSync(destination,JSON.stringify({binarySha256:metadata.binarySha256,
 scalarAbi:privateEntry?'numerator32/divisor16':'numerator32/divisor32',frames:frameCount,streams:records,captured})+'\n');
console.log(JSON.stringify({frames:frameCount,calls:captured.length,asmPcmAndResetExact:true,binarySha256:metadata.binarySha256}));
