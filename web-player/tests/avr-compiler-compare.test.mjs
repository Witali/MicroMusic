import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as WASM} from '../lib/avr-core.js';
const bytes=words=>Uint8Array.from(words.flatMap(w=>[w&255,w>>8]));
const rr=(base,d,s)=>base|(d<<4)|(s&15)|((s&16)<<5);
for(const Core of [JS,WASM]){
 test(Core.name+': CPC propagates carry and multi-byte zero without writing registers',()=>{
  const core=new Core(bytes([rr(0x0400,16,17)]),new Uint8Array(64),{target:'attiny88'});
  for(const [a,b,carry,zero] of [[0,0,0,1],[0,0,0,0],[0,0,1,1],[128,0,1,1],[255,255,0,1]]){
   core.pc=0;core.r[16]=a;core.r[17]=b;core.sreg=(zero<<1)|carry;
   core.step();const total=a-b-carry,result=total&255;
   assert.equal(core.r[16],a);assert.equal(core.r[17],b);
   assert.equal(core.z,Number(zero&&result===0));assert.equal(core.c,Number(total<0));
   assert.equal((core.sreg>>2)&1,result>>7);
  }
 });
 test(Core.name+': CPSE skips both one- and two-word instructions and preserves SREG',()=>{
  for(const next of [[0xe001],[0x9100,0x100]])for(const equal of [false,true]){
   const core=new Core(bytes([rr(0x1000,16,17),...next,0]),new Uint8Array(64),{target:'attiny88'});
   core.r[16]=9;core.r[17]=equal?9:10;core.sreg=0x75;
   core.step();assert.equal(core.pc,equal?1+next.length:1);
   assert.equal(core.cyc,equal?1+next.length:1);assert.equal(core.sreg,0x75);
  }
 });
}
