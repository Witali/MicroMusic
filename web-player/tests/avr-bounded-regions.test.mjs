import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A} from '../lib/attiny13a.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr,put} from './helpers/avr-test-state.mjs';
import {makePhaseProbe,phaseTrace,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';
const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false};
const brne=(pc,target)=>[0xf401|(((target-pc-1)&127)<<3)];
const program=[avr.ldi(16,128),[0x9405|(16<<4)],[0x9601],[0x01ec],[0x9402|(17<<4)],
  [0xfa00|(16<<4)|5],[0xf800|(18<<4)|2],[rr(0x1c00,19,20)],[rr(0x0800,21,22)],
  [rr(0x0400,23,24)],avr.eor(25,26),avr.inc(27),[rr(0x1000,19,20)],[0x9401|(20<<4)],
  [0x940a|(31<<4)],brne(31,16)];
const image=flash({instructions:[avr.rjmp(0,16)]},...Array.from({length:9},(_,n)=>({at:n+1,instructions:[avr.rjmp(n+1,64)]})),
  {at:16,instructions:[...program,avr.out(IO.PORTB,16),avr.rjmp(33,33)]},{at:64,instructions:[avr.inc(30),avr.reti()]});
const make=(binary=image,extra={})=>{const c=new ATtiny13A(binary,null,{...options,...extra});c.clock(8);c.pc=16;return c;};
const pair=(binary=image,extra={})=>[true,false].map(boundedRegions=>make(binary,{...extra,boundedRegions}));
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const same=(a,b,label)=>{assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);};
function oracleUntil(c,end){for(let at=c.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;c.runUntilPs(at);}}
test('bounded loops really execute32 instructions with full flags and staged signed/pair writes',()=>{
  const [a,b]=pair();assert.ok(a.transpilation.regions.some(r=>r.pcs.includes(16)&&r.pcs.includes(31)));
  for(let flags=0;flags<256;flags++){
    for(const c of [a,b]){c._call('avr_reset',0,0);c.clock(8);c.pc=16;c.sreg=flags;for(let n=0;n<32;n++)c.r[n]=(flags+n*17)&255;c.r[31]=10;}
    assert.equal(a._execute('block',Infinity,64),32);for(let n=0;n<32;n++)b.step();same(a,b,'SREG'+flags);
    assert.equal(a.r[16],a.state().cpuPhase.execPc===16?128:192,'ASR must read the cached LDI result');
  }
});
test('native clock sees old registers/flags and the region commits after completion',()=>{
  const c=makePhaseProbe(image,{...options,boundedRegions:true});c.clock(8);c.pc=16;c.r[16]=17;c.r[31]=10;c.sreg=0x73;clearPhaseProbe(c);
  assert.equal(c._execute('block',Infinity,64),32);
  const calls=phaseTrace(c).filter(row=>row.kind===E.PHASE_ENTER||row.kind===E.PHASE_EXIT);
  assert.equal(calls.length,2,'one actual native clock span');
  for(const row of calls){assert.equal(row.r16,17);assert.equal(row.sreg,0x73);}
  assert.equal(c.r[16],192);assert.equal(c.state().cpuPhase.retired,32n);
});

test('short physical deadlines admit smaller real regions, including exact and adjacent1ps ties',()=>{
  const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
  // maxCost=2: these endpoints distinguish a strict bound from a rounded-up
  // endpoint tie. Returns >0 are real region execution, not public run fallback.
  const cases=[[0n,0],[1n,0],[399999n,0],[400000n,0],[400001n,2],
    [599999n,2],[600000n,2],[600001n,3],[6400000n,31],[6400001n,32]];
  for(const optimizePhaseLocals of [false,true])for(const [span,count]of cases){
    const [a,b]=pair(loop,{fuseLow:0xf2,optimizePhaseLocals});
    for(const c of [a,b]){c.pc=0;c.r[16]=0xfe;c.sreg=0x73;}
    const start=a.state().timePs;
    assert.equal(a._execute('block',Number(start+span),64),count,'span '+span);
    for(let n=0;n<count;n++)b.step();same(a,b,'adaptive deadline '+span);
    if(count)assert.ok(a.state().timePs<start+span,'actual clock ends before the physical deadline');
  }
});

test('smaller regions retain clock-before-commit and stop before queued input or RESET',()=>{
  const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
  for(const reset of [false,true]){
    const config={...options,fuseLow:0xf2,boundedRegions:true};
    const a=makePhaseProbe(loop,config),b=makePhaseProbe(loop,{...config,boundedRegions:false});
    for(const c of [a,b]){c.clock(8);c.pc=0;c.r[16]=17;c.sreg=0x73;
      c.injectPinsPs({at:c.state().timePs+900000n,mask:reset?32:1,levels:reset?0:1});}
    const start=a.state().timePs;clearPhaseProbe(a);
    assert.equal(a._execute('block',Infinity,64),4);
    const clocks=phaseTrace(a).filter(row=>row.kind===E.PHASE_ENTER||row.kind===E.PHASE_EXIT);
    assert.equal(clocks.length,2);assert.equal(clocks[0].argument,12);
    for(const row of clocks){assert.equal(row.r16,17);assert.equal(row.sreg,0x73);}
    for(let n=0;n<4;n++)b.step();same(a,b,'before event');
    for(const offset of [899999n,900000n,900001n,1200001n]){
      a.runUntilPs(start+offset);oracleUntil(b,start+offset);same(a,b,'after event '+offset);
      assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
    }
  }
});

test('adaptive regions account for three-cycle skips and an early path exit',()=>{
  const loop=flash({instructions:[[rr(0x1000,0,1)],avr.lds(17,0x60),avr.inc(16),avr.rjmp(4,0)]});
  for(const equal of [false,true]){
    const [a,b]=pair(loop,{fuseLow:0xf2});
    for(const c of [a,b]){c.pc=0;c.r[0]=1;c.r[1]=equal?1:0;c.data[0x60]=0x5a;}
    const deadline=a.state().timePs+1000000n,count=equal?3:1;
    assert.equal(a.transpilation.regions.find(r=>r.pcs.includes(0)).maxCost,3);
    assert.equal(a._execute('block',Number(deadline),64),count);
    for(let n=0;n<count;n++)b.step();same(a,b,'three-cycle skip '+equal);
    assert.ok(a.state().timePs<deadline);
  }
});

test('exhausted or past cycle bounds decline without a float conversion trap or effects',()=>{
  const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
  for(const [cycles,bound]of [[8,8],[8,7.5],[8,-Infinity],
    [2**52-0.5,Infinity],[2**52-1,Infinity],[2**52,Infinity],[2**52+1,Infinity]]){
    const [a,b]=pair(loop,{fuseLow:0xf2});
    for(const c of [a,b]){c.pc=0;c.cyc=cycles;c.overflowAt=bound;}
    assert.equal(a._execute('block',Infinity,64),0);same(a,b,'bound '+cycles+'/'+bound);
  }
});

test('retirement headroom uses the smaller admitted budget without wrapping uint64',()=>{
  const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]});
  const [a,b]=pair(loop,{fuseLow:0xf2});
  for(const c of [a,b]){c.pc=0;new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,0xfffffffffffffffdn,true);}
  assert.equal(a._execute('block',Number(a.state().timePs+500000n),64),2);
  b.step();b.step();same(a,b,'last two retirements');
  assert.equal(a.state().cpuPhase.retired,0xffffffffffffffffn);
});

for(const peripheral of ['adc','watchdog'])test('adaptive regions preserve active '+peripheral+' across physical audio boundaries',()=>{
  const loop=flash({instructions:[avr.rjmp(0,16)]},
    ...Array.from({length:9},(_,n)=>({at:n+1,instructions:[avr.rjmp(n+1,64)]})),
    {at:16,instructions:[avr.inc(16),avr.eor(17,18),avr.add(19,20),avr.rjmp(19,16)]},
    {at:64,instructions:[avr.inc(30),avr.reti()]});
  const [a,b]=pair(loop,{fuseLow:0xf2});
  for(const c of [a,b]){
    c.sreg=128;
    if(peripheral==='adc'){c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,0xe7);}
    else c.writeIO(IO.WDTCR,0x40);
  }
  for(let n=0;n<32;n++){
    assert.deepEqual(a.capturePhysical(64,48000,1),b.capturePhysical(64,48000,1));
    same(a,b,peripheral+' sample batch '+n);assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
  }
  if(peripheral==='adc')assert.equal(a.data[32+IO.ADCSRA]&0x90,0x90,'enabled ADC actually completes conversions');
  else{assert.ok(a.irqCount>0,'watchdog actually enters its ISR');assert.ok(a.r[30]>0);}
});
test('every entry, short budget and path exit agrees with individual instructions',()=>{
  for(const pc of [16,18,23,28,31,32,33])for(const count of [1,2,3,7,16,31,32,33,64]){
    const [a,b]=pair();for(const c of [a,b]){c.pc=pc;c.r[31]=3;c.r[16]=0x80;c.sreg=0x73;}
    assert.equal(a.run(count),count);for(let n=0;n<count;n++)b.step();same(a,b,'PC'+pc+' count'+count);
    assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
  }
});
test('half edges and adjacent1ps deadlines fall back without speculative writes',()=>{
  for(let half=1n;half<=70n;half++)for(const delta of [-1n,0n,1n]){
    const [a,b]=pair(),end=a.state().timePs+half*50000n+delta;
    for(const c of [a,b]){c.r[31]=10;c.r[16]=17;c.sreg=0x73;}
    a.runUntilPs(end);oracleUntil(b,end);same(a,b,'deadline'+end);
  }
});
for(const kind of ['timer','comparator','pin','reset','eeprom-window','watchdog-window','clkpr'])
test('bounded regions preserve '+kind+' boundaries',()=>{
  const [a,b]=pair(),start=a.state().timePs;
  for(const c of [a,b]){
    c.r[31]=100;
    if(kind==='timer'){c.writeIO(IO.OCR0A,5);c.writeIO(IO.TIMSK0,4);c.writeIO(IO.TCCR0B,1);c.sreg=128;}
    if(kind==='comparator'){c.writeIO(IO.ACSR,8);c.sreg=128;c.setAnalogPs({at:start+350001n,pin:0,microvolts:2000000});}
    if(kind==='pin'){c.writeIO(IO.PCMSK,1);c.writeIO(IO.GIMSK,0x20);c.sreg=128;c.injectPinsPs({at:start+350001n,mask:1,levels:1});}
    if(kind==='reset')c.injectPinsPs({at:start+350001n,mask:32,levels:0});
    if(kind==='eeprom-window'){c.writeIO(IO.EEARL,3);c.writeIO(IO.EEDR,0x5a);c.writeIO(IO.EECR,4);}
    if(kind==='watchdog-window')c.writeIO(IO.WDTCR,0x18);
    if(kind==='clkpr'){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,3);}
  }
  for(const offset of [300000n,350000n,350001n,500001n,1100000n,2500001n,10000001n]){
    const end=start+offset;a.runUntilPs(end);oracleUntil(b,end);same(a,b,kind+' at'+offset);assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
  }
});
test('pending IRQ/delay/continuation/retirement headroom reject the whole region',()=>{
  const idle=flash({instructions:[avr.rjmp(0,0)]});
  for(const mode of ['irq','delay','active','overflow']){
    const [a,b]=[true,false].map(boundedRegions=>new ATtiny13A(idle,null,{...options,boundedRegions}));
    for(const c of [a,b]){
      if(mode==='irq'){c.writeIO(IO.EECR,8);c.sreg=128;}
      if(mode==='delay')c.irqDelay=1;
      if(mode==='active')c.runUntilPs(50001n);
      if(mode==='overflow')new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,0xfffffffffffffffen,true);
    }
    assert.equal(a._execute('block',Infinity,64),0,mode);same(a,b,mode);
  }
});
test('phase-local mode, cached re-entry and package dispatch preserve full state',async()=>{
  for(const optimizePhaseLocals of [false,true]){
    const [a,b]=pair(image,{optimizePhaseLocals});
    for(const value of [0,1,127,128,255]){for(const c of [a,b]){c.pc=16;c.r[31]=10;c.r[20]=value;c.sreg=value;}
      a.run(32);for(let n=0;n<32;n++)b.step();same(a,b,'edited input'+value);}
  }
  const [a]=pair(),runtime=readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url)),{fastIdle,...configuration}=options;
  const pkg=await createPackage({flash:image,runtime,translated:a.transpiledBytes,configuration});
  const c=await ATtiny13A.fromPackage(pkg);c.fastIdle=false;c.clock(8);c.pc=16;
  assert.equal(c._execute('block',Infinity,64),32);assert.equal(a.run(32),32);same(c,a,'package');
  const again=make(image,{boundedRegions:true});assert.equal(again._translatedModule,a._translatedModule);
  assert.throws(()=>new ATtiny13A(image,null,{...options,resumable:false,boundedRegions:true}),/require resumable/);
});
test('SBRC/SBRS and two-word skips retain path-dependent cycles and bus exits',()=>{
  for(const set of [false,true])for(const value of [0,1,128,255]){
    const code=flash({instructions:[[0xfc00|(16<<4)|(set?512:0)],avr.inc(17),avr.rjmp(2,0)]});
    const [a,b]=[true,false].map(boundedRegions=>new ATtiny13A(code,null,{...options,boundedRegions}));
    a.r[16]=b.r[16]=value;assert.equal(a._execute('block',Infinity,64),32);for(let n=0;n<32;n++)b.step();same(a,b,'bit skip');
  }
  const code=flash({instructions:[[rr(0x1000,0,1)],avr.lds(17,0x60),avr.inc(16),avr.rjmp(4,0)]});
  for(const equal of [false,true]){
    const [a,b]=[true,false].map(boundedRegions=>new ATtiny13A(code,null,{...options,boundedRegions}));
    for(const c of [a,b]){c.r[0]=1;c.r[1]=equal?1:0;c.data[0x60]=0x5a;}
    assert.equal(a.run(64),64);for(let n=0;n<64;n++)b.step();same(a,b,'two-word skip '+equal);
    assert.equal(a.r[17],equal?0:0x5a);
  }
});
test('oversized components fall back, and actual unequal CLKI never uses a positive region budget',()=>{
  const large=flash({instructions:[...Array.from({length:70},()=>avr.inc(16)),avr.rjmp(70,0)]});
  const [a,b]=[true,false].map(boundedRegions=>new ATtiny13A(large,null,{...options,boundedRegions}));
  assert.equal(a.transpilation.regions.length,0);a.run(200);for(let n=0;n<200;n++)b.step();same(a,b,'large SCC');
  const loop=flash({instructions:[avr.inc(16),avr.rjmp(1,0)]}),extra={resumable:true,fuseLow:0x70,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1},fastIdle:false};
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(loop,null,{...extra,boundedRegions}));
  for(const c of cores)c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:70000n,lowPs:30000n,transitionCount:2000n,knownUntilPs:100000000n});
  assert.equal(cores[0]._execute('block',Infinity,64),0);same(...cores,'CLKI region rejected');
  for(const end of [69999n,70000n,99999n,100000n,1234567n,5000001n]){cores[0].runUntilPs(end);oracleUntil(cores[1],end);same(...cores,'CLKI deadline');}
});
test('SPM invalidates region code before the next instruction fetch during a held clock',()=>{
  const code=flash({instructions:[[0x95e8],avr.rjmp(1,128)]},{at:128,instructions:[avr.ldi(20,17),avr.rjmp(129,129)]});
  const extra={resumable:true,fuseHigh:0xef,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1},
    nvmClockProfile:1,nvmCalibrationReferenceHz:9600000,spmCommandCycles:1};
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(code,null,{...extra,boundedRegions}));
  const stop=5000000000n;
  for(const c of cores){const old=c._translatedModule;c.r[31]=1;c.writeIO(IO.SPMCSR,3);
    c.injectClkiPs({edges:[],knownUntilPs:stop});assert.equal(c.runUntilPs(stop),1);assert.notEqual(c._translatedModule,old);}
  same(...cores,'SPM');assert.equal(cores[0].transpilation.boundedRegions,true);assert.equal(cores[0].transpilation.mapping[128].word,0xffff);
  for(const c of cores){c.injectClkiPeriodicPs({startPs:stop,initialLevel:1,highPs:50000n,lowPs:50000n,transitionCount:6n,knownUntilPs:stop+400000n});
    assert.equal(c.runUntilPs(stop+300000n),1);assert.equal(c.pc,128);assert.throws(()=>c.runUntilPs(stop+300001n),/Unsupported opcode/);assert.equal(c.r[20],0);}
  assert.deepEqual(snapshot(cores[0]),snapshot(cores[1]));
});
test('all eligible official forms execute through a real region with complete observable state',()=>{
  const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
  const code=new Uint8Array(1024).fill(255);
  for(const [n,entry]of instructions.entries()){
    put(code,n*3,parseInt(entry.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2));
    put(code,n*3+1,0);put(code,n*3+2,avr.rjmp(n*3+2,n*3)[0]);
  }
  const cores=[true,false].map(boundedRegions=>new ATtiny13A(code,null,{...options,boundedRegions}));
  const eligible=new Set(cores[0].transpilation.regions.flatMap(region=>region.pcs));let forms=0;
  for(const [n,entry]of instructions.entries())if(eligible.has(n*3)){
    forms++;
    for(let flags=0;flags<4;flags++){
      for(const c of cores){c._call('avr_reset',0,0);c.clock(8);c.pc=n*3;c.sreg=0x70|flags;for(let r=0;r<32;r++)c.r[r]=(0x96+r*29+flags*17)&255;}
      assert.equal(cores[0]._execute('block',Infinity,64),32,entry.form);
      for(let step=0;step<32;step++)cores[1].step();same(...cores,entry.form+' flags'+flags);
    }
  }
  assert.ok(forms>=60,'must cover the full eligible ALU/control subset, got'+forms);
});
