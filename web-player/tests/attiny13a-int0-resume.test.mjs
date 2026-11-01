import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const runtime=process.env.MICROMUSIC_INT0_RUNTIME?new Uint8Array(readFileSync(process.env.MICROMUSIC_INT0_RUNTIME)):getRuntimeBytes();
const runtimeModule=new WebAssembly.Module(runtime);
function image(sense,mode){
  return sequential([avr.ldi(16,MASK.PORTB1),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16),
    avr.ldi(16,MASK.SE|(mode<<3)|sense),avr.out(IO.MCUCR,16),
    avr.ldi(16,MASK.WDTIE),avr.out(IO.WDTCR,16),...Array.from({length:8},avr.nop),
    avr.ldi(16,MASK.INTF0),avr.out(IO.GIFR,16),avr.in(19,IO.GIFR),avr.sleep(),
    avr.in(20,IO.GIFR),avr.in(21,IO.PINB),avr.rjmp(21,21)]);
}
function make(sense,{clock='internal',policy='verification',mode=2,wake='wdt'}={}){
  const osccalHz=Array(128).fill(0);osccalHz[0]=1000000;
  const c=new ATtiny13A(image(sense,mode),null,{runtimeModule,resumable:true,fastIdle:false,
    ...policy==='verification'?executionOptions('verification'):{boundedRegions:true,optimizePhaseLocals:true,sramBlocks:true},
    oscillatorHz:1000000,fuseLow:clock==='clki'?0x70:0x72,
    ...clock==='clki'?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz}});
  c.observePins(MASK.PINB1);
  if(wake==='pin'){
    c.writeIO(IO.PCMSK,MASK.PCINT0);c.writeIO(IO.GIMSK,MASK.PCIE);
    c.injectPinsPs({at:50000000n,mask:MASK.PINB0,levels:MASK.PINB0});
  }
  if(clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,
    transitionCount:40000n,knownUntilPs:20000000000n}),true);
  return c;
}
function run(sense,options,expected){
  const c=make(sense,options);c.runUntilPs(19000000n);
  assert.equal(c.pc,19);assert.equal(c.state().cpuPhase.retired,19n);assert.equal(c.state().sleeping,true);
  assert.equal(c.r[19]&MASK.INTF0,0);assert.equal(c.r[20],0);assert.equal(c.readIO(IO.GIMSK)&MASK.INT0,0);
  c.runUntilPs(options.wake==='pin'?100000000n:16010000000n);
  assert.equal(c.state().sleeping,false);assert.equal(c.r[20]&MASK.INTF0,expected);
  assert.equal(c.r[21]&MASK.PINB1,MASK.PINB1);assert.equal(c.state().irqs,0);assert.equal(c.sp,0x9f);
  assert.equal(c.state().deviceFault,0);assert.equal(c.sreg,0);
  assert.ok(c.state().cpuPhase.retired>=21n);return c;
}

for(const sense of [1,2,3])for(const clock of ['internal','clki'])for(const policy of ['verification','optimized'])
test(`firmware reads masked INT0 restoration flag after WDT wake: sense${sense}/${clock}/${policy}`,()=>{
  run(sense,{clock,policy},MASK.INTF0);
});

for(const clock of ['internal','clki'])test(`PCINT wake restores the masked high INT0 flag on ${clock}`,()=>{
  const c=run(3,{clock,wake:'pin'},MASK.INTF0);assert.ok(c.r[20]&MASK.PCIF);
});

for(const mode of [0,1])for(const clock of ['internal','clki'])
test(`firmware sleep control mode${mode}/${clock} creates no INT0 restoration flag`,()=>{
  run(3,{clock,mode},0);
});
