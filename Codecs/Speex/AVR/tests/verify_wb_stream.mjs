// Full unbroken decoder history + actual production PWM/IRQ/queue functions.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';
import {CPU,avrInstruction,AVRTimer,timer1Config,timer2Config} from 'avr8js';
import {tickAvr} from './avr_tick.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
function option(n,f){const i=process.argv.indexOf(n);return i<0?f:resolve(process.argv[i+1]);}
const dir=option('--firmware',join(root,'build/angle-wb-stream-32')),streams=option('--streams',join(root,'build/higher-corpus/wb128/streams'));
const oracle=option('--oracle',join(root,'build/higher-corpus/wb128/oracle'));
const metadata=JSON.parse(readFileSync(join(dir,'backend.json'),'utf8')),width=metadata.packetBytes;
assert.ok([25,32].includes(width));assert.equal(metadata.backend,'asm');
const binary=readFileSync(join(dir,'wb.bin'));assert.ok(binary.length<=32768);assert.equal(createHash('sha256').update(binary).digest('hex'),metadata.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&65535;}
const [packetAddress,pwmAddress,command,status,last,chunks,pcm,count,started,done,error,underruns,head,tail,finished,end]=[
 'stream_packet_address','stream_pwm_address','stream_command','stream_status','stream_last','stream_chunks','stream_pcm','stream_samples',
 'speex_player_started','speex_player_done','speex_player_error','speex_player_underruns','head','tail','input_finished','__bss_end'].map(address);
const loadBegin=metadata.frameLoadCycles?address('speex_player_load_begin'):-1,loadEnd=metadata.frameLoadCycles?address('speex_player_load_end'):-1;
const reports=[];
for(const name of readdirSync(streams).filter(n=>n.endsWith('.spxraw')).sort()){
 const raw=readFileSync(join(streams,name)),expected=readFileSync(join(oracle,name.replace('.spxraw','.pcm'))),frames=raw.length/width;
 assert.ok(Number.isInteger(frames)&&frames>0);assert.equal(expected.length,frames*640);
 const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);const cpu=new CPU(program,2048);
 new AVRTimer(cpu,timer1Config);new AVRTimer(cpu,timer2Config);
 let minSP=2303,oldChunks=0,parts=[],minQueue=127,loadActive=false,loadCycles=0;const samples=[],times=[],loads=[];
 function until(predicate){const deadline=cpu.cycles+3000000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'WB stream timeout '+name+' PC='+cpu.pc*2);assert.equal(cpu.data[error],0,'Decode status');
  const pc=cpu.pc*2,before=cpu.cycles,previouslyEnabled=cpu.interruptsEnabled;
  if(pc===loadBegin){assert.equal(loadActive,false);loadActive=true;loadCycles=0;}
  avrInstruction(cpu);
  if(pc>=loadBegin&&pc<loadEnd)loadCycles+=cpu.cycles-before;
  if(loadActive&&cpu.pc*2===loadEnd){loads.push(loadCycles);loadActive=false;}
  tickAvr(cpu,previouslyEnabled);
  minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'Static/stack collision');
  if(cpu.data[chunks]!==oldChunks){oldChunks=cpu.data[chunks];assert.equal(cpu.data[count],80);const ptr=cpu.dataView.getUint16(pcm,true);parts.push(Buffer.from(cpu.data.subarray(ptr,ptr+160)));}
 }}
 until(()=>cpu.data[status]===1);
 const packet=cpu.dataView.getUint16(packetAddress,true),pwm=cpu.dataView.getUint16(pwmAddress,true);assert.ok(packet>=256&&packet+width<=end);
 const previous=cpu.writeHooks[pwm];cpu.writeHooks[pwm]=(value,old,at,mask)=>{
  if(cpu.data[started]){samples.push(value);times.push(cpu.cycles);if(!cpu.data[finished])minQueue=Math.min(minQueue,(cpu.data[head]-cpu.data[tail])&127);}
  return previous?.(value,old,at,mask)??false;
 };
 for(let f=0;f<frames;f++){
  until(()=>cpu.data[status]===1);cpu.data.set(raw.subarray(f*width,(f+1)*width),packet);cpu.data[last]=Number(f+1===frames);
  parts=[];cpu.data[command]=1;until(()=>cpu.data[status]===2);
  assert.equal(parts.length,4);assert.ok(Buffer.concat(parts).equals(expected.subarray(f*640,(f+1)*640)),name+' s16 frame '+f);
 }
 until(()=>cpu.data[done]===1);assert.equal(cpu.dataView.getUint16(underruns,true),0,name+' underruns');
 const expectedPwm=Buffer.from(Array.from({length:expected.length/2},(_,i)=>expected[2*i+1]^128));
 assert.equal(samples.length,expectedPwm.length+1,'One intentional final midpoint');assert.equal(samples.at(-1),128);
 assert.ok(Buffer.from(samples.slice(0,-1)).equals(expectedPwm),name+' PWM exact');
 const intervals=times.slice(1,-1).map((t,i)=>t-times[i]);
 const minimum=intervals.reduce((a,b)=>Math.min(a,b),Infinity),maximum=intervals.reduce((a,b)=>Math.max(a,b),0);
 assert.ok(minimum>=990&&maximum<=1010,'16-kHz output interval');assert.equal(loads.length,metadata.frameLoadCycles?frames:0);
 for(const cycles of loads)assert.equal(cycles,metadata.frameLoadCycles,'Foreground load excluding ISR cycles');
 const row={stream:name,frames,inputSha256:createHash('sha256').update(raw).digest('hex'),pcmSha256:createHash('sha256').update(expected).digest('hex'),
  fullHistoryWithoutChunkReset:true,s16AndPwmExact:true,underruns:0,minQueuedSamplesBeforeOutput:minQueue,freeSramAtPeak:minSP-end+1,peakStackBytes:2303-minSP,
  timerIntervalMinCycles:minimum,timerIntervalMaxCycles:maximum,measuredLoads:loads.length};reports.push(row);console.log('PASS full history',name,frames,'frames, min queue',minQueue,'free',row.freeSramAtPeak);
}
const result={binarySha256:metadata.binarySha256,packetBytes:width,flashBytes:binary.length,staticSramBytes:end-256,includesInterrupts:true,
 simulator:'avr8js 0.21.1 + tests/avr_tick.mjs',physicalBoardTested:false,extraCpuCyclesPerFrame:metadata.frameLoadCycles,
 scope:'Ready RAM packets supplied by host; production IRQ/queue reused; no transport delay modeled; no resets inside a recording',
 frames:reports.reduce((a,b)=>a+b.frames,0),underruns:0,minQueuedSamplesBeforeOutput:Math.min(...reports.map(r=>r.minQueuedSamplesBeforeOutput)),
 freeSramAtPeak:Math.min(...reports.map(r=>r.freeSramAtPeak)),streams:reports};
writeFileSync(join(dir,'verification.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({...result,streams:reports.length}));
