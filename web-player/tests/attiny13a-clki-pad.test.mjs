import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// DS40002307A Tables10-2/10-4: PB3 has DDOE=0/PVOE=0. DDRB/PORTB
// still control its driver. An opposed strong drive has no defined digital
// voltage; diagnose that boundary before clocking consumers of the pad.
const bit=MASK.PINB3,image=sequential([avr.ldi(20,42),avr.rjmp(1,1)]);
const runtime=process.env.MICROMUSIC_CLKI_PAD_RUNTIME
  ?new Uint8Array(readFileSync(process.env.MICROMUSIC_CLKI_PAD_RUNTIME)):getRuntimeBytes();
const runtimeModule=new WebAssembly.Module(runtime);
const options=initialLevel=>({resumable:true,fuseLow:0x70,fastIdle:false,runtimeModule,
  clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel}});
const make=(initial=1,binary=image)=>new ATtiny13A(binary,null,options(initial));
const snapshot=c=>({state:c.state(),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
function drive(c,initial){c.writeIO(IO.PORTB,initial?bit:0);c.writeIO(IO.DDRB,bit);}
function failed(c,action){assert.throws(action,/peripheral fault 18, detail 1$/);assert.equal(c.state().deviceFault,18);}
function source(c,initial,kind='raw'){
  const step=500000n,count=256,horizon=BigInt(count)*step;
  const admitted=kind==='raw'?c.injectClkiPs({knownUntilPs:horizon,
    edges:Array.from({length:count},(_,n)=>({timePs:BigInt(n+1)*step,level:(initial+n+1)&1}))}):
    c.injectClkiPeriodicPs({startPs:0n,initialLevel:initial,highPs:step,lowPs:step,transitionCount:BigInt(count),knownUntilPs:horizon});
  assert.equal(admitted,true);return horizon;
}

for(const initial of [0,1])for(const mask of [0,63])
test(`PB3 same-level driver survives a held CLKI level${initial}, observation${mask}`,()=>{
  const c=make(initial);c.observePins(mask);drive(c,initial);
  const before=c.state();assert.equal(before.pins.driven&bit,bit);assert.equal(before.pins.contention&bit,0);
  assert.equal(c.readIO(IO.DDRB),bit);assert.equal(c.readIO(IO.PORTB),initial?bit:0);
  assert.equal(c.injectClkiPs({edges:[],knownUntilPs:1000000000n}),true);c.runUntilPs(1000000000n);
  assert.equal(c.state().timePs,1000000000n);assert.equal(c.cyc,0);assert.equal(c.state().cpuPhase.retired,0n);
  assert.equal(c.state().clki.level,initial);assert.equal(c.state().deviceFault,0);
  assert.equal(c.state().pins.driven&bit,bit);assert.equal(c.state().pins.levels&bit,initial?bit:0);
  assert.equal(c.state().pins.contention&bit,0);assert.equal(c.r[20],0);
});

for(const initial of [0,1])for(const kind of ['raw','periodic'])
test(`PB3 release resumes exact ${kind} CPU/Timer0/ADC3/pin behavior from level${initial}`,()=>{
  const a=make(initial),b=make(initial);
  for(const c of [a,b]){
    c.writeIO(IO.PORTB,initial?bit:0);c.writeIO(IO.TCCR0B,1);
    c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,MASK.ADEN|MASK.ADSC|MASK.ADPS0);
  }
  a.writeIO(IO.DDRB,bit);assert.equal(a.state().pins.contention&bit,0);a.writeIO(IO.DDRB,0);
  for(const c of [a,b]){c.drainPinsPs();source(c,initial,kind);}
  for(const at of [1n,499999n,500000n,999999n,1000000n,1100000n,128000000n]){
    assert.equal(a.runUntilPs(at),b.runUntilPs(at));assert.deepEqual(snapshot(a),snapshot(b));
    assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());assert.equal(a.state().deviceFault,0);
  }
  assert.equal(a.r[20],42);assert.equal(a.readIO(IO.TCNT0),Math.floor(a.cyc));
  // ADC /2 samples on a rising source phase, when this ideal CLKI pad is high.
  assert.ok(a.readIO(IO.ADCSRA)&MASK.ADIF);assert.equal(a.readIO(IO.ADCL)|(a.readIO(IO.ADCH)<<8),1023);
});

for(const initial of [0,1])for(const mask of [0,63])
test(`opposed CLKI edge stops before a derived CPU phase, initial${initial}, observation${mask}`,()=>{
  const c=make(initial);c.observePins(mask);drive(c,initial);c.r[20]=0x75;
  const at=700001n;assert.equal(c.injectClkiPs({edges:[{timePs:at,level:initial^1}],knownUntilPs:900000n}),true);
  c.runUntilPs(at-1n);const before=c.state();failed(c,()=>c.runUntilPs(at));
  const after=c.state();assert.equal(after.timePs,at);assert.equal(after.clki.level,initial^1);
  assert.equal(after.clki.aligned,before.clki.aligned);assert.equal(after.cpuPhase.retired,0n);assert.equal(c.cyc,0);
  assert.equal(c.r[20],0x75);assert.equal(c.pc,0);assert.equal(after.pins.contention&bit,bit);
  assert.equal(after.pins.driven&bit,bit);assert.equal(after.resetCount,0);
  if(mask)assert.ok(c.drainPinsPs().some(e=>e.timePs===at&&(e.contention&bit)));
});

test('a contended completion edge cannot retire the pending register write',()=>{
  const c=make(1);c.r[20]=0x75;source(c,1);c.runUntilPs(500000n);assert.equal(c.cyc,0.5);
  drive(c,0);assert.equal(c.state().pins.contention&bit,0);const before=c.state();
  failed(c,()=>c.runUntilPs(1000000n));assert.equal(c.cyc,0.5);assert.equal(c.r[20],0x75);
  assert.equal(c.state().cpuPhase.retired,before.cpuPhase.retired);assert.equal(c.state().timePs,1000000n);
});

for(const initial of [0,1])for(const action of ['DDRB','PORTB','PINB'])
test(`opposed ${action} write faults at its bus instant from CLKI level${initial}`,()=>{
  const c=make(initial);
  if(action==='DDRB')c.writeIO(IO.PORTB,initial?0:bit);else drive(c,initial);
  failed(c,()=>c.writeIO(IO[action],action==='DDRB'?bit:action==='PINB'?bit:initial?0:bit));
  assert.equal(c.state().timePs,0n);assert.equal(c.state().pins.contention&bit,bit);
  assert.equal(c.cyc,0);assert.equal(c.state().cpuPhase.retired,0n);
});

test('RESET at a source-edge tie releases the PB3 driver before sampling the pad',()=>{
  const c=make(1);drive(c,1);
  c.injectPinsPs({at:1000000n,mask:MASK.PINB5,levels:0});
  c.injectClkiPs({edges:[{timePs:1000000n,level:0}],knownUntilPs:2000000n});c.runUntilPs(2000000n);
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
  assert.equal(c.state().pins.driven&bit,0);assert.equal(c.state().pins.contention&bit,0);
  assert.equal(c.state().clki.level,0);assert.equal(c.state().cpuPhase.retired,0n);
});

for(const initial of [0,1])test(`RESET releases a matching PB3 output during a held level${initial}`,()=>{
  const c=make(initial);drive(c,initial);c.injectClkiPs({edges:[],knownUntilPs:2000000n});
  c.injectPinsPs({at:1000000n,mask:MASK.PINB5,levels:0});c.runUntilPs(2000000n);
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,true);assert.equal(c.state().deviceFault,0);
  assert.equal(c.state().pins.driven&bit,0);assert.equal(c.state().clki.level,initial);
  assert.ok(c.drainPinsPs().some(e=>e.timePs===1000000n&&!(e.driven&bit)));
});

for(const initial of [0,1])test(`WDT assertion wins a tied source edge and releases PB3 from level${initial}`,()=>{
  const c=make(initial);drive(c,initial);c.writeIO(IO.WDTCR,MASK.WDE);
  c.injectClkiPs({edges:[{timePs:16000000000n,level:initial^1}],knownUntilPs:17000000000n});
  c.runUntilPs(16000000000n);const state=c.state();
  assert.equal(state.deviceFault,0);assert.equal(state.resetCount,1);assert.equal(state.resetHeld,true);
  assert.equal(state.clki.startupCK,1n,'the coincident raw edge cannot discharge the WDT reset pulse');
  assert.equal(state.pins.driven&bit,0);assert.equal(state.pins.contention&bit,0);assert.equal(c.readIO(IO.MCUSR)&MASK.WDRF,MASK.WDRF);
});

test('qualified analog RESET wins the same tied PB3 edge without losing its receiver state',()=>{
  const resetInputProfile={assertThresholdPpm:400000,releaseThresholdPpm:600000,
    assertQualificationNs:0,releaseQualificationNs:0,assertPropagationNs:0,releasePropagationNs:0};
  const c=new ATtiny13A(image,null,{...options(1),resetInputProfile});drive(c,1);
  c.setAnalogPs({at:1000000n,pin:5,microvolts:0});
  c.injectClkiPs({edges:[{timePs:1000000n,level:0}],knownUntilPs:2000000n});c.runUntilPs(2000000n);
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().resetCount,1);assert.equal(c.state().resetInputAsserted,true);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().pins.driven&bit,0);assert.equal(c.state().pins.contention&bit,0);
});

test('an uncertain CLKI pad faults while MAIN is gated in Power-down',()=>{
  const c=make(1);drive(c,1);c.writeIO(IO.MCUCR,0x30);c._call('avr_device_control',1,0,0);
  assert.equal(c.state().sleeping,true);c.injectClkiPs({edges:[{timePs:1000000n,level:0}],knownUntilPs:2000000n});
  failed(c,()=>c.runUntilPs(1000000n));assert.equal(c.cyc,0);assert.equal(c.state().cpuPhase.retired,0n);
  assert.equal(c.state().pins.contention&bit,bit);
});

test('firmware enables the matching PB3 output and stops exactly at the first opposed source edge',()=>{
  const binary=sequential([avr.ldi(16,bit),avr.out(IO.PORTB,16),avr.out(IO.DDRB,16),avr.ldi(20,42)]),c=make(1,binary);
  source(c,1);assert.equal(c.runUntilPs(3000000n),3);assert.equal(c.state().pins.driven&bit,bit);
  assert.equal(c.state().deviceFault,0);assert.equal(c.pc,3);assert.equal(c.cyc,3);
  failed(c,()=>c.runUntilPs(3500000n));assert.equal(c.state().timePs,3500000n);
  assert.equal(c.cyc,3);assert.equal(c.state().cpuPhase.retired,3n);assert.equal(c.r[20],0);
});

test('packaged matching PB3 outputs retain the same held-clock semantics in verification',async()=>{
  for(const initial of [0,1]){
    const original=make(initial),{runtimeModule:_,...configuration}=options(initial);
    delete configuration.fastIdle;
    const pkg=await createPackage({flash:image,runtime,translated:original.transpiledBytes,configuration});
    const c=await ATtiny13A.fromPackage(pkg,{verification:true});drive(c,initial);
    c.injectClkiPs({edges:[],knownUntilPs:10000000n});c.runUntilPs(10000000n);
    assert.equal(c.state().pins.driven&bit,bit);assert.equal(c.state().pins.contention&bit,0);
    assert.equal(c.state().deviceFault,0);assert.equal(c.state().cpuPhase.retired,0n);
  }
});
