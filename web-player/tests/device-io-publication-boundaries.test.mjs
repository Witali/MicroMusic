import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const registers=['ADCSRB','ADMUX','DIDR0','PCMSK','DDRB','PORTB','MCUCR','GIMSK',
  'EEDR','EEARL','PRR','TCCR0A','TCCR0B','OCR0A','OCR0B','TIMSK0'];
const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
const hz=20000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options=clock=>({oscillatorHz:hz,fuseLow:clock==='clki'?0x70:0x72,
  ...(clock==='physical'?{resumable:true,osccalHz}:{}),
  ...(clock==='clki'?{resumable:true,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})});
const make=(clock,binary=loop)=>new ATtiny13A(binary,null,options(clock));
const poison=c=>{for(const name of registers)c.data[32+IO[name]]^=255;};
for(const clock of ['compatible','physical','clki'])test(`I/O publication across zero-work, batch and direct entries: ${clock}`,()=>{
  const c=make(clock);c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,1);c.writeIO(IO.OCR0A,0x71);
  poison(c);const before=c.data.slice();
  if(clock==='clki')assert.throws(()=>c.run(0),/bounded CLKI/);else assert.equal(c.run(0),0);
  assert.deepEqual(c.data,before);
  if(clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,
    highPs:25000n,lowPs:25000n,transitionCount:200n,knownUntilPs:5000000n}),true);
  if(clock==='clki')c.runUntilPs(200000n);else c.run(10);
  for(let n=0;n<3;n++){
    assert.equal(c.data[32+IO.DDRB],2);assert.equal(c.data[32+IO.PORTB],1);
    assert.equal(c.data[32+IO.OCR0A],0x71);assert.equal(c.state().deviceFault,0);
    if(n===2)break;
    poison(c);
    // Bypass the host wrapper: standalone generated/native entry is public too.
    if(clock==='clki'){
      const end=200000*(n+2);c._exports.avr_device_phase_deadline(end);c._translated.runUntil(end);
    }else c._translated.run(10);
  }
});
test('unknown CLKI WAIT and a zero physical deadline do not eagerly normalize I/O',()=>{
  for(const clock of ['physical','clki']){
    const c=make(clock);poison(c);const before=c.data.slice();
    c.runUntilPs(clock==='clki'?100000n:0n);assert.deepEqual(c.data,before);
    assert.equal(c.state().deviceFault,0);
  }
});
for(const power of [false,true])test(`reset cancels a partial store and restores I/O shadows: power=${power}`,()=>{
  // Explicit synthetic thresholds, shared with the power integration tests.
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const binary=sequential([avr.ldi(16,0x5a),avr.sts(0x60,16)]);
  const c=new ATtiny13A(binary,null,{...options('physical'),...power?{powerResetProfile}:{}});
  c.step();c.writeIO(IO.PORTB,3);poison(c);const at=c.state().timePs+37n;
  if(power)c.setVccPs({at,microvolts:0});else c.injectPinsPs({at,mask:32,levels:0});
  c.runUntilPs(200000n);
  assert.equal(c.data[0x60],0);assert.equal(c.state().resetCount,1);
  assert.equal(c.data[32+IO.PORTB],0);assert.equal(c.state().resetHeld,true);
  if(power)c.setVccPs({at:250000n,microvolts:5000000});else c.injectPinsPs({at:250000n,mask:32,levels:32});
  poison(c);c.runUntilPs(300000n);
  assert.equal(c.data[32+IO.PORTB],0);assert.equal(c.state().resetHeld,false);
  assert.equal(c.state().deviceFault,0);
});
test('faults preserve publication at their original boundary',()=>{
  const c=make('physical',sequential([avr.ldi(16,7),avr.out(IO.ADCSRB,16)]));
  assert.throws(()=>c.run(2),/peripheral fault 4, detail 7/);assert.equal(c.data[32+IO.ADCSRB],7);
  const stopped=make('physical');stopped.error=1;poison(stopped);const before=stopped.data.slice();
  assert.throws(()=>stopped.run(1));assert.deepEqual(stopped.data,before);
});
test('a WASM trap restores native exports without eagerly publishing memory',()=>{
  const c=make('physical'),native=c._exports,run=c._bridges.run.translated;
  const trap=new WebAssembly.Instance(new WebAssembly.Module(Uint8Array.from([
    0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,7,8,1,4,116,114,97,112,0,0,10,5,1,3,0,0,11]))).exports.trap;
  c._bridges.run.translated=trap;poison(c);const before=c.data.slice();
  assert.throws(()=>c.run(1),WebAssembly.RuntimeError);
  assert.equal(c._exports,native);assert.deepEqual(c.data,before);
  c._bridges.run.translated=run;c.run(1);assert.equal(c.data[32+IO.PORTB],0);
});
