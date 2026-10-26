import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash,IO} from './fixtures/attiny13a-system-firmware.mjs';

const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
const options={resumable:true,fastIdle:false,oscillatorHz:10000000,osccalHz,fuseLow:0x72,
  comparatorTimingProfile:{domain:'physical-ns-v1',propagationNs:200,bandgapStartupNs:0}};
test('physical comparator completion reaches each generated CPU policy interrupt path exactly once',()=>{
  const image=flash({instructions:[avr.rjmp(0,16)]},
    {at:5,instructions:[avr.inc(20),avr.reti()]},
    {at:16,instructions:[avr.sei(),avr.rjmp(17,17)]});
  for(const optimized of [false,true]){
    const c=new ATtiny13A(image,null,{...options,boundedRegions:optimized,optimizePhaseLocals:optimized});c.writeIO(IO.ACSR,8);
    c.setAnalogPs({at:500000n,pin:0,microvolts:3000000});
    c.runUntilPs(799999n);assert.equal(c.r[20],0);assert.equal(c.data[32+IO.ACSR]&0x30,0);
    c.runUntilPs(2000000n);assert.equal(c.r[20],1);assert.equal(c.state().irqs,1);
    assert.equal(c.data[32+IO.ACSR]&0x30,0x20,'ACO stays set while vector entry acknowledges ACI');
    assert.equal(c.state().deviceFault,0);
  }
});

test('Power-down disables raw work; PCINT wake restarts physical settling before clocked visibility',()=>{
  const image=flash({instructions:[avr.ldi(16,0x30),avr.out(IO.MCUCR,16),avr.sleep(),avr.inc(18),avr.rjmp(4,4)]});
  const c=new ATtiny13A(image,null,{...options,boundedRegions:true,optimizePhaseLocals:true});c.writeIO(IO.PCMSK,4);c.writeIO(IO.GIMSK,0x20);
  c.setAnalogPs({at:1000000n,pin:0,microvolts:3000000});c.injectPinsPs({at:5000000n,mask:4,levels:4});
  c.runUntilPs(4999999n);assert.equal(c.r[18],0);assert.equal(c.data[32+IO.ACSR]&0x30,0);
  c.runUntilPs(5299999n);assert.equal(c.data[32+IO.ACSR]&0x30,0);
  c.runUntilPs(5300000n);assert.equal(c.data[32+IO.ACSR]&0x30,0x30);
  c.runUntilPs(6000000n);assert.equal(c.r[18],1);assert.equal(c.state().irqs,0);
  // PRADC also shuts down the comparator (DS40002307A7.5.3). Its retained
  // output must not hide raw settling that starts only after ungating.
  c.writeIO(IO.ACSR,0x10);c.writeIO(IO.PRR,1);
  c.setAnalogPs({at:7000000n,pin:0,microvolts:0});c.runUntilPs(8000000n);
  assert.equal(c.data[32+IO.ACSR]&0x30,0x20);c.writeIO(IO.PRR,0);
  c.runUntilPs(8299999n);assert.equal(c.data[32+IO.ACSR]&0x30,0x20);
  c.runUntilPs(8300000n);assert.equal(c.data[32+IO.ACSR]&0x30,0x10);
  assert.equal(c.state().deviceFault,0);
});
