import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-transpiled.js';
import {rr,immediate,put,out} from './helpers/avr-test-state.mjs';
const image=words=>{const rom=new Uint8Array(1024).fill(255);words.forEach((w,p)=>put(rom,p,w));return rom;};
const wordOp=(op,d,k)=>op|(((d-24)/2)<<4)|(k&15)|((k&48)<<2);

// Independent integer/boolean equations from DS40002198A 5.3/5.45/5.93/5.94/5.98.
test('ADIW/SBIW: all 65536 words and all 64 immediates preserve the documented flags and two-cycle timing',()=>{
  for(const subtract of [false,true]){
    const core=new AVRCore(image(Array.from({length:64},(_,k)=>wordOp(subtract?0x9700:0x9600,24,k))));
    for(let x=0;x<65536;x++)for(let k=0;k<64;k++){
      core.pc=k;core.r[24]=x;core.r[25]=x>>8;core.sreg=0xe0;
      core._translated.step();
      const total=subtract?x-k:x+k,result=total&65535,n=result>>15;
      const overflow=subtract?Number(x>=32768&&result<32768):Number(x<32768&&result>=32768);
      const expected=0xe0|Number(subtract?total<0:total>65535)|(Number(result===0)<<1)|(n<<2)|(overflow<<3)|((n^overflow)<<4);
      assert.equal(core.r[24]|(core.r[25]<<8),result);assert.equal(core.sreg,expected);
    }
    assert.equal(core.cyc,65536*64*2);
  }
  for(const d of [24,26,28,30]){const c=new AVRCore(image([wordOp(0x9600,d,63)]));c.r[d]=250;c.step();assert.equal(c.r[d],57);assert.equal(c.r[d+1],1);}
});

test('SBC/SBCI/CPC: all byte pairs and both C/Z inputs use borrow and chained zero correctly',()=>{
  const cores=[new AVRCore(image([rr(0x0800,16,17)])),new AVRCore(image(Array.from({length:256},(_,k)=>immediate(0x4000,16,k)))),new AVRCore(image([rr(0x0400,16,17)]))];
  for(let type=0;type<3;type++)for(let x=0;x<256;x++)for(let y=0;y<256;y++)for(let flags=0;flags<4;flags++){
    const c=cores[type],carry=flags&1,total=x-y-carry,result=total&255,n=result>>7;
    c.pc=type===1?y:0;c.r[16]=x;c.r[17]=y;c.sreg=flags|0xc0;c._translated.step();
    const overflow=Number(((x^y)&(x^result)&128)!==0);
    const expected=0xc0|Number(total<0)|((Number(result===0)&(flags>>1))<<1)|(n<<2)|(overflow<<3)|((n^overflow)<<4)|(Number((x&15)<(y&15)+carry)<<5);
    assert.equal(c.r[16],type===2?x:result);assert.equal(c.sreg,expected);
  }
});

test('BST/BLD: every register, bit and byte transfers T without changing other flags',()=>{
  const rom=image([]);for(let d=0;d<32;d++)for(let b=0;b<8;b++){put(rom,d*8+b,0xfa00|(d<<4)|b);put(rom,256+d*8+b,0xf800|(d<<4)|b);}
  const c=new AVRCore(rom);
  for(let d=0;d<32;d++)for(let b=0;b<8;b++)for(let value=0;value<256;value++){
    c.pc=d*8+b;c.r[d]=value;c.sreg=0xbf;c._translated.step();assert.equal(c.sreg,0xbf|(((value>>b)&1)<<6));assert.equal(c.r[d],value);
    for(const t of [0,1]){c.pc=256+d*8+b;c.r[d]=value;c.sreg=0xbf|(t<<6);c._translated.step();assert.equal(c.r[d],(value&~(1<<b))|(t<<b));assert.equal(c.sreg,0xbf|(t<<6));}
  }
});

test('CPSE/SBIC/SBIS skip one or two words and observe I/O at the completing CPU cycle',()=>{
  for(const opcode of [rr(0x1000,16,17),0x9900|(5<<3)|2,0x9b00|(5<<3)|2])for(const wide of [false,true])for(const take of [false,true]){
    const c=new AVRCore(image([opcode,wide?0x9200:0,0]));c.r[16]=1;c.r[17]=take?1:2;
    c.io[5]=(opcode&0xff00)===0x9900?(take?0:4):(take?4:0);c.sreg=0xd5;c.step();
    assert.equal(c.pc,take?(wide?3:2):1);assert.equal(c.cyc,take?(wide?3:2):1);assert.equal(c.sreg,0xd5);
  }
  // EEMPE expires during the first cycle. SBIC must observe the cleared bit.
  const c=new AVRCore(image([0x9900|(0x1c<<3)|2,0,0]));c.io[0x1c]=4;c.eempeUntil=1;
  c.step();assert.equal(c.pc,2);assert.equal(c.cyc,2);
});

test('IJMP/ICALL use word-addressed Z, the 9-bit PC and the observable AVR SRAM return stack',()=>{
  const c=new AVRCore(image([0x9409,0x9509,0,0x9508]));c.r[30]=1;c.r[31]=0xfe;c.sreg=0x73;c.step();
  assert.equal(c.pc,1);assert.equal(c.cyc,2);c.r[30]=3;c.r[31]=0;c.step();assert.equal(c.pc,3);assert.equal(c.sp,157);
  assert.equal(c.data[159],2);assert.equal(c.data[158],0);c.step();assert.equal(c.pc,2);assert.equal(c.sp,159);assert.equal(c.cyc,9);assert.equal(c.sreg,0x73);
});

test('operandless LPM and CBI have their own real encodings, preserved SREG and exact cycles',()=>{
  const c=new AVRCore(image([0x95c8,0x9800|(5<<3)|2]));c.r[30]=1;c.io[5]=255;c.sreg=0xa7;c.step();assert.equal(c.r[0],0x95);assert.equal(c.cyc,3);
  c.step();assert.equal(c.io[5],251);assert.equal(c.cyc,5);assert.equal(c.sreg,0xa7);
});

test('MCU instructions use a boundary protocol, never WASM-to-JS callbacks or silent active-device no-ops',()=>{
  const c=new AVRCore(image([0x9588,0x95a8,0x9598,0x95e8,0]));c.sreg=0xa7;
  c.run(3);assert.equal(c.pc,3);assert.equal(c.cyc,3);assert.equal(c.watchdogResetCycle,2);assert.equal(c.sreg,0xa7);
  assert.throws(()=>c.step(),/Flash-controller/);assert.equal(c.pc,4);assert.equal(c.cyc,3);assert.equal(c.controlRequest,2);
  assert.throws(()=>c.acknowledgeControl(),/cycle count/);c.acknowledgeControl(123);c.step();assert.equal(c.cyc,127);
  const sleep=new AVRCore(image([0x9588,0]));sleep.io[0x35]=32;assert.throws(()=>sleep.run(2),/sleep\/wake/);assert.equal(sleep.pc,1);assert.equal(sleep.cyc,1);
  assert.throws(()=>sleep.step(),/sleep\/wake/);assert.equal(sleep.pc,1);sleep.acknowledgeControl(256);sleep.step();assert.equal(sleep.cyc,258);
  const debug=new AVRCore(image([0x9598,0]));debug.debugEnabled=true;assert.throws(()=>debug.run(2),/stopped at BREAK/);assert.equal(debug.pc,1);debug.acknowledgeControl();debug.step();assert.equal(debug.cyc,2);
  const watchdog=new AVRCore(image([0x95a8,0]));watchdog.io[0x21]=8;assert.throws(()=>watchdog.run(2),/watchdog/);assert.equal(watchdog.pc,1);assert.equal(watchdog.cyc,1);
});

test('optimized blocks account for two-cycle word operations and carry/T/Z dependencies',()=>{
  const rom=image([]),words=[immediate(0xe000,16,1),rr(0x1800,17,18),rr(0x0800,19,20),rr(0x0400,21,22),wordOp(0x9600,24,63),
    0xfa00|(24<<4)|7,0xf800|(25<<4)|0,wordOp(0x9700,26,63),rr(0x1c00,28,29),0xcff6];
  words.forEach((w,n)=>put(rom,16+n,w));
  const fast=new AVRCore(rom),exact=new AVRCore(rom,null,{optimizeFlags:false});
  let seed=0x13a;const random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;};
  for(let trial=0;trial<100;trial++){
    for(const c of [fast,exact]){c.pc=16;c.cyc=0;c.sreg=trial;}
    const registers=Uint8Array.from({length:32},()=>random()&255);fast.r.set(registers);exact.r.set(registers);
    fast.run(200);for(let i=0;i<200;i++)exact.step();assert.deepEqual(fast.data,exact.data);assert.equal(fast.pc,exact.pc);assert.equal(fast.cyc,exact.cyc);
  }
});
