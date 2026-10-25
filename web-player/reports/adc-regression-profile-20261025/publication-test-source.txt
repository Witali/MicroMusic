import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

// These bytes change through firmware writes/reset, rather than autonomous
// counting. They are still part of the public data view after clock service.
const registers=['ADCSRB','ADMUX','DIDR0','PCMSK','DDRB','PORTB','MCUCR','GIMSK',
  'EEDR','EEARL','PRR','TCCR0A','TCCR0B','OCR0A','OCR0B','TIMSK0'];
const rom=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
for(const clock of ['compatible','physical','clki'])test(`clock service republishes controller-owned I/O bytes: ${clock}`,()=>{
  const osccalHz=Array(128).fill(0);osccalHz[0]=20000000;
  const c=new ATtiny13A(rom,null,{oscillatorHz:20000000,fastIdle:false,
    fuseLow:clock==='clki'?0x70:0x72,
    ...(clock==='physical'?{resumable:true,osccalHz}:{}),
    ...(clock==='clki'?{resumable:true,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})});
  if(clock==='clki')assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,
    highPs:25000n,lowPs:25000n,transitionCount:200n,knownUntilPs:5000000n}),true);
  for(const [io,value]of [[IO.DDRB,2],[IO.PORTB,1],[IO.EEDR,0x5a],[IO.EEARL,0x2b],
    [IO.OCR0A,0x71],[IO.OCR0B,0x22],[IO.PRR,1]])c.writeIO(io,value);
  let at=0n;
  const advance=()=>{if(clock==='clki')c.runUntilPs(at+=200000n);else c.clock(1);};
  advance();advance();
  const before=c.state(),started=clock==='compatible'?before.baseHalf:before.timePs;
  const data=c.data,expected=registers.map(name=>data[32+IO[name]]);
  data[17]=0x5a; // CPU-owned GPR, outside the publication set.
  for(const [i,name]of registers.entries())data[32+IO[name]]=expected[i]^255;
  assert.deepEqual(registers.map(name=>data[32+IO[name]]),expected.map(n=>n^255),'raw shadow mutation is visible before service');
  advance();
  assert.deepEqual(registers.map(name=>data[32+IO[name]]),expected,'raw memory does not replace controller register state');
  assert.equal(data[17],0x5a);
  const after=c.state();assert.equal(after.deviceFault,0);
  assert.ok((clock==='compatible'?after.baseHalf:after.timePs)>started,'source time actually advances');
});
