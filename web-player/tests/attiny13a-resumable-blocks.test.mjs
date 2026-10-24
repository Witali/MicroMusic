import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr,immediate} from './helpers/avr-test-state.mjs';
import {makePhaseProbe,phaseTrace,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';

const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;osccalHz[1]=9000000;
const body=[avr.ldi(16,255),avr.ldi(17,1),avr.add(16,17),[rr(0x1c00,18,19)],
  [immediate(0x4000,18,5)],[0x9407|(18<<4)],[0xfa00|(18<<4)|3],
  [0xf800|(20<<4)|5],[0x9601],[0x9701],avr.eor(21,22),avr.inc(23)];
function image(instructions=body){const end=16+instructions.flat().length;
  return flash({instructions:[avr.rjmp(0,16)]},
    ...Array.from({length:9},(_,n)=>({at:n+1,instructions:[avr.rjmp(n+1,64)]})),
    {at:16,instructions:[...instructions,avr.rjmp(end,end)]},
    {at:64,instructions:[avr.inc(25),avr.reti()]});}
function make(binary=image(),extra={}){
  const c=new ATtiny13A(binary,null,{resumable:true,osccalHz,oscillatorHz:hz,
    fuseLow:0x72,fastIdle:false,...extra});
  c.clock(8);c.pc=16;return c;
}
function snapshot(c){return {state:c.state(),diagnostics:Array.from(c._state),
  data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irqFrames:Array.from(c.irqFrames)};}
function same(a,b,label){assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);}
function oracleUntil(c,end){
  // Each observation lies <=0.1 CPU cycle away, so a >=2-instruction block
  // cannot pass its guard. Retain the production generated instruction path.
  for(let at=c.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;c.runUntilPs(at);}
}

test('resumable ALU blocks execute and retain every live flag/register and full retirement count',()=>{
  for(let seed=0;seed<256;seed+=7){const a=make(),b=make();
    for(const c of [a,b]){for(let r=0;r<32;r++)c.r[r]=(seed*17+r*29)&255;c.sreg=seed;}
    const count=a._execute('block',Infinity,64);
    assert.equal(count,body.length,'the optimized path must actually run');
    for(let n=0;n<count;n++)b.step();same(a,b,'seed '+seed);
    assert.equal(a.state().cpuPhase.retired,BigInt(count));
    assert.equal(a.state().cpuPhase.execPc,16+count-1);
  }
});

for(const bounded of [false,true])
test(`${bounded?'runUntil':'run'} actually executes a complete block through the native clock bridge`,()=>{
  const a=makePhaseProbe(image(),{resumable:true,osccalHz,oscillatorHz:hz,fuseLow:0x72,fastIdle:false}),b=make();
  a.clock(8);a.pc=16;clearPhaseProbe(a);
  if(bounded){const end=a.state().timePs+1400001n;a.runUntilPs(end);oracleUntil(b,end);}
  else{assert.equal(a.run(body.length),body.length);for(let n=0;n<body.length;n++)b.step();}
  same(a,b,'public runner full state');
  const calls=phaseTrace(a).filter(event=>event.kind===E.PHASE_ENTER);
  assert.equal(calls[0].argument,28,'one actual14-cycle block clock call must replace the individual phases');
  assert.equal(calls.filter(event=>event.argument===28).length,1);
});

test('instruction limits and exact or fractional physical deadlines reject whole-block overrun',()=>{
  for(const offset of [1n,49999n,50000n,50001n,99999n,100000n,100001n,1199999n,1200000n,1200001n,1399999n,1400000n,1400001n]){
    const a=make(),b=make(),end=a.state().timePs+offset;
    a.runUntilPs(end);oracleUntil(b,end);same(a,b,'offset '+offset);
  }
  const a=make(),b=make();assert.equal(a._execute('block',Infinity,body.length-1),0);
  same(a,b,'rejected instruction budget');
  assert.equal(a.run(body.length-1),body.length-1);for(let n=0;n<body.length-1;n++)b.step();same(a,b,'run budget');
});

test('a suspended instruction bypasses blocks and resumes its saved phase exactly once',()=>{
  const a=make(),b=make(),start=a.state().timePs;
  for(const c of [a,b])c.runUntilPs(start+50001n);
  assert.equal(a.state().cpuPhase.active,1);
  assert.equal(a._execute('block',Infinity,64),0);same(a,b,'active phase cannot enter block');
  a.runUntilPs(start+1600001n);oracleUntil(b,start+1600001n);same(a,b,'resumed result');
});

test('a ready IRQ level permits blocks only with global interrupts masked',()=>{
  const a=make(),b=make();for(const c of [a,b]){c.writeIO(IO.EECR,8);c.sreg=0;}
  assert.equal(a._execute('block',Infinity,64),body.length);
  for(let n=0;n<body.length;n++)b.step();same(a,b,'ready level with I clear');
  for(const c of [a,b]){c.pc=16;c.sreg=128;}
  assert.equal(a._execute('block',Infinity,64),0);same(a,b,'pending enabled IRQ rejects block');
});

test('internal block dispatch preserves PC faults and interrupt-delay boundaries',()=>{
  for(const pc of [-1,512])for(const bounded of [false,true]){
    const a=make(),b=make();for(const c of [a,b])c.pc=pc;
    assert.throws(()=>bounded?a.runUntilPs(a.state().timePs+1000000n):a.run(1),/PC out of Flash/);
    assert.throws(()=>b.step(),/PC out of Flash/);same(a,b,'invalid PC '+pc);
  }
  const a=make(),b=make();for(const c of [a,b])c.irqDelay=1;
  assert.equal(a._execute('block',Infinity,64),0);same(a,b,'interrupt delay rejects whole block');
  a.run(body.length);for(let n=0;n<body.length;n++)b.step();same(a,b,'delay expires on first retirement');
});

for(const kind of ['timer','comparator','pin','reset','eeprom-window','watchdog-window','clkpr','osccal'])
test(`resumable blocks preserve ${kind} boundaries and all observable CPU/device state`,()=>{
  const instructions=Array.from({length:30},(_,n)=>avr.inc(16+n%8));
  const a=make(image(instructions)),b=make(image(instructions)),start=a.state().timePs;
  for(const c of [a,b]){
    if(kind==='timer'){c.writeIO(IO.OCR0A,5);c.writeIO(IO.TIMSK0,4);c.writeIO(IO.TCCR0B,1);c.sreg=128;}
    if(kind==='comparator'){c.writeIO(IO.ACSR,8);c.sreg=128;c.setAnalogPs({at:start+350001n,pin:0,microvolts:2000000});}
    if(kind==='pin'){c.writeIO(IO.PCMSK,1);c.writeIO(IO.GIMSK,0x20);c.sreg=128;c.injectPinsPs({at:start+350001n,mask:1,levels:1});}
    if(kind==='reset')c.injectPinsPs({at:start+350001n,mask:32,levels:0});
    if(kind==='eeprom-window'){c.writeIO(IO.EEARL,3);c.writeIO(IO.EEDR,0x5a);c.writeIO(IO.EECR,4);}
    if(kind==='watchdog-window')c.writeIO(IO.WDTCR,0x18);
    if(kind==='clkpr'){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,3);}
  }
  for(const offset of [300000n,350000n,350001n,500001n,1100000n,2500001n,4000000n]){
    const end=start+offset;a.runUntilPs(end);oracleUntil(b,end);same(a,b,kind+' at '+offset);
    assert.deepEqual(a.drainPinsPs(),b.drainPinsPs(),kind+' physical pins');
    if(kind==='osccal'&&offset===350001n)for(const c of [a,b])c.writeIO(IO.OSCCAL,1);
  }
});

test('register/I/O aliases and multicycle bus effects stay on the generated instruction path',()=>{
  const binary=image([avr.add(16,17),avr.stx(16),avr.ldx(18),avr.inc(19),avr.inc(20)]);
  for(const address of [0,16,32+IO.PORTB,0x60,0x9f]){const a=make(binary),b=make(binary);
    for(const c of [a,b]){c.r[16]=1;c.r[17]=2;c.r[26]=address;}
    a.run(5);for(let n=0;n<5;n++)b.step();same(a,b,'address '+address);
  }
});

test('retirement counters near uint64 overflow fall back without wrapping a whole block',()=>{
  const a=make(),b=make();
  for(const c of [a,b])new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,0xfffffffffffffffen,true);
  assert.equal(a._execute('block',Infinity,64),0);same(a,b,'near overflow rejects block');
  a.run(1);b.step();same(a,b,'last available retirement');
  assert.equal(a.state().cpuPhase.retired,0xffffffffffffffffn);
  assert.throws(()=>a.run(1));assert.throws(()=>b.step());same(a,b,'overflow faults on the original instruction');
});

for(const start of [0xfffffffen,0xffffffffffffffffn-BigInt(body.length)])
test(`accepted blocks preserve the full retirement counter starting at ${start}`,()=>{
  const a=make(),b=make();
  for(const c of [a,b])new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,start,true);
  assert.equal(a._execute('block',Infinity,64),body.length);
  for(let n=0;n<body.length;n++)b.step();same(a,b,'accepted counter boundary');
  assert.equal(a.state().cpuPhase.retired,start+BigInt(body.length));
});

test('accepted blocks retain a starting half cycle and strict deadline ties',()=>{
  for(const delta of [-1n,0n,1n]){
    const a=make(),b=make();for(const c of [a,b])c.clock(0.5);
    const relative=1400000n+delta,end=a.state().timePs+relative;
    a._call('avr_device_rebase_time');
    assert.equal(a._execute('block',Number(relative),64),delta===1n?body.length:0);
    if(delta===1n){for(let n=0;n<body.length;n++)b.step();same(a,b,'accepted half-phase block');}
    a.runUntilPs(end);oracleUntil(b,end);same(a,b,'half-phase deadline '+delta);
  }
});

test('unbounded blocks fall back before physical uint64 time overflow',()=>{
  const slow=Array(128).fill(0);slow[0]=1;
  const binary=image(Array.from({length:30},()=>avr.inc(16)));
  const cores=Array.from({length:2},()=>new ATtiny13A(binary,null,{
    resumable:true,osccalHz:slow,oscillatorHz:1,fuseLow:0x72,fastIdle:false}));
  for(const c of cores){c.clock(18446740);c.pc=16;}
  const [a,b]=cores;
  assert.equal(a._execute('block',Infinity,64),0,'unsafe whole span must fall back without mutation');
  same(a,b,'physical timestamp capacity rejects block');
  assert.throws(()=>a.run(30));assert.throws(()=>{for(let n=0;n<30;n++)b.step();});
  assert.deepEqual(snapshot(a),snapshot(b),'fault preserves the exact successful instruction prefix');
  assert.equal(a.state().cpuPhase.retired,4n);assert.equal(a.r[16],4);
});

for(const resumable of [false,true])
test(`rounded physical endpoints preserve instructions before a tied reset (${resumable?'resumable':'ordinary'})`,()=>{
  const frequency=9000000,cal=Array(128).fill(0);cal[0]=frequency;
  const binary=flash({instructions:[avr.ldi(16,1),avr.inc(16),avr.rjmp(2,2)]});
  for(const delta of [-1n,0n,1n]){
    const cores=Array.from({length:2},()=>new ATtiny13A(binary,null,{
      resumable,osccalHz:cal,oscillatorHz:frequency,fuseLow:0x72,fastIdle:false}));
    for(const c of cores)c.injectPinsPs({at:222223n+delta,mask:32,levels:0});
    const [a,b]=cores;
    a.run(2);b.step();b.step();same(a,b,'9MHz rounded endpoint '+delta);
    assert.equal(a.r[16],delta===1n?2:1);
  }
});

test('bounded CLKI keeps individual phases and never claims an unproved positive block budget',()=>{
  const c=new ATtiny13A(image(),null,{resumable:true,fastIdle:false,fuseLow:0x70,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  c.pc=16;c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:70000n,lowPs:30000n,
    transitionCount:100n,knownUntilPs:5000000n});
  assert.equal(c._execute('block',Infinity,64),0);assert.equal(c.cyc,0);
  c.runUntilPs(5000000n);assert.equal(c.state().deviceFault,0);
});
