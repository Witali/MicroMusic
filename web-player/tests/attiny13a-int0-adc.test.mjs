import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {executionOptions} from '../lib/emulation-configurations.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A 9.3.3,14.4,14.12.4: ADC sees interrupt flags, while
// low-level INT0 remains a separate live CPU/wake condition with INTF0 clear.
const runtime=process.env.MICROMUSIC_INT0_ADC_RUNTIME?readFileSync(process.env.MICROMUSIC_INT0_ADC_RUNTIME):getRuntimeBytes();
const runtimeModule=new WebAssembly.Module(runtime),us=1000000n;
const idle=sequential([avr.rjmp(0,0)]),auto=MASK.ADEN|MASK.ADATE,busy=MASK.ADSC|MASK.ADIF;
function make(clock,policy,image=idle){
  const osccalHz=Array(128).fill(0);osccalHz[0]=1000000;
  const c=new ATtiny13A(image,null,{runtimeModule,resumable:true,fastIdle:false,
    ...policy==='verification'?executionOptions('verification'):{boundedRegions:true,optimizePhaseLocals:true,sramBlocks:true},
    oscillatorHz:1000000,fuseLow:clock==='clki'?0x70:0x72,
    ...clock==='clki'?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz}});
  c.observePins(0);c.setAnalogPs({at:0n,pin:2,microvolts:1250000});
  if(clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:us/2n,lowPs:us/2n,
    transitionCount:4000n,knownUntilPs:2000n*us}),true);
  return c;
}
function arm(c,sense,enabled=0){
  c.writeIO(IO.MCUCR,sense);c.injectPinsPs({at:0n,mask:MASK.PINB1,levels:sense===2?MASK.PINB1:0});
  c.runUntilPs(5n*us);c.writeIO(IO.GIFR,MASK.INTF0);c.writeIO(IO.GIMSK,enabled);
  c.writeIO(IO.ADMUX,1);c.writeIO(IO.ADCSRB,2);c.writeIO(IO.ADCSRA,auto);
  c.runUntilPs(7n*us);
}
const result=c=>c.readIO(IO.ADCL)|(c.readIO(IO.ADCH)<<8);
function healthy(c){assert.equal(c.state().deviceFault,0);assert.equal(c.state().irqs,0);assert.equal(c.sreg,0);}

for(const clock of ['internal','clki'])for(const policy of ['verification','optimized'])for(const enabled of [0,MASK.INT0])
test(`low INT0 cannot auto-trigger ADC: ${clock}/${policy}/GIMSK${enabled}`,()=>{
  const c=make(clock,policy);arm(c,0,enabled);c.runUntilPs(100n*us);
  assert.equal(c.readIO(IO.GIFR)&MASK.INTF0,0);assert.equal(c.readIO(IO.ADCSRA)&busy,0);assert.equal(result(c),0);
  let at=100n;
  for(const levels of [MASK.PINB1,0,MASK.PINB1,0]){
    c.injectPinsPs({at:(at+1n)*us,mask:MASK.PINB1,levels});at+=20n;c.runUntilPs(at*us);
    assert.equal(c.readIO(IO.GIFR)&MASK.INTF0,0);assert.equal(c.readIO(IO.ADCSRA)&busy,0);
    assert.equal(c.state().pendingIRQs&2,!levels&&enabled?2:0,'live CPU request remains independent');
  }
  c.writeIO(IO.ADCSRA,auto|MASK.ADSC);c.runUntilPs((at+60n)*us);
  assert.equal(c.readIO(IO.ADCSRA)&busy,MASK.ADIF);assert.equal(result(c),256,'manual ADSC still works');healthy(c);
});

for(const sense of [1,2,3])for(const clock of ['internal','clki'])for(const policy of ['verification','optimized'])
test(`INTF0 edges trigger ADC once: sense${sense}/${clock}/${policy}`,()=>{
  const c=make(clock,policy);arm(c,sense);assert.equal(c.readIO(IO.ADCSRA)&busy,0);
  const levels=sense===2?0:MASK.PINB1;
  c.injectPinsPs({at:20n*us,mask:MASK.PINB1,levels});c.runUntilPs(25n*us);
  assert.equal(c.readIO(IO.GIFR)&MASK.INTF0,MASK.INTF0);assert.equal(c.readIO(IO.ADCSRA)&busy,MASK.ADSC);
  c.runUntilPs(80n*us);assert.equal(c.readIO(IO.ADCSRA)&busy,MASK.ADIF);assert.equal(result(c),256);
  c.writeIO(IO.GIMSK,MASK.INT0);assert.equal(c.state().pendingIRQs&2,2);
  c.writeIO(IO.ADCSRA,auto|MASK.ADIF);c.runUntilPs(150n*us);
  assert.equal(c.readIO(IO.ADCSRA)&busy,0,'held INTF0 cannot retrigger');
  c.writeIO(IO.GIFR,MASK.INTF0);c.setAnalogPs({at:151n*us,pin:2,microvolts:2500000});
  c.injectPinsPs({at:160n*us,mask:MASK.PINB1,levels:levels^MASK.PINB1});
  c.injectPinsPs({at:170n*us,mask:MASK.PINB1,levels});c.runUntilPs(230n*us);
  assert.equal(c.readIO(IO.ADCSRA)&busy,MASK.ADIF);assert.equal(result(c),512);healthy(c);
});

function sleepImage(sense){
  return sequential([avr.ldi(16,MASK.PORTB1),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16),
    avr.ldi(16,MASK.SE|MASK.SM1|sense),avr.out(IO.MCUCR,16),...Array.from({length:8},avr.nop),
    avr.ldi(16,MASK.INTF0),avr.out(IO.GIFR,16),avr.ldi(16,1),avr.out(IO.ADMUX,16),
    avr.ldi(16,2),avr.out(IO.ADCSRB,16),avr.ldi(16,auto),avr.out(IO.ADCSRA,16),
    avr.in(19,IO.ADCSRA),avr.sleep(),avr.in(20,IO.GIFR),avr.in(21,IO.ADCSRA)]);
}
for(const sense of [1,2,3])for(const clock of ['internal','clki'])
test(`Power-down clamp cannot trigger ADC before INT0 restoration: sense${sense}/${clock}`,()=>{
  const c=make(clock,'verification',sleepImage(sense));c.writeIO(IO.PCMSK,MASK.PCINT0);c.writeIO(IO.GIMSK,MASK.PCIE);
  c.injectPinsPs({at:100n*us,mask:MASK.PINB0,levels:MASK.PINB0});c.runUntilPs(50n*us);
  assert.equal(c.state().sleeping,true);assert.equal(c.r[19]&busy,0);assert.equal(c.readIO(IO.GIFR)&MASK.INTF0,0);
  assert.equal(c.readIO(IO.ADCSRA)&busy,0,'clamping is not a rising INTF0 flag');
  c.runUntilPs(110n*us);assert.equal(c.state().sleeping,false);
  assert.equal(c.r[20]&MASK.INTF0,MASK.INTF0);assert.equal(c.r[21]&busy,MASK.ADSC);
  c.runUntilPs(200n*us);assert.equal(c.readIO(IO.ADCSRA)&busy,MASK.ADIF);assert.equal(result(c),256);healthy(c);
});

for(const clock of ['internal','clki'])test(`low INT0 still wakes Power-down without an ADC trigger on ${clock}`,()=>{
  const image=sequential([avr.ldi(16,MASK.SE|MASK.SM1),avr.out(IO.MCUCR,16),avr.sleep(),avr.in(20,IO.ADCSRA)]);
  const c=make(clock,'verification',image);c.injectPinsPs({at:0n,mask:MASK.PINB1,levels:MASK.PINB1});
  c.writeIO(IO.GIMSK,MASK.INT0);c.writeIO(IO.ADMUX,1);c.writeIO(IO.ADCSRB,2);c.writeIO(IO.ADCSRA,auto);
  c.injectPinsPs({at:100n*us,mask:MASK.PINB1,levels:0});c.runUntilPs(50n*us);assert.equal(c.state().sleeping,true);
  c.runUntilPs(200n*us);assert.equal(c.state().sleeping,false);assert.equal(c.state().pendingIRQs&2,2);
  assert.equal(c.r[20]&busy,0);assert.equal(c.readIO(IO.GIFR)&MASK.INTF0,0);
  assert.equal(c.readIO(IO.ADCSRA)&busy,0);assert.equal(result(c),0);healthy(c);
});
