// Exercise the exact browser CPU/peripheral implementation with a complete
// linked player. The oracle is independent PCM/PWM, not prerecorded playback.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {ATmega328P} from '../lib/atmega328p.js';
import {parseHex} from '../lib/hex.js';

function option(name){
  const index=process.argv.indexOf(name);
  assert.ok(index>=2&&process.argv[index+1]&&!process.argv[index+1].startsWith('--'),`Missing ${name}`);
  return process.argv[index+1];
}
const build=resolve(option('--firmware')),codec=option('--codec');
assert.ok(['lpx','speex'].includes(codec),'Expected LPX or Speex');
const speex=codec==='speex',raw=readFileSync(resolve(option('--oracle')));
const hex=readFileSync(join(build,speex?'speex-player.hex':'player.hex'),'utf8');
const binary=parseHex(hex,32768);
const reportFile=join(build,'web-core-verification.json');
let expected,done,error,end,started,underruns;
if(speex){
  const metadata=JSON.parse(readFileSync(join(build,'input.json'),'utf8'));
  assert.ok([6,10,15,20,28].includes(metadata.packetBytes));
  assert.equal(raw.length,metadata.frames*160*2,'Complete independent Speex s16le oracle');
  const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
    .map(line=>line.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean)
    .map(match=>[match[2],parseInt(match[1],16)&65535]));
  function address(name){assert.ok(symbols.has(name),`Missing production state: ${name}`);return symbols.get(name);}
  started=address('speex_player_started');done=address('speex_player_done');
  error=address('speex_player_error');underruns=address('speex_player_underruns');end=address('__bss_end');
  expected=Buffer.from(Array.from({length:raw.length/2},(_,i)=>raw[2*i+1]^128));
}else{
  const cost=JSON.parse(readFileSync(join(build,'cost.json'),'utf8')).cost;
  assert.equal(raw.length,cost.samples,'Complete independent LPX PWM oracle');
  // player_hardware.cpp derives these addresses from official avr-libc
  // headers and the linked production symbols; it is not linked into Flash.
  const metadata=readFileSync(join(build,'observer.txt'),'utf8').trim().split(/\s+/).map(Number);
  assert.equal(metadata.length,27);
  error=metadata[23];done=metadata[24];end=metadata[26];expected=raw;
}
assert.ok(end>=256&&end<2303,'Static SRAM must leave stack space');
const core=new ATmega328P(binary,null,{target:'atmega328p',cpuHz:16000000,pwmOutput:speex?'OC1A':'OC2B'});
const output=[],times=[];
core.onPwmWrite=(value,cycles)=>{
  if(speex&&!core.data[started])return;
  output.push(value);times.push(cycles);
};
const deadline=expected.length*2000+3000000;
const wallStart=performance.now();
while(!core.data[done]){
  assert.ok(core.cyc<deadline,'Player must finish within its real-time deadline');
  core.step();assert.ok(core.cpu.SP>=end,'Player stack collided with static SRAM');
}
const simulatorWallMs=performance.now()-wallStart;
assert.equal(core.data[error],0,'Decoder error');
if(speex){
  assert.equal(core.data[underruns]|(core.data[underruns+1]<<8),0,'PCM ring underruns');
  assert.equal(output.length,expected.length+1,'One timer write per sample and final midpoint');
  assert.equal(output.pop(),128);times.pop();
}else{
  assert.equal(output.length,expected.length+1,'One initial midpoint and every timer output');
  assert.equal(output.shift(),128);times.shift();
}
assert.deepEqual(Buffer.from(output),expected,'Every browser-core PWM byte must equal the independent oracle');
assert.equal(core.irqCount,expected.length+(speex?1:0),'One timer interrupt per output');
assert.equal(core.timerLost,0,'Lost timer interrupts');
assert.ok(core.pinEdges>expected.length,'The real GPIO PWM output must toggle');
let minimum=Infinity,maximum=0;
for(let i=1;i<times.length;i++){const gap=times[i]-times[i-1];minimum=Math.min(minimum,gap);maximum=Math.max(maximum,gap);}
assert.ok(minimum>=1992&&maximum<=2008,'8 kHz timer output, including IRQ latency');
const report={schemaVersion:1,passed:true,codec,actualWebCore:true,includesInterrupts:true,
  physicalBoardTested:false,cpuHz:16000000,sampleHz:8000,pwmHz:62500,
  flashSha256:createHash('sha256').update(binary).digest('hex'),flashBytes:binary.length,
  samples:expected.length,pwmOutput:core.pwmOutput,playbackCycles:core.cyc,
  simulatorWallMs,
  interrupts:core.irqCount,lostInterrupts:core.timerLost,underruns:0,pinEdges:core.pinEdges,
  minimumStackPointer:core.minimumSP,freeSramAtPeak:core.minimumSP-end,
  peakStackBytes:2303-core.minimumSP,
  timerIntervalMinCycles:minimum,timerIntervalMaxCycles:maximum};
writeFileSync(reportFile,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
