import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash,IO} from './fixtures/attiny13a-system-firmware.mjs';

// Explicit digital/analog fixture values, not measured ATtiny13A delays.
const image=flash({instructions:[avr.rjmp(0,0)]});
const profile=(propagationNs=200,bandgapStartupNs=0)=>({domain:'physical-ns-v1',propagationNs,bandgapStartupNs});
function internal(hz=10000000,divisor=1,comparatorTimingProfile=profile()){
  const osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  return new ATtiny13A(image,null,{resumable:true,fastIdle:false,oscillatorHz:hz,osccalHz,
    fuseLow:divisor===1?0x72:0x62,comparatorTimingProfile});
}
function observe(c,at){
  c.runUntilPs(at);assert.equal(c.state().deviceFault,0);
  return c.data[32+IO.ACSR]&0x30;
}
for(const [divisor,at] of [[1,300000n],[8,1600000n]])
test(`physical propagation remains 200ns at CLKPR /${divisor}; only digital synchronization scales`,()=>{
  const c=internal(10000000,divisor);c.setAnalogPs({at:0n,pin:0,microvolts:3000000});
  assert.equal(observe(c,at-1n),0);assert.equal(observe(c,at),0x30);
});

for(const [inputAt,acoAt] of [[111n,222223n],[112n,222223n],[113n,333334n]])
test(`9MHz quantized rising-edge boundary, input at ${inputAt}ps`,()=>{
  const c=internal(9000000,1,profile(111));
  c.setAnalogPs({at:inputAt,pin:0,microvolts:3000000});
  // ceil(2*0.5e12/9e6)=111112ps. A raw deadline exactly here is
  // processed before the actual rounded rising edge, despite nonzero residue.
  assert.equal(observe(c,acoAt-1n),0);assert.equal(observe(c,acoAt),0x30);
});

test('CLKPR transition cannot stretch an already scheduled physical analog delay',()=>{
  const c=internal();c.setAnalogPs({at:0n,pin:0,microvolts:3000000});observe(c,50000n);
  c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,3);
  assert.equal(observe(c,1699999n),0);assert.equal(observe(c,1700000n),0x30);
});

function external(initialLevel=1,comparatorTimingProfile=profile(),extra={}){
  return new ATtiny13A(image,null,{resumable:true,fastIdle:false,oscillatorHz:10000000,
    fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel},
    comparatorTimingProfile,...extra});
}
const resume=(c,initialLevel,start=10000000n)=>{
  const edges=Array.from({length:20},(_,n)=>({timePs:start+BigInt(n+1)*50000n,level:initialLevel^((n+1)&1)}));
  assert.equal(c.injectClkiPs({edges,knownUntilPs:start+1000000n}),true);
};
for(const initial of [0,1])for(const kind of ['propagation','bandgap'])
test(`${kind} settles during a held-${initial} CLKI and uses the next two actual rises`,()=>{
  const c=external(initial,kind==='propagation'?profile():profile(0,200));
  assert.equal(c.injectClkiPs({edges:[],knownUntilPs:10000000n}),true);
  if(kind==='propagation')c.setAnalogPs({at:1000000n,pin:0,microvolts:3000000});
  else c.writeIO(IO.ACSR,0x40);
  assert.equal(observe(c,10000000n),0);resume(c,initial);
  const at=initial?10200000n:10150000n;
  assert.equal(observe(c,at-1n),0);assert.equal(observe(c,at),0x30);
});

test('held CLKI cannot publish ACI or trigger ADC before comparator synchronization',()=>{
  const c=external();c.writeIO(IO.ADCSRB,1);c.writeIO(IO.ADCSRA,0xa0);
  c.injectClkiPs({edges:[],knownUntilPs:10000000n});c.setAnalogPs({at:1000000n,pin:0,microvolts:3000000});
  assert.equal(observe(c,10000000n),0);assert.equal(c.data[32+IO.ADCSRA]&0x40,0);
  resume(c,1);assert.equal(observe(c,10100000n),0);assert.equal(c.data[32+IO.ADCSRA]&0x40,0);
  assert.equal(observe(c,10200000n),0x30);assert.equal(c.data[32+IO.ADCSRA]&0x40,0x40);
});

test('zero-delay PB3/ACME changes settle before each eligible CLKI rise',()=>{
  const c=external(0,profile(0));c.writeIO(IO.ADCSRB,0x40);c.writeIO(IO.ADMUX,3);
  c.setAnalogPs({at:0n,pin:0,microvolts:2500000});
  c.injectClkiPs({edges:[],knownUntilPs:10000000n});assert.equal(observe(c,10000000n),0);
  resume(c,0);
  for(let at=10050000n;at<=11000000n;at+=50000n)assert.equal(observe(c,at),0);
});

test('a post-edge zero-delay input cannot reuse the first aligned rising edge',()=>{
  const c=external(0,profile(0));c.injectClkiPs({edges:[],knownUntilPs:10000000n});
  assert.equal(observe(c,10000000n),0);resume(c,0);
  c.setAnalogPs({at:10050000n,pin:0,microvolts:3000000});
  assert.equal(observe(c,10150000n),0);assert.equal(observe(c,10249999n),0);
  assert.equal(observe(c,10250000n),0x30);
});

test('external RESET cancels pending physical comparison and restarts its configured delay',()=>{
  const c=internal(10000000,1,profile(500));c.setAnalogPs({at:0n,pin:0,microvolts:3000000});
  c.injectPinsPs({at:200000n,mask:32,levels:0});c.injectPinsPs({at:1000000n,mask:32,levels:32});
  assert.equal(observe(c,999999n),0);assert.equal(c.state().resetHeld,true);
  assert.equal(observe(c,1599999n),0);assert.equal(observe(c,1600000n),0x30);
});
