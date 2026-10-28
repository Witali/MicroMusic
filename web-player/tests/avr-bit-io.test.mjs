// Shared AVRe bit operations, including the ATtiny48/88 selected-bit W1C rule.
// Microchip doc8008H, register summary note 3; DS40002198A instruction descriptions.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore as JS} from '../lib/avr-reference.js';
import {AVRCore as Wasm} from '../lib/avr-core.js';
import {AVRCore as Translated} from '../lib/avr-transpiled.js';
import {arithmeticFlags} from './helpers/avr-expectations.mjs';

const image=(...words)=>Uint8Array.from(words.flatMap(w=>[w&255,w>>8]));
function put(cpu,word){cpu.rom[0]=word&255;cpu.rom[1]=word>>8;cpu.decode(0);}
const bitIO=(base,io,bit)=>base|(io<<3)|bit;
for(const [engine,Core] of [['JS',JS],['WASM',Wasm]])for(const fast of [false,true]){
  const mode=`${engine} ${fast?'block/fallback':'step'}`;
  const make=(...words)=>new Core(image(...words),null,{target:'attiny88',cpuHz:16_000_000,fastIdle:false,fastBlocks:fast});
  const execute=cpu=>{if(!(fast&&cpu.runBlock(1)))cpu.step();};

  test(`${mode}: BST/BLD every register, bit, flags and selected value`,()=>{
    const cpu=make(0,0xffff);
    for(const base of [0xfa00,0xf800])for(let reg=0;reg<32;reg++)for(let bit=0;bit<8;bit++){
      put(cpu,base|(reg<<4)|bit);assert.equal(cpu.batch[0],0);
      for(let flags=0;flags<256;flags++)for(const old of [0,255,0x55,0xaa]){
        cpu.pc=cpu.cyc=0;cpu.sreg=flags;cpu.r[reg]=old;execute(cpu);
        assert.equal(cpu.r[reg],base===0xfa00?old:(old&~(1<<bit))|(((flags>>6)&1)<<bit));
        assert.equal(cpu.sreg,base===0xfa00?(flags&~64)|(((old>>bit)&1)<<6):flags);
        assert.equal(cpu.pc,1);assert.equal(cpu.cyc,1);
      }
    }
  });

  test(`${mode}: SBI/CBI preserve unselected bits and flags`,()=>{
    const cpu=make(0,0xffff),address=0x3e,io=address-32; // DFP GPIOR0, ordinary R/W.
    for(const base of [0x9800,0x9a00])for(let bit=0;bit<8;bit++){
      put(cpu,bitIO(base,io,bit));assert.equal(cpu.batch[0],0);
      for(let old=0;old<256;old++){
        const flags=old;cpu.pc=cpu.cyc=0;cpu.sreg=flags;cpu.data[address]=old;execute(cpu);
        assert.equal(cpu.data[address],base===0x9a00?old|(1<<bit):old&~(1<<bit));
        assert.equal(cpu.sreg,flags);assert.equal(cpu.pc,1);assert.equal(cpu.cyc,2);
      }
    }
  });

  test(`${mode}: selected-bit SBI clears only its W1C flag; CBI clears none`,()=>{
    const cpu=make(0,0xffff),{tifr,flagMask}=cpu.profile.timer;
    assert.ok(tifr-32<32);
    for(const base of [0x9800,0x9a00])for(let bit=0;bit<8;bit++){
      put(cpu,bitIO(base,tifr-32,bit));
      for(let old=0;old<256;old++){
        cpu.pc=cpu.cyc=0;cpu.sreg=0x7f;cpu.data[tifr]=old;execute(cpu);
        assert.equal(cpu.data[tifr],base===0x9a00?old&~((1<<bit)&flagMask):old);
        assert.equal(cpu.sreg,0x7f);assert.equal(cpu.cyc,2);
      }
    }
    cpu.data[tifr]=flagMask;cpu.writeIO(tifr-32,flagMask);assert.equal(cpu.data[tifr],0);
    cpu.data[tifr]=flagMask;cpu.writeIO(tifr-32,1,1);assert.equal(cpu.data[tifr],flagMask&~1);
  });

  test(`${mode}: SBIC/SBIS skip one- and two-word instructions in 1/2/3 clocks`,()=>{
    // Long instruction need not execute: test all four two-word encodings.
    const cpu=make(0,0,0,0xffff),io=0x1e,address=io+32;
    for(const base of [0x9900,0x9b00])for(let bit=0;bit<8;bit++)for(const following of [0,0x9000,0x9200,0x940c,0x940e]){
      put(cpu,bitIO(base,io,bit));assert.equal(cpu.batch[0],0);
      cpu.rom[2]=following&255;cpu.rom[3]=following>>8;
      for(let old=0;old<256;old++){
        cpu.pc=cpu.cyc=0;cpu.sreg=old;cpu.data[address]=old;execute(cpu);
        const skip=((old>>bit)&1)===Number(base===0x9b00),words=following?2:1;
        assert.equal(cpu.pc,1+(skip?words:0));assert.equal(cpu.cyc,1+(skip?words:0));
        assert.equal(cpu.data[address],old);assert.equal(cpu.sreg,old);
      }
    }
  });

  test(`${mode}: ADC zero is result-only and NEG supplies half carry`,()=>{
    const cpu=make(0,0xffff);
    put(cpu,0x1c00|(17<<4)|2|0x200); // ADC r17,r18.
    for(const previousZ of [0,2]){
      cpu.pc=cpu.cyc=0;cpu.r[17]=0xff;cpu.r[18]=0;cpu.sreg=0xc1|previousZ;execute(cpu);
      assert.equal(cpu.r[17],0);assert.equal(cpu.sreg,arithmeticFlags(255,0,1,false,0xc1|previousZ));
    }
    put(cpu,0x9401|(17<<4));
    for(let value=0;value<256;value++){
      cpu.pc=cpu.cyc=0;cpu.r[17]=value;cpu.sreg=0xc0;execute(cpu);
      assert.equal(cpu.r[17],(-value)&255);assert.equal(cpu.sreg,arithmeticFlags(0,value,0,true,0xc0));
    }
  });
}

test('JS I/O hooks observe skip read after one clock and selected writes after two',()=>{
  class Observed extends JS{
    readData(a){this.observations.push(['read',this.cyc,a]);return super.readData(a);}
    writeIO(a,v,mask=255){this.observations.push(['write',this.cyc,a,v,mask]);return super.writeIO(a,v,mask);}
  }
  const cpu=new Observed(image(bitIO(0x9900,0x1e,2),0),null,{target:'attiny88',cpuHz:16_000_000,fastIdle:false});
  cpu.observations=[];cpu.step();assert.deepEqual(cpu.observations,[['read',1,0x3e]]);
  put(cpu,bitIO(0x9a00,0x1e,2));cpu.pc=cpu.cyc=0;cpu.observations=[];cpu.step();
  assert.deepEqual(cpu.observations,[['write',2,0x1e,4,4]]);
});

for(const target of ['attiny88'])test(`translated ${target}: bit writes use the same selected-bit W1C bridge`,()=>{
  const probe=new Translated(image(0),null,{target,fastIdle:false});
  const {tifr,flagMask}=probe.profile.timer,io=tifr-32;
  const cpu=new Translated(image(bitIO(0x9a00,io,0),bitIO(0x9800,io,1)),null,{target,fastIdle:false});
  cpu.data[tifr]=flagMask;cpu.sreg=0x55;cpu.step();
  assert.equal(cpu.data[tifr],flagMask&~1);assert.equal(cpu.sreg,0x55);assert.equal(cpu.cyc,2);
  cpu.step();assert.equal(cpu.data[tifr],flagMask&~1);assert.equal(cpu.sreg,0x55);assert.equal(cpu.cyc,4);
});

test('legacy translations reject a precompiled module predating masked I/O',()=>{
  const binary=image(0),cpu=new Translated(binary,null,{target:'attiny88',fastIdle:false});
  assert.equal(cpu.transpilation.abi.maskedIO,true);
  const manifest=structuredClone(cpu.transpilation);delete manifest.abi.maskedIO;
  assert.throws(()=>new Translated(binary,null,{target:'attiny88',fastIdle:false,
    precompiled:{bytes:cpu.transpiledBytes,manifest}}),/runtime ABI mismatch/);
});

// A selected-bit write must not replay an unselected command/strobe.
for(const [engine,Core] of [['JS',JS],['WASM',Wasm],['translated',Translated]])
for(const target of ['attiny13a','attiny88'])test(`${engine}/${target}: CBI EERE does not renew unselected EEMPE`,()=>{
  const probe=new Core(image(0),null,{target,fastIdle:false});
  const io=probe.profile.system.eecr-32;assert.ok(io>=0&&io<32);
  const cpu=new Core(image(bitIO(0x9800,io,0)),null,{target,fastIdle:false});
  cpu.writeIO(io,4);assert.equal(cpu.eempeUntil,4);cpu.sreg=0x55;
  cpu.step();assert.equal(cpu.cyc,2);assert.equal(cpu.eempeUntil,4);
  assert.equal(cpu.io[io],4);assert.equal(cpu.sreg,0x55);
  cpu.clock(2);assert.equal(cpu.cyc,4);assert.equal(cpu.io[io]&4,0);
});
