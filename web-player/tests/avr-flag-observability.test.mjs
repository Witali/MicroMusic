import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr} from './helpers/avr-test-state.mjs';
const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false};
const body=[avr.add(16,17),[rr(0x1c00,18,19)],[rr(0x0800,20,21)],[rr(0x0400,22,23)],
  [0x9407|(24<<4)],[rr(0x2000,25,26)],avr.inc(27),avr.eor(28,29)];
function image(instructions=body){const end=16+instructions.flat().length;
  return flash({instructions:[avr.rjmp(0,16)]},{at:16,instructions:[...instructions,avr.rjmp(end,end)]},
    {at:70,instructions:[avr.rjmp(70,18)]});
}
function make(binary=image(),seed=0){
  const c=new ATtiny13A(binary,null,options);c.clock(8);c.pc=16;
  for(let r=0;r<32;r++)c.r[r]=(seed*17+r*29)&255;c.sreg=seed;return c;
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const same=(a,b,label)=>{assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);};
test('every public instruction limit and external block entry exposes full SREG',()=>{
  for(let seed=0;seed<256;seed+=7)for(const pc of [16,18])for(let count=1;count<=8;count++){
    const a=make(undefined,seed),b=make(undefined,seed);a.pc=b.pc=pc;
    assert.equal(a.transpilation.blocks.find(block=>block.start===16).end,18,'the internal leader must actually split the blocks');
    assert.equal(a.run(count),count);for(let n=0;n<count;n++)b.step();same(a,b,'seed'+seed+' pc'+pc+' count'+count);
  }
});
test('half-phase and adjacent1ps observations preserve flags between neighboring blocks',()=>{
  for(let half=0n;half<=16n;half++)for(const delta of [-1n,0n,1n]){
    const offset=half*50000n+delta;if(offset<=0n)continue;
    const a=make(undefined,0x73),b=make(undefined,0x73),end=a.state().timePs+offset;
    a.runUntilPs(end);for(let at=b.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;b.runUntilPs(at);}
    same(a,b,'offset'+offset);
  }
});
test('an IN of SREG observes all flags at a following I/O boundary',()=>{
  const binary=image([body[0],body[1],avr.in(20,IO.SREG)]);
  for(let seed=0;seed<256;seed+=7){const a=make(binary,seed),b=make(binary,seed);
    assert.equal(a.run(3),3);for(let n=0;n<3;n++)b.step();same(a,b,'SREG read seed'+seed);
    assert.equal(a.r[20],a.sreg);
  }
});
