import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A6.3.1 does not specify silicon ripple phase. This checks the
// retained T1+T2 digital fixture, not a measured physical switching latency.
const policies={ordinary:{},verification:{resumable:true,...executionOptions('verification')},
  optimized:{resumable:true,boundedRegions:true,optimizePhaseLocals:true,sramBlocks:true}};
// A pinned historical artifact can exercise the same final test source.
const runtimeModule=process.env.MICROMUSIC_CLKPR_RUNTIME
  ?new WebAssembly.Module(readFileSync(process.env.MICROMUSIC_CLKPR_RUNTIME)):undefined;
function image(oldCode,newCode){
  // Initial /1: five cycles install oldDiv. The nine-instruction loop has
  // ten CPU cycles, weighted 6*oldDiv+4*newDiv source periods. Each target
  // CLKPR OUT is within four cycles of unlock; its following NOP keeps one
  // old period before the selected new divider becomes active.
  return sequential([avr.ldi(16,128),avr.out(IO.CLKPR,16),avr.ldi(17,oldCode),avr.out(IO.CLKPR,17),avr.nop(),
    avr.out(IO.CLKPR,16),avr.ldi(17,newCode),avr.out(IO.CLKPR,17),avr.nop(),
    avr.out(IO.CLKPR,16),avr.ldi(17,oldCode),avr.out(IO.CLKPR,17),avr.nop(),avr.rjmp(13,5)]);
}
const endpoint=(sourcePeriods,hz)=>(BigInt(sourcePeriods)*1000000000000n+BigInt(hz)-1n)/BigInt(hz);
function make(oldCode,newCode,hz,policy){
  const osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  return new ATtiny13A(image(oldCode,newCode),null,{oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,...policies[policy],runtimeModule});
}
function check(c,oldCode,newCode,hz,loops){
  const periods=5+loops*(6*2**oldCode+4*2**newCode);
  assert.equal(c.state().timePs,endpoint(periods,hz),`clock ${oldCode}->${newCode}, loops ${loops}`);
  assert.equal(c.cyc,5+10*loops);assert.equal(c.pc,5);
  assert.equal(c.state().clockDivisor,2**oldCode);assert.equal(c.readIO(IO.CLKPR),oldCode);
  if(c._translationOptions.resumable)assert.equal(c.state().cpuPhase.retired,BigInt(5+9*loops));
  assert.equal(c.state().deviceFault,0);
}

for(const policy of Object.keys(policies)){
  test(`CLKPR ${policy}: all81 divider pairs retain fractional source progress`,()=>{
    for(let oldCode=0;oldCode<=8;oldCode++)for(let newCode=0;newCode<=8;newCode++){
      const c=make(oldCode,newCode,9000000,policy);assert.equal(c.run(5+9*19),5+9*19);check(c,oldCode,newCode,9000000,19);
    }
  });

  for(const hz of [9000000,11000003,10000000])
  test(`CLKPR ${policy}/${hz}: repeated writes never accumulate timestamp rounding`,()=>{
    const c=make(0,1,hz,policy);assert.equal(c.run(5),5);
    for(let loops=4000;loops<=32000;loops+=4000){assert.equal(c.run(9*4000),9*4000);check(c,0,1,hz,loops);}
  });

  test(`CLKPR ${policy}: Timer0 CTC witnesses every exact divided-clock edge`,()=>{
    const hz=9000000,oldCode=1,newCode=3,c=make(oldCode,newCode,hz,policy);c.run(5);
    c.observePins(1);
    c.writeIO(IO.DDRB,1);c.writeIO(IO.OCR0A,0);c.writeIO(IO.TCCR0A,0x42);c.writeIO(IO.TCCR0B,1);c.drainPinsPs();
    const loops=16,weights=[2,2,2,2,8,8,8,8,2,2],expected=[];let sourcePeriods=5,level=0;
    for(let n=0;n<loops;n++)for(const weight of weights){
      sourcePeriods+=weight;level^=1;expected.push({at:endpoint(sourcePeriods,hz),level});
    }
    assert.equal(c.run(loops*9),loops*9);check(c,oldCode,newCode,hz,loops);
    let previous=0;
    const actual=c.drainPinsPs().flatMap(e=>{
      const level=e.levels&1;if(level===previous)return [];
      previous=level;assert.equal(e.driven&1,1);return [{at:e.timePs,level}];
    });
    assert.deepEqual(actual,expected,'CTC TOP=0 toggles once per original synchronous cycle');
    assert.equal(c.readIO(IO.TCNT0),0);assert.ok(c.readIO(IO.TIFR0)&4);
  });
}

test('physical observation cuts around a pending CLKPR switch preserve its fractional continuation',()=>{
  const hz=9000000,oldCode=3,newCode=0,loops=257,transition=endpoint(5+4*8,hz);
  for(const policy of ['verification','optimized'])for(const delta of [-1n,0n,1n]){
    const c=make(oldCode,newCode,hz,policy);c.runUntilPs(transition+delta);
    const retired=c.state().cpuPhase.retired,remaining=5+9*loops-Number(retired);
    assert.equal(c.run(remaining),remaining);check(c,oldCode,newCode,hz,loops);
  }
});
