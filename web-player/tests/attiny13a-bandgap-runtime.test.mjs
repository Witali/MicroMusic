import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash,IO} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A7.3-7.4,8.3.1,14.7 specify shared reference demand and startup.
// All physical delays below are explicit digital fixtures, not measured silicon
// characteristics. Readiness precedes a tied ADC sample; ACO still requires its
// two selected clock stages. The BOD receiver/recovery is a separate fixture.
const max=0xffffffffffffffffn,loop=flash({instructions:[avr.rjmp(0,0)]});
const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
const options={resumable:true,fastIdle:false,oscillatorHz:10000000,osccalHz,fuseLow:0x72,
  comparatorTimingProfile:{domain:'physical-ns-v1',propagationNs:0,bandgapStartupNs:0},
  bandgapProfile:{domain:'physical-ns-v1',startupNs:1000}};
const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
  bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
  bodHysteresisMicrovolts:50000,bodFilterNs:20,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
const core=(extra={},image=loop)=>new ATtiny13A(image,null,{...options,...extra});
const bg=c=>c.state().bandgap;
const acsr=c=>c.data[32+IO.ACSR]&0x30;
const adcResult=c=>c.data[32+IO.ADCL]+256*c.data[32+IO.ADCH];

test('ADC or BOD warms the shared reference before ACBG, with no second startup',()=>{
  for(const owner of ['cold','ADC','BOD']){
    const c=core(owner==='BOD'?{fuseHigh:0xfb}:{});
    if(owner==='ADC')c.writeIO(IO.ADCSRA,0x80);
    c.runUntilPs(1100000n);
    assert.equal(bg(c).ready,owner!=='cold');
    c.writeIO(IO.ACSR,0x40);
    if(owner==='ADC')c.writeIO(IO.ADCSRA,0); // Continuous handoff to ACBG.
    assert.equal(bg(c).owners,owner==='BOD'?6:2);
    const at=owner==='cold'?2200000n:1300000n;
    assert.equal(bg(c).deadlinePs,owner==='cold'?2100000n:max);
    c.runUntilPs(at-1n);assert.equal(acsr(c),0);
    c.runUntilPs(at);assert.equal(acsr(c),0x30);assert.equal(bg(c).ready,true);
    c.writeIO(IO.ACSR,0x80); // Software ACD releases comparator demand.
    assert.equal(bg(c).owners,owner==='BOD'?4:0);
    assert.equal(bg(c).ready,owner==='BOD');assert.equal(c.state().deviceFault,0);
  }
});

for(const reference of [0,0x40])for(const firstSample of [27,29])
test(`ADC readiness around the first sample, REFS=${reference>>6}, phase=${firstSample}`,()=>{
  // ADPS=0 means /2: conversion starts after 2 CPU clocks, then each ADC
  // half phase takes one CPU clock. The first sample is (2+phase)*100 ns.
  const sampleNs=(2+firstSample)*100,samplePs=BigInt(sampleNs)*1000n;
  for(const offset of [-1,0,1]){
    const c=core({adcFirstSample:firstSample,bandgapProfile:{...options.bandgapProfile,startupNs:sampleNs+offset}});
    c.setAnalogPs({at:0n,pin:2,microvolts:500000});c.writeIO(IO.ADMUX,reference|1);c.writeIO(IO.ADCSRA,0xc0);
    c.runUntilPs(samplePs-1n);assert.equal(c.data[32+IO.ADCSRA]&0x10,0);assert.equal(adcResult(c),0);
    if(offset>0){
      assert.throws(()=>c.runUntilPs(samplePs),/peripheral fault 4, detail 17/);
      assert.equal(c.state().timePs,samplePs);assert.equal(c.data[32+IO.ADCSRA]&0x10,0);
      assert.equal(adcResult(c),0);assert.equal(bg(c).ready,false);
    }else{
      c.runUntilPs(samplePs);assert.equal(bg(c).ready,true);assert.equal(c.data[32+IO.ADCSRA]&0x10,0);
      c.runUntilPs(5200000n);assert.equal(adcResult(c),reference?465:102);
      assert.equal(c.data[32+IO.ADCSRA]&0x50,0x10);assert.equal(c.state().deviceFault,0);
    }
  }
});

test('a shared startup tied to an odd-half ADC sample does not clock ADC prematurely',()=>{
  const c=core({bandgapProfile:{...options.bandgapProfile,startupNs:2900}});
  c.runUntilPs(50000n);c.setAnalogPs({at:50000n,pin:2,microvolts:500000});
  c.writeIO(IO.ADMUX,0x41);c.writeIO(IO.ADCSRA,0xc0);
  c.runUntilPs(2949999n);assert.equal(bg(c).ready,false);
  c.runUntilPs(2950000n);assert.equal(bg(c).ready,true);assert.equal(c.data[32+IO.ADCSRA]&0x10,0);
  c.runUntilPs(5250000n);assert.equal(adcResult(c),465);assert.equal(c.state().deviceFault,0);
});

test('integer-ps quantization preserves readiness one ps before/on/after an ADC sample',()=>{
  // At 9MHz the independently calculated half58 endpoint is ceil(29e12/9e6).
  const hz=Array(128).fill(0);hz[0]=9000000;
  const samplePs=(29n*1000000000000n+8999999n)/9000000n;
  for(const at of [222n,223n,224n]){
    const c=core({oscillatorHz:9000000,osccalHz:hz,bandgapProfile:{...options.bandgapProfile,startupNs:3222}});
    c.runUntilPs(at);c.setAnalogPs({at,pin:2,microvolts:500000});
    c.writeIO(IO.ADMUX,1);c.writeIO(IO.ADCSRA,0xc0);
    assert.equal(bg(c).deadlinePs,at+3222000n);c.runUntilPs(samplePs-1n);
    if(at===224n)assert.throws(()=>c.runUntilPs(samplePs),/peripheral fault 4, detail 17/);
    else {c.runUntilPs(samplePs);assert.equal(bg(c).ready,true);assert.equal(c.state().deviceFault,0);}
    assert.equal(c.data[32+IO.ADCSRA]&0x10,0);assert.equal(adcResult(c),0);
  }
});

test('held CLKI permits physical reference startup but requires actual rising edges for ACO',()=>{
  for(const initialLevel of [0,1]){
    const c=core({osccalHz:null,fuseLow:0x70,
      clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel}});
    c.writeIO(IO.ACSR,0x40);assert.equal(c.injectClkiPs({edges:[],knownUntilPs:2000000n}),true);
    c.runUntilPs(999999n);assert.equal(bg(c).ready,false);
    c.runUntilPs(2000000n);assert.equal(bg(c).ready,true);assert.equal(acsr(c),0);
    const edges=initialLevel?[{timePs:2050000n,level:0},{timePs:2100000n,level:1}]:[{timePs:2100000n,level:1}];
    assert.equal(c.injectClkiPs({edges:[...edges,{timePs:2150000n,level:0},{timePs:2200000n,level:1}],knownUntilPs:3000000n}),true);
    c.runUntilPs(2199999n);assert.equal(acsr(c),0);
    c.runUntilPs(2200000n);assert.equal(acsr(c),0x30);assert.equal(c.state().deviceFault,0);
  }
});

test('PRADC gates comparator work without clearing an explicit ACBG reference request',()=>{
  const c=core();c.writeIO(IO.ACSR,0x40);c.writeIO(IO.PRR,1);
  c.runUntilPs(2000000n);assert.equal(bg(c).owners,2);assert.equal(bg(c).ready,true);assert.equal(acsr(c),0);
  c.writeIO(IO.PRR,0);assert.equal(bg(c).deadlinePs,max);
  c.runUntilPs(2199999n);assert.equal(acsr(c),0);
  c.runUntilPs(2200000n);assert.equal(acsr(c),0x30);assert.equal(c.state().deviceFault,0);
});

const sleepImage=flash({instructions:[avr.ldi(16,0x30),avr.out(IO.MCUCR,16),
  avr.ldi(16,3),avr.out(IO.BODCR,16),avr.ldi(16,2),avr.out(IO.BODCR,16),
  avr.sleep(),avr.inc(18),avr.rjmp(8,8)]});
test('BOD sleep disable releases only its demand; wake recovery remains independent of reference readiness',()=>{
  for(const retained of [0,1,2]){
    const c=core({fuseHigh:0xfb},sleepImage);
    if(retained===1)c.writeIO(IO.ADCSRA,0x80);
    if(retained===2)c.writeIO(IO.ACSR,0x40);
    c.writeIO(IO.PCMSK,4);c.writeIO(IO.GIMSK,0x20);c.injectPinsPs({at:5000000n,mask:4,levels:4});
    c.runUntilPs(4999999n);assert.equal(c.r[18],0);assert.equal(c.state().bodDisabled,true);
    assert.equal(bg(c).owners,retained);assert.equal(bg(c).ready,retained!==0);
    c.runUntilPs(5000000n);assert.equal(bg(c).owners,retained|4);
    assert.equal(bg(c).deadlinePs,retained?max:6000000n);
    c.runUntilPs(6000000n);assert.equal(bg(c).ready,true);assert.equal(c.state().bodRecovering,true);
    c.runUntilPs(65000000n);assert.equal(c.r[18],0);
    c.runUntilPs(66000000n);assert.equal(c.r[18],1);assert.equal(c.state().deviceFault,0);
  }
});

test('warm external reset preserves BOD demand but clears software reference requests',()=>{
  for(const bod of [false,true]){
    const c=core({fuseHigh:bod?0xfb:0xff});c.writeIO(IO.ADCSRA,0x80);
    c.injectPinsPs({at:3000000n,mask:32,levels:0});c.injectPinsPs({at:4000000n,mask:32,levels:32});
    c.runUntilPs(2000000n);assert.equal(bg(c).ready,true);
    c.runUntilPs(3500000n);assert.equal(c.state().resetHeld,true);assert.equal(bg(c).powered,true);
    assert.equal(bg(c).owners,bod?4:0);assert.equal(bg(c).ready,bod);
    c.runUntilPs(4500000n);assert.equal(c.state().resetHeld,false);assert.equal(bg(c).ready,bod);
    assert.equal(c.readIO(IO.MCUSR)&1,1,'sticky PORF is not a current power loss');
    if(!bod){c.writeIO(IO.ADCSRA,0x80);assert.equal(bg(c).deadlinePs,5500000n);}
    assert.equal(c.state().deviceFault,0);
  }
});

test('POR removes readiness and power release starts reference even while external RESET remains held',()=>{
  const c=core({fuseHigh:0xfb,powerResetProfile});
  c.setVccPs({at:3000000n,microvolts:0});c.injectPinsPs({at:3500000n,mask:32,levels:0});
  c.setVccPs({at:4000000n,microvolts:5000000});c.injectPinsPs({at:4500000n,mask:32,levels:32});
  c.runUntilPs(2000000n);assert.equal(bg(c).ready,true);
  c.runUntilPs(3000000n);assert.equal(bg(c).powered,false);assert.equal(bg(c).ready,false);
  assert.equal(bg(c).active,false);assert.equal(bg(c).owners,4);
  c.runUntilPs(4000000n);assert.equal(c.state().resetHeld,true);assert.equal(bg(c).powered,true);
  assert.equal(bg(c).deadlinePs,5000000n);
  c.runUntilPs(4999999n);assert.equal(bg(c).ready,false);
  c.runUntilPs(5000000n);assert.equal(bg(c).ready,true);assert.equal(c.state().deviceFault,0);
});

test('watchdog reset retains a warm BOD reference and releases software owners',()=>{
  // Accelerated explicit watchdog input: 2048 ticks at 1GHz = 2048ns.
  // This is a reset-ordering fixture, not a supported silicon oscillator rate.
  for(const bod of [false,true]){
    const c=core({fuseHigh:bod?0xfb:0xff,watchdogHz:1000000000});
    c.writeIO(IO.ADCSRA,0x80);c.writeIO(IO.WDTCR,8);
    c.runUntilPs(2000000n);assert.equal(bg(c).ready,true);
    c.runUntilPs(3000000n);assert.equal(c.state().resetCount,1);
    assert.equal(c.readIO(IO.MCUSR)&8,8);assert.equal(bg(c).powered,true);
    assert.equal(bg(c).owners,bod?4:0);assert.equal(bg(c).ready,bod);
    assert.equal(c.state().deviceFault,0);
  }
});

test('POR added during an existing RESET hold invalidates a previously warm reference',()=>{
  const c=core({fuseHigh:0xfb,powerResetProfile});
  c.injectPinsPs({at:3000000n,mask:32,levels:0});c.setVccPs({at:3500000n,microvolts:0});
  c.setVccPs({at:4500000n,microvolts:5000000});c.injectPinsPs({at:5000000n,mask:32,levels:32});
  c.runUntilPs(3000000n);assert.equal(c.state().resetHeld,true);assert.equal(bg(c).ready,true);
  c.runUntilPs(3500000n);assert.equal(c.state().resetHeld,true);assert.equal(bg(c).powered,false);
  assert.equal(bg(c).ready,false);assert.equal(bg(c).owners,4);
  c.runUntilPs(4500000n);assert.equal(bg(c).powered,true);assert.equal(bg(c).deadlinePs,5500000n);
  c.runUntilPs(5499999n);assert.equal(bg(c).ready,false);
  c.runUntilPs(5500000n);assert.equal(bg(c).ready,true);assert.equal(c.state().deviceFault,0);
});
