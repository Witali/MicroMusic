import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {AVRCore} from '../lib/avr-core.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {Renderer} from '../lib/renderer.js';
import {ReferenceRenderer} from './helpers/reference-audio.mjs';
import {sameCPU,snapshot,rr,immediate,out,put,program,advance} from './helpers/avr-test-state.mjs';

// fmin ignores a single NaN; this is deliberately independent of the proposed
// comparison sequence. Signed zero never permits an instruction to execute.
const minimumNumber=(a,b)=>Number.isNaN(a)?b:Number.isNaN(b)?a:Math.min(a,b);
for(const [name,word,cycles] of [['NOP',0,1],['LD X+',0x900d,2],['LPM Z',0x9004,3]])
test('block budget '+name+': strict boundaries, fractional limits, NaN/Infinity and large clocks',()=>{
  const rom=new Uint8Array(1024);for(let p=0;p<512;p++)put(rom,p,word);
  const c=new AVRCore(rom,null,{fastIdle:false});
  const distances=[-Infinity,-1,-0,0,.5,.999,1,1.5,2,3,63,63.5,64,65,66,Infinity,NaN];
  for(const origin of [0,2**31-32,2**32-32,2**48-32]){
    for(const overflow of distances)for(const limit of distances){
      c.pc=16;c.cyc=origin;c.overflowAt=origin+overflow;c.r[26]=96;c.r[27]=0;c.r[30]=32;c.r[31]=0;
      c.sreg=0xa5;const deadline=origin+limit;
      const budget=minimumNumber(64,minimumNumber(c.overflowAt-origin-1,deadline-origin));
      const count=Math.max(0,Math.floor(budget/cycles)),before=snapshot(c),instructionsBefore=c.blockInstructions;
      assert.equal(c.runBlock(deadline),count>0,name+' budget '+budget);
      assert.equal(c.pc,(16+count)&511);assert.equal(c.cyc,origin+count*cycles);
      assert.equal(c.blockInstructions,instructionsBefore+count);
      assert.equal(c.sreg,0xa5);assert.equal(c.irqCount,0);assert.equal(c.lost,0);
      if(!count)assert.deepEqual(snapshot(c),before,'Rejected block must not change CPU state');
      if(name==='LD X+')assert.equal(c.r[26],96+count);
    }
  }
});

test('arithmetic block operand encodings, register aliases and preserved flags match hardware formulas',async()=>{
  const {arithmeticFlags}=await import('./helpers/avr-expectations.mjs');
  for(const [name,op,subtract] of [['ADD',0x0c00,false],['ADC',0x1c00,false],['SUB',0x1800,true]]){
    const c=program(AVRCore,[0]);
    for(let d=0;d<32;d++)for(let s=0;s<32;s++)for(const previous of [0,1,0x40,0x81,0xc0,0xff]){
      const word=rr(op,d,s);put(c.rom,16,word);c.decode(16);
      c.pc=16;c.cyc=0;c.r.set(Uint8Array.from({length:32},(_,n)=>(n*37+previous)&255));c.sreg=previous;
      const expected=c.r.slice(),x=expected[d],y=expected[s],carry=name==='ADC'?previous&1:0;
      expected[d]=(subtract?x-y-carry:x+y+carry)&255;
      assert.equal(c.runBlock(),true);assert.deepEqual(c.r,expected);
      assert.equal(c.sreg,arithmeticFlags(x,y,carry,subtract,previous));assert.equal(c.cyc,1);
    }
  }
});

const chain=[...Array.from({length:5},(_,i)=>0x900d|((16+i)<<4)),
  rr(0x0c00,16,18),rr(0x1c00,17,19),immediate(0x5000,20,1),immediate(0x3000,20,127),
  rr(0x0c00,21,22),rr(0x1c00,23,21)];
for(const mode of [0,3])for(const [source,divisor] of [[1,1],[2,8],[3,64],[4,256],[5,1024]])
test('LD/ADD/ADC chains: Timer0 mode '+mode+', /'+divisor+' keeps exact event/IRQ boundaries',()=>{
  for(const origin of [0,2**32-8])for(const delay of [0,1])for(const enabled of [0,1]){
    for(let ticks=1;ticks<=24;ticks++){
      const fast=program(AVRCore,chain,16,true),reference=program(Reference,chain,16,true);
      for(const c of [fast,reference]){
        c.cyc=origin+divisor-1;c.prescalerAt=origin;c.r[26]=96;
        c.sram.set(Uint8Array.from({length:64},(_,i)=>(i*71+ticks)&255));
        c.writeIO(0x2f,mode);c.writeIO(0x33,source);c.writeIO(0x32,(mode===3?255:256)-ticks);
        c.writeIO(0x39,2);c.sreg=0x7f|(enabled<<7);c.irqDelay=delay;
        c.writeIO(0x1c,4);c.writeIO(0x26,128);
      }
      let steps=0;const end=16+chain.length;
      while(fast.pc!==end){
        assert.equal(advance(fast,reference,'mode '+mode+' /'+divisor+' tick '+ticks),null);
        assert.ok(++steps<100,'Program must reach the I/O boundary');
      }
      assert.equal(fast.lost,0);
    }
  }
});

test('LD chains wrap Flash, stop at invalid/aliased pointers and invalidate decoded neighbors',()=>{
  for(const length of [2,5,8])for(const start of [16,511])for(const address of [96,160-length,159,160,65535]){
    for(const alias of [-1,26,27]){
      const words=Array.from({length},(_,i)=>0x900d|((i===1&&alias>=0?alias:16+i)<<4));
      const fast=program(AVRCore,words,start),reference=program(Reference,words,start);
      for(const c of [fast,reference]){
        c.r[26]=address&255;c.r[27]=address>>8;c.sreg=0xff;
        c.sram.set(Uint8Array.from({length:64},(_,i)=>i^0xa5));
      }
      let error=null,n=0;
      while(fast.pc!==((start+length)&511)&&!error){error=advance(fast,reference,'LD chain');assert.ok(++n<20);}
      assert.equal(!!error,address+length>160||alias>=0);
    }
  }
  for(const replacement of [out(0x29),rr(0x1800,17,16),0xffff]){
    const words=[0x910d,0x911d,0x912d,rr(0x0c00,17,18),rr(0x1c00,19,20)];
    const fast=program(AVRCore,words),reference=program(Reference,words);
    for(const c of [fast,reference]){
      c.r[26]=96;put(c.rom,17,replacement);c.decode(17);
    }
    let error=null,n=0;
    while(fast.pc!==21&&!error){error=advance(fast,reference,'decode changed middle instruction');assert.ok(++n<20);}
    assert.equal(!!error,replacement===0xffff);
  }
});

test('legal seeded mixed programs reach every end boundary without early-abort coverage gaps',()=>{
  let seed=0x88a328,random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;};
  const reached=new Set(),operations=new Set();
  for(let run=0;run<48;run++){
    const words=[];
    for(let n=0;n<64;n++){
      const d=random()%24,s=random()%24,k=random()&255;
      const choices=[rr(0x0c00,d,s),rr(0x1c00,d,s),rr(0x1800,d,s),rr(0x2400,d,s),rr(0x2c00,d,s),
        immediate(0xe000,16+d%8,k),immediate(0x3000,16+d%8,k),immediate(0x5000,16+d%8,k),
        0x900d|(d<<4),0x9201|(d<<4),0x9005|(d<<4),0x9407|(d<<4),rr(0x2800,d,s),
        immediate(0x7000,16+d%8,k),0x9403|(d<<4),0x940a|(d<<4)];
      if(n<60)choices.push(0xf400|(1<<3)|(k&7),0xfc00|(d<<4)|(k&7));
      words.push(choices[random()%choices.length]);
    }
    const fast=program(AVRCore,words,16,true),reference=program(Reference,words,16,true);
    const initial=Uint8Array.from({length:160},()=>random()&255);
    for(const c of [fast,reference]){
      c.data.set(initial);c.sp=159;c.r[26]=c.r[30]=96;c.r[27]=c.r[31]=0;
      c.io.fill(0);c.sp=159;c.sreg=0xff;
      const origin=[0,2**31-16,2**32-16,2**48-16][run%4],source=1+run%5,divisor=[0,1,8,64,256,1024][source];
      c.cyc=origin+divisor-1;c.prescalerAt=origin;
      c.writeIO(0x2f,run%2?3:0);c.writeIO(0x33,source);c.writeIO(0x32,run%2?254:255);c.writeIO(0x39,2);
    }
    let n=0;
    while(fast.pc!==80){
      assert.equal(advance(fast,reference,'seed 0x88a328 run '+run+' boundary '+n,core=>{
        reached.add(core.pc);operations.add(core.op[core.pc]);
      }),null);
      assert.ok(++n<200,'Seeded program must finish');
    }
  }
  assert.ok(reached.size>40,'Meaningful instruction-boundary coverage');
  assert.ok(operations.size>=12,'Meaningful mixed-operation coverage');
});

const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
for(const entry of catalog.entries)for(const rate of [22050,44100,48000,96000])
test(entry.id+' '+rate+' Hz: every PCM/raw sample and complete state match JS across irregular blocks',()=>{
  const controls={cutoff:9000,volume:.65},a=new Renderer(entry,rate,controls),b=new ReferenceRenderer(entry,rate,controls);
  const sizes=[1,2,127,128,129,4095,4096,4097,8191,16384];let offset=0,block=0,max=0;
  while(offset<rate*2){
    const count=Math.min(sizes[block++%sizes.length],rate*2-offset),actual=a.render(count),expected=b.render(count);
    assert.deepEqual(a.core.rawSamples,b.rawSamples);
    assert.equal(actual.length,expected.length);
    for(let i=0;i<actual.length;i++)max=Math.max(max,Math.abs(actual[i]-expected[i]));
    sameCPU(a.core,b.core,'audio block '+block);offset+=count;
  }
  assert.ok(max<2e-7,'Full filtered PCM comparison, max error '+max);
  assert.equal(a.core.lost,0);assert.equal(a.core.workLost,0);
  const paused=snapshot(a.core);a.setAudioControls({cutoff:4000,volume:0});
  assert.deepEqual(snapshot(a.core),paused,'Changing controls while paused cannot advance CPU/IRQ clocks');
});
