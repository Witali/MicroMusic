import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const osccalHz=Array(128).fill(0);osccalHz[50]=9600000;osccalHz[51]=9696000;
const options={factoryOsccal96:50,osccalHz};
const image=sequential([avr.rjmp(0,0)]);
const core=extra=>new ATtiny13A(image,null,{...options,...extra});
function pwm(extra){
  const c=core(extra);c.writeIO(0x17,3);c.writeIO(0x36,191);c.writeIO(0x29,63);
  c.writeIO(0x2f,0xa3);c.writeIO(0x33,1);return c;
}

test('calibration changes CPU frequency while physical timestamps keep their unit',()=>{
  const c=core();c.clock(96);assert.equal(c.state().timePs,10000000n);
  c.writeIO(0x31,51);assert.equal(c.state().oscillatorHz,9696000);
  c.clock(9696);assert.equal(c.state().timePs,1010000000n);
  assert.equal(c.state().deviceFault,0);assert.equal(c.readIO(0x31),51);
  assert.throws(()=>c.runUntil(1n),/runUntilPs/);
  assert.throws(()=>c.drainPins(),/drainPinsPs/);assert.equal(c.state().deviceFault,0);
  const legacy=new ATtiny13A(image);assert.throws(()=>legacy.runUntilPs(1n),/fixed oscillator profile/);
});

test('generated AVR writes OSCCAL and retains the calibrated frequency in subsequent instructions',()=>{
  const c=new ATtiny13A(sequential([avr.ldi(16,51),avr.out(0x31,16),avr.ldi(17,42)]),null,options);
  c.run(3);assert.equal(c.r[17],42);assert.equal(c.state().oscillatorHz,9696000);
  // Two initial cycles plus one calibrated cycle, quantized up to1ps.
  assert.ok(c.state().timePs>=311468n&&c.state().timePs<=311470n);
  c.runUntilPs(1000000n);assert.ok(c.state().timePs>=1000000n);
  assert.equal(c.state().deviceFault,0);
});

test('physical digital/analog injections and pin trace use explicit picosecond APIs',()=>{
  const c=core();c.drainPinsPs();
  c.injectPinsPs({at:1000000n,mask:1,levels:1});c.setAnalogPs({at:2000000n,pin:2,microvolts:1234567});
  c.runUntilPs(3000000n);
  assert.ok(c.drainPinsPs().some(e=>e.timePs===1000000n&&(e.levels&1)));
  assert.equal(c.state().deviceFault,0);
  assert.throws(()=>c.injectPinsPs({at:1n<<64n,mask:1,levels:1}),/uint64/);
});

for(const physical of [true,false])test(`audio starts from current pins after a drained ${physical?'picosecond':'legacy'} trace`,()=>{
  const c=physical?core():new ATtiny13A(image);
  c.writeIO(0x17,2);c.writeIO(0x18,2);physical?c.drainPinsPs():c.drainPins();
  assert.ok(c.state().pins.levels&2);assert.deepEqual(c.capturePhysical(3,8000),Float32Array.of(1,1,1));
});

for(const rate of [44100,96000])test(`calibrated PWM stays identical with/without idle acceleration and arbitrary ${rate}Hz batches`,()=>{
  const a=pwm(),b=pwm({fastIdle:false});
  a.capturePhysical(13,rate,2);b.capturePhysical(13,rate,2);
  a.writeIO(0x31,51);b.writeIO(0x31,51);
  const expected=a.capturePhysical(2173,rate,2),actual=new Float32Array(4346);
  actual.set(b.capturePhysical(1,rate,2));actual.set(b.capturePhysical(17,rate,2),2);actual.set(b.capturePhysical(2155,rate,2),36);
  assert.deepEqual(actual,expected);assert.deepEqual({...a.state(),idleCycles:0},b.state());assert.deepEqual(a.data,b.data);
  assert.equal(a.state().deviceFault,0);
});

test('fixed physical clock agrees with the existing oscillator-half PWM integration',()=>{
  const a=pwm(),b=new ATtiny13A(image,null,{factoryOsccal96:50});b.writeIO(0x17,3);b.writeIO(0x36,191);b.writeIO(0x29,63);b.writeIO(0x2f,0xa3);b.writeIO(0x33,1);
  //37500Hz lands exactly on oscillator half edges. Other rates differ because
  // the original model quantizes sample endpoints to a half oscillator period.
  const actual=a.capturePhysical(512,37500,2),expected=b.capturePhysical(512,37500,2);
  for(let i=0;i<actual.length;i++)assert.ok(Math.abs(actual[i]-expected[i])<2e-7,`sample ${i}`);
  assert.equal(a.cyc,b.cyc);assert.deepEqual(a.data,b.data);
});

test('rebasing a capture preserves samples already crossed by a slow instruction',()=>{
  const a=pwm({fuseLow:0x6a}),b=pwm({fuseLow:0x6a});
  for(const c of [a,b]){c.writeIO(0x26,128);c.writeIO(0x26,8);c.clock(300);}
  const expected=a.capturePhysical(37,192000,2),actual=new Float32Array(74);
  for(let i=0;i<37;i++)actual.set(b.capturePhysical(1,192000,2),i*2);
  assert.deepEqual(actual,expected);assert.deepEqual(a.state(),b.state());
});

test('absolute picosecond input time remains exact beyond the f64 integer limit',()=>{
  const c=core(),release=(1n<<53n)+17n;
  c.injectPinsPs({at:0n,mask:32,levels:0});c.injectPinsPs({at:release,mask:32,levels:32});
  c.runUntilPs(release);assert.equal(c.state().timePs,release);assert.equal(c.state().resetHeld,false);
  const events=c.drainPinsPs();assert.ok(events.some(e=>e.timePs===release));
  c.runUntilPs(release+1000000n);assert.ok(c.state().timePs>=release+1000000n);
  assert.equal(c.state().deviceFault,0);
});
