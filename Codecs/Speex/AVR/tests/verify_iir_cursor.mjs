// Independent transposed recurrence; sweep every SRAM state-base low byte.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction} from 'avr8js';
const root=fileURLToPath(new URL('../',import.meta.url)),build=join(root,'build/iir');
const symbols=new Map(readFileSync(join(build,'symbols.txt'),'utf8').split(/\r?\n/)
  .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
function address(n){assert.ok(symbols.has(n),n);return symbols.get(n)&0xffff;}
const binary=readFileSync(join(build,'iir.bin')),program=new Uint16Array(16384).fill(0xffff);
new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),status=address('iir_status'),command=address('iir_command');
const samples=address('iir_samples')+2,input=address('iir_input')+2,coef=address('iir_coef');
const preserved=[...Array.from({length:16},(_,i)=>i+2),28,29],entry=address('speex_avr_iir40');
let active=null,returned=0,clipped=0,wraps=0,calls=0,seed=0x5c8711a3;
function random(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;}
function until(predicate){const deadline=cpu.cycles+30000;while(!predicate()){
  assert.ok(cpu.cycles<deadline,'IIR address-sweep timeout');
  if(cpu.pc*2===entry){assert.equal(active,null);active={sp:cpu.SP,cycles:cpu.cycles,regs:preserved.map(r=>cpu.data[r])};}
  avrInstruction(cpu);cpu.tick();assert.ok(cpu.SP>=address('__bss_end'));
  if(active && cpu.SP===active.sp+2){
    assert.deepEqual(preserved.map(r=>cpu.data[r]),active.regs,'Callee-saved registers');
    assert.equal(cpu.data[1],0,'r1 at actual return');returned=cpu.cycles-active.cycles;active=null;
  }
}}
until(()=>cpu.data[status]===1);
const rows=[];
for(const inPlace of [true,false])for(let offset=0;offset<256;offset++){
  const state=address('iir_state_arena')+4+offset;
  assert.ok(state+64<=address('iir_state_arena')+324);
  cpu.data[address('iir_state_offset')]=offset;cpu.data.fill(0,state,state+60);
  cpu.dataView.setUint32(state-4,0x13579bdf,true);cpu.dataView.setUint32(state+60,0x2468ace0,true);
  for(const p of [samples,input]){cpu.dataView.setUint16(p-2,0x1357,true);cpu.dataView.setUint16(p+80,0x2468,true);}
  const mem=new Int32Array(10),den=new Int16Array(10),expected=new Int16Array(40),inputs=new Int16Array(40);
  let min=Infinity,max=0,total=0;
  for(let block=0;block<32;block++){
    for(let j=0;j<10;j++){den[j]=block%3?random():random()%1001-500;cpu.dataView.setInt16(coef+2*j,den[j],true);}
    for(let i=0;i<40;i++){
      inputs[i]=(random()<<16)>>16;cpu.dataView.setInt16((inPlace?samples:input)+2*i,inputs[i],true);
      const raw=inputs[i]+(((mem[0]+4096)|0)>>13),y=Math.max(-32767,Math.min(32767,raw));
      expected[i]=y;clipped+=raw!==y;
      for(let j=0;j<9;j++){const next=mem[j+1]-den[j]*y;mem[j]=next;wraps+=next!==mem[j];}
      mem[9]=-den[9]*y;
    }
    cpu.data[status]=1;cpu.data[command]=inPlace?6:7;until(()=>cpu.data[status]===2);assert.equal(active,null);
    for(let i=0;i<40;i++){
      assert.equal(cpu.dataView.getInt16(samples+2*i,true),expected[i],`base low ${state&255}, mode ${inPlace}, block ${block}, sample ${i}`);
      if(!inPlace)assert.equal(cpu.dataView.getInt16(input+2*i,true),inputs[i]);
    }
    for(let j=0;j<10;j++)assert.equal(cpu.dataView.getInt16(coef+2*j,true),den[j]);
    for(const p of [samples,input]){assert.equal(cpu.dataView.getUint16(p-2,true),0x1357);assert.equal(cpu.dataView.getUint16(p+80,true),0x2468);}
    assert.equal(cpu.dataView.getUint32(state-4,true),0x13579bdf);assert.equal(cpu.dataView.getUint32(state+60,true),0x2468ace0);
    assert.equal(cpu.data[address('iir_zero')],0);min=Math.min(min,returned);max=Math.max(max,returned);total+=returned;calls++;
  }
  rows.push({inPlace,baseLow:state&255,blocks:32,minCycles:min,maxCycles:max,totalCycles:total});
}
assert.equal(calls,16384);assert.ok(clipped>10000 && wraps>1000);
assert.equal(new Set(rows.map(r=>r.baseLow)).size,256);
const report={mcu:'ATmega328P',compiler:'AVR GCC 7.3.0 O3, LTO, fwrapv',simulator:'avr8js 0.21.1',
  binarySha256:createHash('sha256').update(binary).digest('hex'),calls,samples:calls*40,baseLowValues:256,
  inPlace:true,separateInputOutput:true,pageCrossingsCovered:true,clipped,wraps,exact:true,
  calleeSavedRegistersPreserved:true,zeroRegisterRestored:true,guardsIntact:true,inputsAndCoefficientsPreserved:true,
  minKernelCycles:Math.min(...rows.map(r=>r.minCycles)),maxKernelCycles:Math.max(...rows.map(r=>r.maxCycles)),
  totalKernelCycles:rows.reduce((s,r)=>s+r.totalCycles,0),rows,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(build,'cursor-verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,rows:undefined},null,2));
