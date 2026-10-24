import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// TOP=0 remains unmeasured: these assert the uncertainty boundary, not a
// predicted silicon counter waveform. DS40002307A11.7.4/Table11-8.
for(const resumable of [false,true]){
  const mode=resumable?'physical continuation':'compatible clock';
  const make=()=>new ATtiny13A(sequential([
    ...Array.from({length:7},()=>avr.nop()),avr.inc(16),avr.rjmp(8,8),
  ]),null,{oscillatorHz:1000000,fuseLow:0x7a,fuseStartupProfile:0,fastIdle:false,
    ...(resumable?{resumable:true,osccalHz:Array(128).fill(1000000)}:{})});
  const advance=(cpu,half)=>resumable?cpu.runUntilPs(half*500000n):cpu.runUntil(half);
  const drain=cpu=>resumable?cpu.drainPinsPs():cpu.drainPins();
  const pendingTop=(cpu,source)=>{
    cpu.writeIO(IO.TCCR0A,0x61);cpu.writeIO(IO.TCCR0B,8|source);
    cpu.writeIO(IO.OCR0A,3);cpu.writeIO(IO.OCR0B,1);
    drain(cpu);
  };
  test(`zero active TOP with pending OCR3 faults at the first /8 pulse: ${mode}`,()=>{
    const cpu=make();pendingTop(cpu,2);
    advance(cpu,14n);
    assert.equal(cpu.pc,7);assert.equal(cpu.r[16],0);
    assert.equal(cpu.readIO(IO.TCNT0),0);assert.equal(cpu.readIO(IO.TIFR0),0);
    assert.equal(cpu.readIO(IO.OCR0A),3);assert.equal(cpu.readIO(IO.OCR0B),1);
    assert.throws(()=>advance(cpu,16n),/peripheral fault 3, detail 6/);
    assert.equal(cpu.state().deviceFault,3);assert.equal(cpu.r[16],0,'Uncompleted INC must not publish');
    assert.equal(cpu.data[32+IO.TCNT0],0);assert.equal(cpu.data[32+IO.TIFR0],0);
    assert.deepEqual(drain(cpu),[],'No invented OC transition');
    if(resumable)assert.equal(cpu.state().timePs,8000000n);
    else assert.equal(cpu.state().baseHalf,16n);
  });
  test(`zero active TOP may be configured and held without a timer pulse: ${mode}`,()=>{
    for(const source of [0,7]){
      const cpu=make();pendingTop(cpu,source);
      if(resumable)cpu.injectPinsPs({at:0n,mask:MASK.PINB2,levels:0});
      else cpu.injectPins({at:0n,mask:MASK.PINB2,levels:0});
      advance(cpu,100n);
      assert.equal(cpu.state().deviceFault,0);assert.equal(cpu.readIO(IO.TCNT0),0);
      assert.equal(cpu.readIO(IO.TIFR0),0);assert.equal(cpu.readIO(IO.OCR0A),3);
      if(source===7){
        if(resumable)cpu.injectPinsPs({at:50500000n,mask:MASK.PINB2,levels:MASK.PINB2});
        else cpu.injectPins({at:101n,mask:MASK.PINB2,levels:MASK.PINB2});
        assert.throws(()=>advance(cpu,112n),/peripheral fault 3, detail 6/);
        assert.equal(cpu.data[32+IO.TCNT0],0);assert.equal(cpu.data[32+IO.TIFR0],0);
      }
    }
  });
  test(`non-PWM preload establishes known TOP3 before WGM5: ${mode}`,()=>{
    const cpu=make();cpu.writeIO(IO.OCR0A,3);cpu.writeIO(IO.OCR0B,1);
    cpu.writeIO(IO.TCCR0A,0x61);cpu.writeIO(IO.TCCR0B,9);
    advance(cpu,12n);
    assert.equal(cpu.readIO(IO.TCNT0),0);assert.equal(cpu.readIO(IO.OCR0A),3);
    assert.equal(cpu.readIO(IO.TIFR0)&14,14);assert.equal(cpu.state().deviceFault,0);
  });
}
