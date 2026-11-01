import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A 8.4/8.5.2: real firmware, not direct watchdog state mutation.
const us=1000000n,ms=1000n*us,first=16n*ms,second=32n*ms;
function image(mode){
  const served=mode==='interrupt'||mode==='combined';
  const main=[avr.ldi(16,mode==='interrupt'?MASK.WDTIE:MASK.WDTIE|MASK.WDE),avr.out(IO.WDTCR,16),
    avr.ldi(16,MASK.DDB4),avr.out(IO.DDRB,16),avr.ldi(16,MASK.SE|MASK.SM1),avr.out(IO.MCUCR,16),
    served?avr.sei():avr.cli(),avr.sleep(),avr.in(21,IO.WDTCR)];
  if(!served)main.push(avr.ldi(16,MASK.WDTIF|MASK.WDTIE|MASK.WDE),avr.out(IO.WDTCR,16),avr.in(23,IO.WDTCR));
  if(mode==='wdr')main.push(avr.wdr());
  main.push(avr.in(22,IO.MCUSR));const end=16+main.flat().length;
  return flash({instructions:[avr.rjmp(0,16)]},{at:8,instructions:[avr.rjmp(8,64)]},
    {at:16,instructions:[...main,avr.rjmp(end,end)]},
    {at:64,instructions:[avr.in(20,IO.WDTCR),avr.inc(18),avr.sbi(IO.PINB,4),avr.reti()]});
}
function make(mode,clock,policy,held){
  const osccalHz=Array(128).fill(0);osccalHz[0]=1000000;
  const c=new ATtiny13A(image(mode),null,{resumable:true,fastIdle:false,oscillatorHz:1000000,
    ...policy==='verification'?executionOptions('verification'):{boundedRegions:true,optimizePhaseLocals:true,sramBlocks:true},
    fuseLow:clock==='clki'?0x70:0x72,
    ...clock==='clki'?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz}});
  c.observePins(MASK.PINB4);
  if(clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:us/2n,lowPs:us/2n,
    transitionCount:held===undefined?80000n:held?20n:21n,knownUntilPs:40n*ms}),true);
  c.runUntilPs(12n*us);assert.equal(c.state().sleeping,true);assert.equal(c.pc,24);assert.equal(c.r[18],0);
  assert.equal(c.readIO(IO.WDTCR)&(MASK.WDTIF|MASK.WDTIE|MASK.WDE),mode==='interrupt'?MASK.WDTIE:MASK.WDTIE|MASK.WDE);
  c.drainPinsPs();return c;
}
const healthy=c=>assert.equal(c.state().deviceFault,0);
for(const mode of ['interrupt','combined','w1c','wdr'])for(const clock of ['internal','clki'])for(const policy of ['verification','optimized'])
test(`firmware watchdog ${mode}/${clock}/${policy}`,()=>{
  const c=make(mode,clock,policy);c.runUntilPs(first-1n);
  assert.equal(c.readIO(IO.WDTCR)&MASK.WDTIF,0);assert.equal(c.state().resetCount,0);assert.equal(c.r[18],0);
  c.runUntilPs(first+50n*us);assert.equal(c.state().sleeping,false);assert.equal(c.sp,0x9f);
  const served=mode==='interrupt'||mode==='combined';
  assert.equal(c.r[18],served?1:0);assert.equal(c.state().irqs,served?1:0);
  if(served){
    assert.equal(c.r[20],mode==='interrupt'?MASK.WDTIE:MASK.WDE,'vector acceptance clears WDTIF and combined WDTIE');
    assert.equal(c.r[21],c.r[20]);assert.equal(c.state().pins.levels&MASK.PINB4,MASK.PINB4);
  }else{
    assert.equal(c.r[21],MASK.WDTIF|MASK.WDTIE|MASK.WDE);assert.equal(c.r[23],MASK.WDTIE|MASK.WDE);
    assert.equal(c.state().pins.levels&MASK.PINB4,0,'W1C cannot execute the ISR');
  }
  assert.equal(c.r[22]&15,MASK.PORF);assert.equal(c.readIO(IO.WDTCR)&MASK.WDTIF,0);
  // WDR completes at16.009ms, after pulse2049: the reset moves to pulse4097.
  const resetAt=mode==='wdr'?4097n*7812500n:second;
  c.runUntilPs(resetAt-1n);assert.equal(c.state().resetCount,0);
  if(mode==='interrupt'){
    c.runUntilPs(second+50n*us);assert.equal(c.r[18],2);assert.equal(c.state().irqs,2);
    assert.equal(c.state().resetCount,0);assert.equal(c.readIO(IO.WDTCR),MASK.WDTIE);assert.equal(c.sp,0x9f);
    const pins=c.drainPinsPs();assert.deepEqual(pins.map(e=>!!(e.levels&MASK.PINB4)),[true,false]);
  }else{
    c.runUntilPs(resetAt);assert.equal(c.state().resetCount,1);assert.equal(c.pc,0);assert.equal(c.sp,0x9f);
    assert.equal(c.readIO(IO.MCUSR)&15,MASK.PORF|MASK.WDRF);assert.equal(c.readIO(IO.WDTCR),MASK.WDE);
    assert.equal(c.readIO(IO.DDRB),0);assert.equal(c.readIO(IO.PORTB),0);
    const pins=c.drainPinsPs();assert.ok(pins.some(e=>e.timePs===resetAt&&!(e.driven&MASK.PINB4)));
  }
  healthy(c);
});

for(const held of [0,1])for(const policy of ['verification','optimized'])
test(`combined watchdog cannot enter its ISR while CLKI is held${held}/${policy}`,()=>{
  const c=make('combined','clki',policy,held);const retired=c.state().cpuPhase.retired;
  c.runUntilPs(first);assert.equal(c.state().irqs,0);assert.equal(c.r[18],0);assert.equal(c.pc,24);
  assert.equal(c.state().cpuPhase.retired,retired);assert.equal(c.state().clki.level,held);
  assert.equal(c.readIO(IO.WDTCR),MASK.WDTIF|MASK.WDTIE|MASK.WDE);assert.equal(c.state().pendingIRQs&256,256);
  c.runUntilPs(second-1n);assert.equal(c.state().resetCount,0);
  c.runUntilPs(second);assert.equal(c.state().resetCount,1);assert.equal(c.state().irqs,0);assert.equal(c.r[18],0);
  assert.equal(c.readIO(IO.DDRB),0);assert.equal(c.readIO(IO.MCUSR)&15,MASK.PORF|MASK.WDRF);
  const pins=c.drainPinsPs();assert.ok(pins.some(e=>e.timePs===second&&!(e.driven&MASK.PINB4)));
  c.runUntilPs(40n*ms);assert.equal(c.state().resetCount,1);assert.equal(c.state().irqs,0);
  assert.equal(c.injectClkiPeriodicPs({startPs:40n*ms,initialLevel:held,highPs:us/2n,lowPs:us/2n,
    transitionCount:100n,knownUntilPs:40n*ms+50n*us}),true);
  c.runUntilPs(40n*ms+50n*us);assert.equal(c.state().resetCount,1);assert.equal(c.state().sleeping,true);
  assert.equal(c.readIO(IO.DDRB),MASK.DDB4);assert.equal(c.state().irqs,0);healthy(c);
});
