// ATtiny13(A) supports ADIW/SBIW: device section21 and DS40002198A §§5.3/5.98.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as Wasm} from '../lib/avr-core.js';
const opcode=(subtract,d,k)=>(subtract?0x9700:0x9600)|(((d-24)/2)<<4)|(k&15)|((k&48)<<2);
function expected(x,k,subtract,previous) {
  const total=subtract?x-k:x+k,value=total&65535,negative=value>>>15;
  const signed=x<32768?x:x-65536,signedTotal=subtract?signed-k:signed+k;
  const overflow=Number(signedTotal< -32768||signedTotal>32767);
  return {value,flags:(previous&0xe0)|((negative^overflow)<<4)|(overflow<<3)|(negative<<2)|
    (Number(value===0)<<1)|Number(subtract?total<0:total>65535)};
}
function load(cpu,word,p=0) {cpu.rom[p*2]=word;cpu.rom[p*2+1]=word>>8;cpu.decode(p);}
for(const [engine,Core] of [['JS',JS],['WASM',Wasm]])for(const block of [false,true])for(const subtract of [false,true])
test(`${engine} ${block?'block':'step'} ${subtract?'SBIW':'ADIW'}: all16-bit values and64 immediates`,()=>{
  const cpu=new Core(Uint8Array.of(0,0,255,255),null,{fastIdle:false});
  for(let k=0;k<64;k++) {
    load(cpu,opcode(subtract,24,k));
    for(let x=0;x<65536;x++) {
      const previous=((x>>>8)^k)&255,e=expected(x,k,subtract,previous);
      cpu.pc=cpu.cyc=0;cpu.r[24]=x;cpu.r[25]=x>>8;cpu.sreg=previous;
      if(block)assert.equal(cpu.runBlock(2),true);else cpu.step();
      assert.equal(cpu.r[24]|cpu.r[25]<<8,e.value);assert.equal(cpu.sreg,e.flags);
      assert.equal(cpu.cyc,2);assert.equal(cpu.pc,1);
    }
  }
});
for(const [engine,Core] of [['JS',JS],['WASM',Wasm]])
test(`${engine} word arithmetic: all register-pair encodings, preserved I/T/H, Flash wrap and strict budgets`,()=>{
  const cpu=new Core(Uint8Array.of(0,0),null,{fastIdle:false});
  for(const subtract of [false,true])for(const d of [24,26,28,30])for(const k of [0,1,31,32,63])
    for(const x of [0,1,63,127,255,256,32705,32767,32768,32831,65472,65535])for(let previous=0;previous<256;previous++) {
      load(cpu,opcode(subtract,d,k),511);
      cpu.pc=511;cpu.cyc=0;cpu.r.fill(0x5a);cpu.r[d]=x;cpu.r[d+1]=x>>8;cpu.sreg=previous;
      const before=cpu.r.slice(),e=expected(x,k,subtract,previous);
      assert.equal(cpu.runBlock(1),false);assert.deepEqual(cpu.r,before);assert.equal(cpu.cyc,0);assert.equal(cpu.sreg,previous);
      assert.equal(cpu.runBlock(2),true);assert.equal(cpu.pc,0);assert.equal(cpu.cyc,2);
      before[d]=e.value;before[d+1]=e.value>>8;
      assert.deepEqual(cpu.r,before);assert.equal(cpu.sreg,e.flags);
    }
});
