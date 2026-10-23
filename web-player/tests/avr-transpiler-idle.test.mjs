import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-transpiled.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {put,out,rr,immediate,sameCPU} from './helpers/avr-test-state.mjs';

const loops=[
  [0xcfff], // RJMP .
  [0xf7fe], // BRTC .
  [rr(0x2c00,16,17),rr(0x1800,16,18),immediate(0x7000,16,127),immediate(0x3000,16,3),0xf7d8],
];
function firmware(words){
  const rom=new Uint8Array(1024).fill(255);
  words.forEach((word,i)=>put(rom,16+i,word));
  put(rom,3,out(0x29));put(rom,4,0x9518);return rom;
}
function configure(core,origin,until){
  core.pc=16;core.cyc=origin;core.r[17]=15;core.r[18]=4;core.sreg=0x80;
  core.writeIO(0x33,1);core.writeIO(0x39,2);core.overflowAt=origin+until;
}

test('WASM wait-loop acceleration preserves exact timer, flags and IRQ state at every deadline phase',()=>{
  for(const words of loops){
    const rom=firmware(words),actual=new AVRCore(rom);
    for(const origin of [0,2**32-7])for(const until of [1,2,3,5,6,7,127,256]){
      actual._call('avr_reset',1,0);
      const reference=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
      for(const core of [actual,reference])configure(core,origin,until);
      assert.equal(actual.nextDuty(),reference.nextDuty());sameCPU(actual,reference,`${words}/${origin}/${until}`);
      if(until===256)assert.ok(actual.idleCycles>0,'wait loop must actually be skipped');
    }
  }
});

test('instruction-counted run and single step never accelerate waits, even with fastIdle enabled',()=>{
  for(const words of loops){
    const rom=firmware(words),actual=new AVRCore(rom),reference=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
    for(const core of [actual,reference])configure(core,0,1000);
    for(const count of [1,2,3,32,65]){
      actual.run(count);for(let i=0;i<count;i++)reference.step();
      sameCPU(actual,reference);assert.equal(actual.idleCycles,0);
      actual.step();reference.step();sameCPU(actual,reference);assert.equal(actual.idleCycles,0);
    }
  }
});
