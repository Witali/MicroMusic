// Independent expectations from Microchip DS40002198A: CP, NEG and §§5.66–68,
// 5.114–116. Exercise both production engines, including the peripheral bus.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {arithmeticFlags} from './helpers/avr-expectations.mjs';
const rr=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
const displacement=q=>(q&7)|((q&24)<<7)|((q&32)<<8);

for(const [engine,Core] of [['WASM',Wasm],['JS',JS]]) {
  const cpu=word=>new Core(Uint8Array.of(word&255,word>>8),null,{fastIdle:false});
  test(`${engine} CP compares every byte pair without changing either operand`,()=>{
    const c=cpu(rr(0x1400,17,18));
    for(let a=0;a<256;a++)for(let b=0;b<256;b++) {
      c.pc=c.cyc=0;c.r[17]=a;c.r[18]=b;c.sreg=0xff;c.step();
      assert.equal(c.r[17],a);assert.equal(c.r[18],b);
      assert.equal(c.sreg,arithmeticFlags(a,b,0,true,0xff));
      assert.equal(c.cyc,1);
    }
  });
  test(`${engine} NEG checks every byte and initial SREG, including zero and -128`,()=>{
    const c=cpu(0x9511);
    for(let a=0;a<256;a++)for(let flags=0;flags<256;flags++) {
      c.pc=c.cyc=0;c.r[17]=a;c.sreg=flags;c.step();
      const v=(-a)&255,n=v>>7,overflow=Number(v===128);
      const expected=(flags&0xc0)|(((v|a)&8)?32:0)|((n^overflow)<<4)|
        (overflow<<3)|(n<<2)|(Number(v===0)<<1)|Number(v!==0);
      assert.equal(c.r[17],v);assert.equal(c.sreg,expected);assert.equal(c.cyc,1);
    }
  });
  for(const [pointer,plain,post,pre] of [[26,0x900c,0x900d,0x900e],
      [28,0x8008,0x9009,0x900a],[30,0x8000,0x9001,0x9002]]) {
    for(const store of [false,true])test(`${engine} ${store?'ST':'LD'} pointer ${pointer}: plain, increment and decrement`,()=>{
      for(const [base,delta] of [[plain,0],[post,1],[pre,-1]])for(const address of [97,112,158]) {
        const c=cpu(base|(16<<4)|(store?0x200:0));
        c.r[pointer]=address;c.r[16]=0xa5;c.sreg=0x73;
        const effective=address+(delta<0?-1:0);if(!store)c.data[effective]=0x6d;
        c.step();assert.equal(store?c.data[effective]:c.r[16],store?0xa5:0x6d);
        assert.equal(c.r[pointer]|c.r[pointer+1]<<8,address+delta);
        assert.equal(c.sreg,0x73);assert.equal(c.cyc,2);assert.equal(c.pc,1);
      }
      for(const base of [post,pre])for(const reg of [pointer,pointer+1]) {
        const c=cpu(base|(reg<<4)|(store?0x200:0));c.r[pointer]=100;
        assert.throws(()=>c.step(),/Undefined/);
      }
      const invalid=cpu(pre|(16<<4)|(store?0x200:0));
      assert.throws(()=>invalid.step(),/out of range/);
    });
  }
  for(const pointer of [28,30])for(const store of [false,true]) {
    test(`${engine} ${store?'STD':'LDD'} pointer ${pointer}: all 64 displacements and flag values`,()=>{
      for(let q=0;q<64;q++) {
        const c=cpu(0x8000|(pointer===28?8:0)|(store?0x200:0)|(16<<4)|displacement(q));
        for(let flags=0;flags<256;flags++) {
          c.pc=c.cyc=0;c.r[pointer]=96;c.r[pointer+1]=0;c.r[16]=0x35;c.data[96+q]=0x72;c.sreg=flags;
          c.step();assert.equal(store?c.data[96+q]:c.r[16],store?0x35:0x72);
          assert.equal(c.r[pointer],96);assert.equal(c.sreg,flags);assert.equal(c.cyc,2);
        }
      }
    });
  }
  test(`${engine} indirect I/O observes the final access cycle and PWM/TOV0 side effects`,()=>{
    const c=cpu(0x910c); // LD r16,X
    c.writeIO(0x33,1);c.r[26]=0x52;c.step();
    assert.equal(c.r[16],2,'TCNT0 read occurs after two instruction clocks');
    const d=cpu(0x930a); // ST -Y,r16
    d.writeIO(0x2f,35);d.writeIO(0x33,1);d.r[28]=0x4a;d.r[16]=201;d.step();
    assert.equal(d.duty,201);assert.equal(d.writes,1);assert.equal(d.r[28],0x49);
    const e=cpu(0x8308|displacement(2)); // STD Y+2,r16
    e.r[28]=0x56;e.io[0x38]=14;e.r[16]=2;e.step();
    assert.equal(e.io[0x38],12,'TOV0 uses write-one-to-clear through displacement');
  });
  test(`${engine} ATtiny13A indirect data access ignores and preserves every XH/YH/ZH value`,()=>{
    for(const [pointer,plain,post,pre] of [[26,0x900c,0x900d,0x900e],
        [28,0x8008,0x9009,0x900a],[30,0x8000,0x9001,0x9002]]) {
      for(const store of [false,true])for(const [base,delta] of [[plain,0],[post,1],[pre,-1]]) {
        const c=cpu(base|(16<<4)|(store?0x200:0));
        for(let high=0;high<256;high++) {
          c.pc=c.cyc=0;c.r[pointer]=100;c.r[pointer+1]=high;c.r[16]=0x59;
          const address=100+(delta<0?-1:0);c.data[address]=0xa3;
          // Post-increment also exercises the optimized executor; others use step().
          if(!c.runBlock())c.step();
          assert.equal(store?c.data[address]:c.r[16],store?0x59:0xa3);
          assert.equal(c.r[pointer],100+delta);assert.equal(c.r[pointer+1],high);
        }
      }
    }
  });
}
