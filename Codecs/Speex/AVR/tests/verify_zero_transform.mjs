// Original upstream Q14 decomposition; bounded signed8 shape/positive scale.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/zero-transform-unit');
const binary=readFileSync(join(build,'zero-transform.bin'));
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const program=new Uint16Array(16384).fill(0xffff);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),status=address('zero_status'),command=address('zero_command');
const out=address('zero_output')+2,packed=address('zero_packed');
const cEntry=[...symbols].find(([n])=>/^zero_transform_c(?:\.|$)/.test(n))[1];
const cNEntry=[...symbols].find(([n])=>/^zero_transform_c_n(?:\.|$)/.test(n))[1];
const entries=new Set([address('speex_avr_zero_innovation10'),address('speex_avr_innovation10'),
  address('speex_avr_zero_innovation_n'),cEntry,cNEntry]);
const preserved=[...Array.from({length:16},(_,i)=>i+2),28,29];
const times=[null,...Array.from({length:5},()=>({min:Infinity,max:0,calls:0}))];
const counts=Array.from({length:11},(_,count)=>({count,calls:0,samples:0}));
let active=null,which=0,blocks=0,seed=0x5e70a11,returned=0,pairedSaved=new Set(),largest=0;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function until(predicate){const deadline=cpu.cycles+100000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'Zero-transform timeout');
  if(entries.has(cpu.pc*2)){
    assert.equal(active,null);active={sp:cpu.SP,cycles:cpu.cycles,registers:preserved.map(r=>cpu.data[r])};
  }
  avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=address('__bss_end'));
  if(active && cpu.SP===active.sp+2){
    assert.deepEqual(preserved.map(r=>cpu.data[r]),active.registers,'Callee-saved registers');
    assert.equal(cpu.data[1],0,'r1 at actual return');returned=cpu.cycles-active.cycles;
    times[which].min=Math.min(times[which].min,returned);times[which].max=Math.max(times[which].max,returned);
    times[which].calls++;active=null;
  }
}}
until(()=>cpu.data[status]===1);
function check(scale,index){
  assert.ok(scale>=0 && scale<=121000000);
  const expected=[];
  for(let i=0;i<10;i++){
    const shape=(index+i)%256-128,a=4*shape;
    const q=a*(scale>>14)+Math.floor(a*(scale&16383)/16384);
    const original=((q*128+8192)|0)>>14;
    assert.equal(original,Math.floor((shape*scale+262144)/524288),'Independent zero-gain identity');
    assert.ok(original>=-32767 && original<=32767);largest=Math.max(largest,Math.abs(original));
    expected.push(original);
  }
  cpu.dataView.setInt32(address('zero_scale'),scale,true);cpu.data[address('zero_index')]=index;
  const count=blocks%11;cpu.data[address('zero_count')]=count;
  cpu.data.fill(0,packed,packed+32);cpu.data[packed]=0x56;cpu.data[packed+31]=0x78;
  cpu.dataView.setUint16(out-2,0x1234,true);cpu.dataView.setUint16(out+20,0xabcd,true);
  let zeroCycles=0;
  for(which=1;which<=5;which++){
    cpu.data.fill(0xa5,out,out+20);cpu.data[status]=1;cpu.data[command]=which;
    until(()=>cpu.data[status]===2);assert.equal(active,null);
    const size=which<=3?10:count;
    assert.deepEqual(Array.from({length:10},(_,i)=>cpu.dataView.getInt16(out+2*i,true)),
      expected.map((value,i)=>i<size?value:-23131),'Exact samples and untouched tails');
    assert.equal(cpu.dataView.getUint16(out-2,true),0x1234);assert.equal(cpu.dataView.getUint16(out+20,true),0xabcd);
    assert.equal(cpu.data[packed],0x56);assert.equal(cpu.data[packed+31],0x78);
    assert.ok(cpu.data.subarray(packed+1,packed+31).every(v=>v===0),'Read-only packed zero vector');
    assert.equal(cpu.data[address('zero_r1')],0);
    if(which===1)zeroCycles=returned;
    if(which===3)pairedSaved.add(returned-zeroCycles);
    if(which===4 && count===10)assert.equal(returned-zeroCycles,4,'Runtime count setup cost');
    if(which===4 && count===0)assert.equal(returned,6,'Zero returns without data access');
  }
  counts[count].calls++;counts[count].samples+=count;
  blocks++;
}
const upstream=readFileSync(join(root,'vendor/speex-1.2.1/libspeex/nb_celp.c'),'utf8');
const gains=upstream.match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number);
const correction=upstream.match(/exc_gain_quant_scal1\[2\]=\{([^}]+)\}/)[1].split(',').map(Number);
const scales=gains.flatMap(g=>correction.map(c=>Math.floor(c*Math.floor(28406*g/32768)/16384)));
const edgeScales=[0,1,255,256,4095,4096,65535,65536,16777215,16777216,120988612,121000000];
for(const scale of [...scales,...edgeScales])for(let index=0;index<256;index+=10)check(scale,index);
const gridBlocks=blocks;
function gcd(a,b){while(b)[a,b]=[b,a%b];return a;}
function inverse(a,m){let [t,n,r,s]=[0,1,m,((a%m)+m)%m];while(s){const q=Math.floor(r/s);[t,n]=[n,t-q*n];[r,s]=[s,r-q*s];}assert.equal(r,1);return((t%m)+m)%m;}
for(let shape=-128;shape<=127;shape++)if(shape){
  const g=gcd(Math.abs(shape),524288),period=524288/g;
  const base=(inverse(shape/g,period)*(262144/g))%period;
  for(let repeat=0;repeat<8;repeat++){
    const tie=base+random()%Math.floor((121000000-base)/period+1)*period;
    assert.equal(((shape*tie)%524288+524288)%524288,262144);
    for(const delta of [-1,0,1])if(tie+delta>=0 && tie+delta<=121000000)check(tie+delta,shape+128);
  }
}
const roundingBlocks=blocks-gridBlocks;
for(let i=0;i<20000;i++)check(random()%121000001,random()&255);
assert.equal(times[1].calls,blocks);assert.equal(times[2].calls,blocks);assert.equal(times[3].calls,blocks);
assert.equal(times[4].calls,blocks);assert.equal(times[5].calls,blocks);
assert.ok(counts.every(r=>r.calls>0));assert.equal(times[1].min,501);assert.equal(times[1].max,501);
assert.ok(largest<=29542 && Math.min(...pairedSaved)>0);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0 mixed Os/O2, LTO, fwrapv',simulator:'avr8js 0.21.1',
  binarySha256:createHash('sha256').update(binary).digest('hex'),blocks,samplesPerBackend:blocks*10,
  actualNb3Scales:64,scaleMin:0,scaleMax:121000000,shapeMin:-128,shapeMax:127,
  gridBlocks,roundingBlocks,randomBlocks:20000,largestAbsoluteOutput:largest,exact:true,
  zeroIdentityVerified:true,explicitCWorker:true,guardsIntact:true,packedPitchPreserved:true,
  calleeSavedRegistersPreserved:true,zeroRegisterRestored:true,asmKernelCycles:times[1],
  cKernelCycles:times[2],packedZeroKernelCycles:times[3],pairedAsmCyclesSaved:[...pairedSaved].sort((a,b)=>a-b),
  variableAsmKernelCycles:times[4],variableCKernelCycles:times[5],counts,
  variableSamplesPerBackend:counts.reduce((s,r)=>s+r.samples,0),
  includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
