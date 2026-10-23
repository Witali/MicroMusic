import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-transpiled.js';
import {AVRCore as Reference} from '../lib/avr-reference.js';
import {put,rr,sameCPU} from './helpers/avr-test-state.mjs';

test('guarded SRAM/Flash blocks exit with exact flags before I/O, aliases and invalid addresses',()=>{
  const rom=new Uint8Array(1024).fill(255);
  [rr(0x0c00,16,17),0x920d|(18<<4),0x900d|(19<<4),0x9005|(20<<4),rr(0x2400,21,22),0x940a|(23<<4)].forEach((word,n)=>put(rom,16+n,word));
  const a=new AVRCore(rom);
  for(let pointer=0;pointer<=160;pointer++)for(const z of [0,1023,1024]){
    a._call('avr_reset',0,0);const b=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
    for(const c of [a,b]){c.pc=16;c.r[16]=255;c.r[17]=1;c.r[18]=0;c.r[26]=pointer;c.r[30]=z;c.r[31]=z>>8;c.sreg=0xe0;}
    let actualError=null,expectedError=null;
    try{a.run(6);}catch(error){actualError=error.message;}
    try{for(let n=0;n<6;n++)b.step();}catch(error){expectedError=error.message;}
    assert.equal(actualError,expectedError,`pointer ${pointer}, Z ${z}`);sameCPU(a,b,`pointer ${pointer}, Z ${z}`);
  }
});

test('memory blocks preserve exact CPU/timer/IRQ state when each possible instruction meets an event boundary',()=>{
  const rom=new Uint8Array(1024).fill(255);
  [rr(0x0c00,16,17),0x9005|(18<<4),0x920d|(18<<4),0x900d|(19<<4),rr(0x1c00,20,21),0x9407|(22<<4)].forEach((word,n)=>put(rom,16+n,word));
  put(rom,3,0x9518);
  const a=new AVRCore(rom);
  for(const origin of [0,2**32-7])for(let until=1;until<=16;until++){
    a._call('avr_reset',0,0);const b=new Reference(rom,null,{fastIdle:false,fastBlocks:false});
    for(const c of [a,b]){c.pc=16;c.r[16]=255;c.r[17]=1;c.r[26]=100;c.sreg=0x80;c.cyc=origin;c.prescalerAt=origin-3;c.writeIO(0x33,1);c.writeIO(0x39,2);c.overflowAt=origin+until;}
    a.run(6);for(let i=0;i<6;i++)b.step();sameCPU(a,b,`${origin}/${until}`);
  }
});
