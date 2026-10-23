// Microchip DS40002198A §§5.93–94: one cycle; Z is chained with previous Z.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {arithmeticFlags} from './helpers/avr-expectations.mjs';
const rr=(op,d,s)=>op|(d<<4)|(s&15)|((s&16)<<5);
const immediate=k=>0x4000|(1<<4)|(k&15)|((k&240)<<4); // SBCI r17,K

for(const [engine,Core] of [['JS',JS],['WASM',Wasm]])for(const fast of [false,true])for(const form of ['SBC','SBCI']) {
  test(`${engine} ${fast?'block':'step'} ${form}: all operands, carry and previous Z`,()=>{
    const cpu=new Core(Uint8Array.of(0,0,255,255),null,{fastIdle:false});
    for(let b=0;b<256;b++) {
      const word=form==='SBC'?rr(0x0800,17,18):immediate(b);
      cpu.rom[0]=word&255;cpu.rom[1]=word>>8;cpu.decode(0);
      for(let a=0;a<256;a++)for(let carry=0;carry<2;carry++)for(let zero=0;zero<2;zero++) {
        const flags=0xc0|carry|(zero<<1);
        cpu.pc=cpu.cyc=0;cpu.r[17]=a;cpu.r[18]=b;cpu.sreg=flags;
        if(fast)assert.equal(cpu.runBlock(1),true);else cpu.step();
        let expected=arithmeticFlags(a,b,carry,true,flags);
        if(!zero)expected&=~2;
        assert.equal(cpu.r[17],(a-b-carry)&255);assert.equal(cpu.r[18],b);
        assert.equal(cpu.sreg,expected);assert.equal(cpu.cyc,1);assert.equal(cpu.pc,1);
      }
    }
  });
}
