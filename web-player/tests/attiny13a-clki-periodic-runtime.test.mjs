import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const clkiProfile={phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1};
const options={resumable:true,clkiProfile,fuseLow:0x70,fastIdle:false};
const loop=sequential([avr.rjmp(0,0)]);
const make=(binary=loop,extra={})=>new ATtiny13A(binary,null,{...options,...extra});
function segment(c,{start=0n,initial=1,high=70000n,low=30000n,count=2000n,horizon}={}){
  const pairs=count/2n,end=start+pairs*(high+low)+(count&1n?(initial?high:low):0n);
  return c.injectClkiPeriodicPs({startPs:start,initialLevel:initial,highPs:high,lowPs:low,
    transitionCount:count,knownUntilPs:horizon??end});
}
function stream(count,start=0n,initial=1,high=70000n,low=30000n){
  let timePs=start,level=initial;
  return Array.from({length:count},()=>{timePs+=level?high:low;level^=1;return{timePs,level};});
}

test('a finite periodic source larger than the queue preserves every phase and pin timestamp',()=>{
  const binary=sequential([avr.ldi(16,2),avr.out(IO.DDRB,16),avr.ldi(17,2),avr.out(IO.PORTB,17),
    avr.eor(17,16),avr.out(IO.PORTB,17),avr.rjmp(6,4)]);
  const a=make(binary),b=make(binary),edges=stream(2000),horizon=100000123n;
  assert.equal(segment(a,{horizon}),true);
  assert.equal(a.state().clki.queued,512);assert.equal(a.state().clki.periodicRemaining,1488n);
  const actual=a.drainPinsPs(),expected=b.drainPinsPs();let aCount=0,bCount=0;
  for(let n=0;n<edges.length;n+=200){
    const batch=edges.slice(n,n+200),at=batch.at(-1).timePs;
    assert.equal(b.injectClkiPs({edges:batch,knownUntilPs:at}),true);
    aCount+=a.runUntilPs(at);bCount+=b.runUntilPs(at);
    actual.push(...a.drainPinsPs());expected.push(...b.drainPinsPs());
  }
  assert.equal(b.injectClkiPs({edges:[],knownUntilPs:horizon}),true);
  aCount+=a.runUntilPs(horizon);bCount+=b.runUntilPs(horizon);
  actual.push(...a.drainPinsPs());expected.push(...b.drainPinsPs());
  assert.equal(aCount,bCount);assert.deepEqual(actual,expected);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.equal(a.state().clki.periodicRemaining,0n);assert.equal(a.state().deviceFault,0);
});

test('20MHz periodic CLKI feeds complete native stereo PWM buffers without JavaScript source refills',()=>{
  const a=make(),b=make(),frames=16,rate=8000,end=BigInt(frames)*1000000000000n/BigInt(rate);
  for(const c of [a,b]){
    c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,191);c.writeIO(IO.OCR0B,63);
    c.writeIO(IO.TCCR0A,0xa3);c.writeIO(IO.TCCR0B,1);
    assert.equal(segment(c,{high:25000n,low:25000n,count:end/25000n}),true);
    // Neither module imports JavaScript; a single source descriptor covers
    // 80000 transitions, far beyond the512-slot source queue.
  }
  assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
  const expected=a.capturePhysical(frames,rate,2),actual=new Float32Array(frames*2);
  let offset=0;
  for(const count of [1,3,5,7]){actual.set(b.capturePhysical(count,rate,2),offset*2);offset+=count;}
  assert.deepEqual(actual,expected);assert.ok(expected.every(Number.isFinite));
  assert.ok(expected.some(v=>v!==expected[0]),'Both PWM channels must contribute');
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.equal(a.state().timePs,end);assert.equal(a.cyc,40000);
  assert.equal(a.state().deviceFault,0);assert.equal(a.state().clki.periodicRemaining,0n);
  assert.equal(a.state().clki.queued,0);
});

test('source backpressure and an extended final hold do not drop or reorder generated phases',()=>{
  const c=make();assert.equal(segment(c,{count:1000n}),true);
  const before=c.state();
  assert.equal(segment(c,{start:50000000n,count:2n}),false);assert.deepEqual(c.state(),before);
  assert.equal(c.injectClkiPs({edges:[{timePs:50000001n,level:0}],knownUntilPs:50000001n}),false);
  assert.deepEqual(c.state(),before);
  assert.equal(c.injectClkiPs({edges:[],knownUntilPs:60000000n}),true);
  for(let at=10000000n;at<=60000000n;at+=10000000n){c.runUntilPs(at);c.drainPinsPs();}
  assert.equal(c.state().timePs,60000000n);assert.equal(c.cyc,500);
  assert.equal(c.state().clki.periodicRemaining,0n);assert.equal(c.state().clki.queued,0);
  assert.equal(c.state().clki.status,'WAIT_CLOCK');assert.equal(c.state().deviceFault,0);
  assert.equal(segment(c,{start:60000000n,count:4n}),true);
  assert.equal(c.runUntilPs(60200000n),1);assert.equal(c.cyc,502);
});

test('20MHz CLKI keeps native audio streaming while Power-down halts CPU and the divided clock',()=>{
  const c=make(sequential([avr.sleep()])),end=2000000000n;
  c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);c.writeIO(IO.MCUCR,0x30);
  assert.equal(segment(c,{high:25000n,low:25000n,count:end/25000n}),true);
  assert.deepEqual(c.capturePhysical(16,8000),Float32Array.from({length:16},()=>1));
  assert.equal(c.state().timePs,end);assert.equal(c.state().sleeping,true);
  assert.equal(c.state().cpuPhase.retired,1n);assert.equal(c.cyc,1);
  assert.equal(c.state().clki.periodicRemaining,0n);assert.equal(c.state().deviceFault,0);
});

test('native capture drains CLK pin changes throughout the independent fuse startup timeout',()=>{
  const c=make(loop,{fuseLow:0x74,fuseStartupProfile:1}),end=1000000000n;
  assert.equal(segment(c,{high:25000n,low:25000n,count:end/25000n}),true);
  assert.deepEqual(c.capturePhysical(8,8000),Float32Array.from({length:8},()=>-1));
  assert.equal(c.state().timePs,end);assert.equal(c.state().starting,true);
  assert.equal(c.state().cpuPhase.retired,0n);assert.equal(c.state().deviceFault,0);
  assert.equal(c.state().clki.startupCK,20n);assert.equal(c.state().clki.periodicRemaining,0n);
});

for(const instruction of [[0x95c8],[0x9004],[0x9005]])
  test(`native audio drains source phases inside slow LPM0x${instruction[0].toString(16)} at CLKPR/256`,()=>{
    const binary=sequential([instruction]),c=make(binary);
    const osccalHz=Array(128).fill(0);osccalHz[0]=20000000;
    const reference=new ATtiny13A(binary,null,{resumable:true,osccalHz,oscillatorHz:20000000,
      fuseLow:0x72,fastIdle:false});
    for(const core of [c,reference]){core.writeIO(IO.CLKPR,128);core.writeIO(IO.CLKPR,8);}
    assert.equal(segment(c,{high:25000n,low:25000n,count:5000n}),true);
    assert.deepEqual(c.capturePhysical(1,8000),reference.capturePhysical(1,8000));
    assert.equal(c.state().deviceFault,0);assert.equal(c.state().timePs,125000000n);
    assert.equal(c.cyc,reference.cyc);assert.equal(c.pc,reference.pc);
    assert.deepEqual(c.state().cpuPhase,reference.state().cpuPhase);
    for(let a=0;a<160;a++)if(a!==32+IO.PINB)assert.equal(c.data[a],reference.data[a],'data'+a);
  });

test('buffered native IRQ entry retains its stack phases at CLKPR/256',()=>{
  const binary=flash({instructions:[avr.rjmp(0,0)]},{at:2,instructions:[avr.reti()]}),c=make(binary);
  const osccalHz=Array(128).fill(0);osccalHz[0]=20000000;
  const reference=new ATtiny13A(binary,null,{resumable:true,osccalHz,oscillatorHz:20000000,
    fuseLow:0x72,fastIdle:false});
  for(const core of [c,reference]){
    core.writeIO(IO.CLKPR,128);core.writeIO(IO.CLKPR,8);
    core.writeIO(IO.PCMSK,1);core.writeIO(IO.GIMSK,0x20);core.sreg=0x80;
    core.injectPinsPs({at:100000n,mask:1,levels:1});
  }
  assert.equal(segment(c,{high:25000n,low:25000n,count:5000n}),true);
  assert.deepEqual(c.capturePhysical(1,8000),reference.capturePhysical(1,8000));
  assert.equal(c.irqCount,1);assert.equal(c.irqCount,reference.irqCount);
  assert.equal(c.cyc,reference.cyc);assert.equal(c.pc,reference.pc);assert.equal(c.sp,reference.sp);
  assert.deepEqual(c.state().cpuPhase,reference.state().cpuPhase);
  for(let a=0;a<160;a++)if(a!==32+IO.PINB)assert.equal(c.data[a],reference.data[a],'data'+a);
  assert.equal(c.state().deviceFault,0);
});

test('periodic, raw and periodic segments share one phase-continuous source',()=>{
  const c=make();assert.equal(segment(c,{count:3n,horizon:200000n}),true);
  assert.equal(c.injectClkiPs({edges:[{timePs:230000n,level:1}],knownUntilPs:230000n}),true);
  assert.equal(segment(c,{start:230000n,count:4n}),true);
  assert.equal(c.runUntilPs(430000n),2);assert.equal(c.cyc,4);
  assert.deepEqual(c.drainPinsPs().filter(e=>e.timePs>0n).map(e=>[e.timePs,(e.levels>>3)&1]),
    [[70000n,0],[100000n,1],[170000n,0],[230000n,1],[300000n,0],[330000n,1],[400000n,0],[430000n,1]]);
  assert.equal(c.state().deviceFault,0);
});

test('a finite odd source stops low within an instruction and later resumes without replay',()=>{
  const c=make(sequential([avr.ldi(16,42)]));
  assert.equal(segment(c,{count:1n,horizon:1000000n}),true);
  assert.equal(c.runUntilPs(1000000n),0);assert.equal(c.cyc,.5);assert.equal(c.r[16],0);
  assert.equal(c.state().clki.level,0);assert.equal(c.state().cpuPhase.remainingHalves,1n);
  assert.equal(segment(c,{start:1000000n,initial:0,high:70000n,low:30000n,count:1n}),true);
  assert.equal(c.runUntilPs(1029999n),0);assert.equal(c.r[16],0);
  assert.equal(c.runUntilPs(1030000n),1);assert.equal(c.r[16],42);
  assert.equal(c.state().cpuPhase.retired,1n);assert.equal(c.state().clki.level,1);
});

test('a zero-transition segment is an exact hold, including unused very long phase durations',()=>{
  const c=make(),max=0xffffffffffffffffn;
  assert.equal(segment(c,{count:0n,high:max,low:max,horizon:1000000n}),true);
  assert.equal(c.runUntilPs(1000000n),0);assert.equal(c.cyc,0);assert.equal(c.pc,0);
  assert.equal(c.state().clki.queued,0);assert.equal(c.state().clki.level,1);
  assert.equal(c.state().clki.status,'WAIT_CLOCK');assert.equal(c.state().deviceFault,0);
});

test('invalid periodic descriptors leave native queue, phase and horizon unchanged',()=>{
  const c=make(),before=c.state(),valid={startPs:0n,initialLevel:1,highPs:70000n,lowPs:30000n,
    transitionCount:4n,knownUntilPs:200000n};
  for(const patch of [{highPs:0n},{lowPs:0n},{transitionCount:-1n},{initialLevel:2},{initialLevel:0},
    {startPs:1},{knownUntilPs:199999n},{transitionCount:0xffffffffffffffffn},
    {knownUntilPs:0xffffffffffffffffn}]){
    assert.throws(()=>c.injectClkiPeriodicPs({...valid,...patch}),/CLKI|timestamp|Timestamp/);
    assert.deepEqual(c.state(),before);
  }
  assert.equal(c.injectClkiPeriodicPs(valid),true);assert.equal(c.state().clki.queued,4);
});

test('generated source timestamps remain exact above2^53 and final hold advances without clock cycles',()=>{
  const c=make(),start=(1n<<53n)+123n;
  assert.equal(c.injectClkiPs({edges:[],knownUntilPs:start}),true);
  c.runUntilPs(start);c.drainPinsPs();
  assert.equal(segment(c,{start,high:7n,low:3n,count:4n,horizon:start+123n}),true);
  assert.equal(c.runUntilPs(start+123n),1);assert.equal(c.cyc,2);
  assert.equal(c.state().timePs,start+123n);
  assert.deepEqual(c.drainPinsPs().map(e=>e.timePs),[start+7n,start+10n,start+17n,start+20n]);
  assert.equal(c.state().deviceFault,0);
});

test('CPU reset cancels its instruction while retaining the future native periodic source',()=>{
  const c=make(),edges=2000n;assert.equal(segment(c,{count:edges}),true);
  c.injectPinsPs({at:1000000n,mask:32,levels:0});c.injectPinsPs({at:1500000n,mask:32,levels:32});
  for(let at=1000000n;at<=100000000n;at+=1000000n){c.runUntilPs(at);c.drainPinsPs();}
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,false);
  assert.equal(c.state().clki.queued,0);assert.equal(c.state().clki.periodicRemaining,0n);
  assert.equal(c.state().clki.level,1);assert.equal(c.state().timePs,100000000n);
  assert.equal(c.state().deviceFault,0);assert.ok(c.state().cpuPhase.retired>0n);
});

for(const initialLevel of [0,1])test(`periodic/raw GPIO wake agrees with CKDIV8 and initial source level${initialLevel}`,()=>{
  const binary=sequential([avr.sleep(),avr.ldi(17,77)]),extra={fuseLow:0x60,wakeStartupHalf:12,
    clkiProfile:{...clkiProfile,initialLevel}},a=make(binary,extra),b=make(binary,extra);
  const edges=stream(201,0n,initialLevel),end=12000000n;
  for(const c of [a,b]){
    c.injectPinsPs({at:0n,mask:2,levels:2});c.injectPinsPs({at:1235000n,mask:2,levels:0});
    c.writeIO(IO.GIMSK,64);c.writeIO(IO.MCUCR,0x30);
  }
  assert.equal(segment(a,{initial:initialLevel,count:201n,horizon:end}),true);
  assert.equal(b.injectClkiPs({edges,knownUntilPs:end}),true);
  assert.equal(a.runUntilPs(end),b.runUntilPs(end));
  assert.equal(a.r[17],77);assert.equal(a.state().sleeping,false);
  assert.equal(a.state().clockDivisor,8);assert.equal(a.state().deviceFault,0);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
});

test('CLKPR switching at a512-edge refill boundary preserves source, CPU and GPIO phases',()=>{
  const binary=sequential([...Array.from({length:252},avr.nop),avr.ldi(16,128),avr.out(IO.CLKPR,16),
    avr.ldi(16,3),avr.out(IO.CLKPR,16),avr.ldi(17,42)]),a=make(binary),b=make(binary),edges=stream(2048);
  assert.equal(segment(a,{count:2048n}),true);
  const actual=a.drainPinsPs(),expected=b.drainPinsPs();
  for(let n=0;n<edges.length;n+=128){
    const batch=edges.slice(n,n+128),end=batch.at(-1).timePs;
    assert.equal(b.injectClkiPs({edges:batch,knownUntilPs:end}),true);
    assert.equal(a.runUntilPs(end),b.runUntilPs(end));
    actual.push(...a.drainPinsPs());expected.push(...b.drainPinsPs());
    if(n===384){assert.equal(a.state().clockDivisor,1);assert.equal(a.r[17],0);}
  }
  assert.equal(a.state().clockDivisor,8);assert.equal(a.r[17],42);
  assert.equal(a.state().deviceFault,0);assert.deepEqual(actual,expected);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
});

test('optional qualification checks generated phases beyond the initially materialized queue',()=>{
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const c=make(loop,{powerResetProfile,clkiProfile:{...clkiProfile,electricalValidation:'datasheet-ideal-v1'}});
  assert.equal(segment(c,{count:1000n}),true);
  c.setVccPs({at:25600001n,microvolts:1800000});
  assert.throws(()=>c.runUntilPs(25670000n),/peripheral fault 18, detail 258/);
  assert.equal(c.state().timePs,25670000n);assert.equal(c.state().cpuPhase.retired,128n);
  assert.equal(c.state().resetCount,0);
});

test('a faulted device rejects raw and periodic admission without mutating its input stream',()=>{
  const c=make();assert.throws(()=>c.writeIO(IO.DDRB,8),/peripheral fault 18, detail 1/);
  const before=c.state();
  assert.throws(()=>segment(c,{count:4n}),/CLKI periodic segment/);assert.deepEqual(c.state(),before);
  assert.throws(()=>c.injectClkiPs({edges:[{timePs:1n,level:0}],knownUntilPs:1n}),/CLKI input batch/);
  assert.deepEqual(c.state(),before);
});
