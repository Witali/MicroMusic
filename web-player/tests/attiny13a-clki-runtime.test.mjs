import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';
import {put,fields} from './helpers/avr-test-state.mjs';

const clkiProfile={phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1};
const options={resumable:true,clkiProfile,fuseLow:0x70,fastIdle:false,spmCommandCycles:1};
const make=(binary,extra={})=>new ATtiny13A(binary,null,{...options,...extra});
function edges(count,start=0n,high=70000n,low=30000n){
  let at=start,level=1;
  return Array.from({length:count},()=>{at+=level?high:low;level^=1;return{timePs:at,level};});
}
function feed(c,stream,knownUntilPs=stream.at(-1)?.timePs??c.state().timePs){
  assert.equal(c.injectClkiPs({edges:stream,knownUntilPs}),true);
}

test('all123 official forms execute from actual unequal CLKI phases with identical final CPU effects',()=>{
  const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
  const image=new Uint8Array(1024).fill(255);
  for(const [n,entry] of instructions.entries()){
    let word=parseInt(entry.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2);
    if(/^(IN|OUT)$/.test(entry.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
    if(/^(SBI|CBI|SBIC|SBIS)$/.test(entry.form))word|=IO.PORTB<<3;
    put(image,n*3,word);put(image,n*3+1,0);
  }
  const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
  const reference=new ATtiny13A(image,null,{oscillatorHz:10000000,osccalHz,fuseLow:0x72,fastIdle:false,spmCommandCycles:1});
  const actual=make(image);
  for(const [n,entry] of instructions.entries()){
    for(const c of [actual,reference]){
      c._call('avr_reset',0,0);c.pc=n*3;c.sreg=0x73;
      if(entry.form==='RET'||entry.form==='RETI')c.pushPC(1);
      if(entry.form==='POP')c.push(0xa5);
      if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])c.r[pointer]=97;
    }
    reference.step();const stream=edges(reference.cyc*2),end=stream.at(-1).timePs;
    feed(actual,stream,end);
    let retired=0;
    for(const at of stream.map(e=>e.timePs)){
      retired+=actual.runUntilPs(at-1n);assert.equal(actual.state().cpuPhase.retired,0n,entry.form+' early retirement');
      retired+=actual.runUntilPs(at);
    }
    assert.equal(retired,1,entry.form);assert.equal(actual.state().timePs,end);
    // CLKI is a real PB3 input, so PINB deliberately differs from an undriven
    // internal-clock fixture. All other register/data effects must match.
    for(let a=0;a<160;a++)if(a!==32+IO.PINB)assert.equal(actual.data[a],reference.data[a],entry.form+' data '+a);
    for(const field of fields)if(field!=='overflowAt')assert.equal(actual[field],reference[field],entry.form+' '+field);
    assert.equal(actual.state().deviceFault,0);assert.equal(actual.state().cpuPhase.active,0);
  }
});

test('initial low CLKI admits no CPU work until a real system rising phase',()=>{
  const c=make(sequential([avr.ldi(16,42)]),{clkiProfile:{...clkiProfile,initialLevel:0}});
  feed(c,[],100n);assert.equal(c.runUntilPs(100n),0);
  assert.equal(c.cyc,0);assert.equal(c.pc,0);assert.equal(c.r[16],0);assert.equal(c.state().clki.aligned,false);
  feed(c,[{timePs:110n,level:1},{timePs:130n,level:0},{timePs:170n,level:1}],170n);
  assert.equal(c.runUntilPs(110n),0);assert.equal(c.cyc,0);assert.equal(c.state().clki.aligned,true);
  assert.equal(c.runUntilPs(169n),0);assert.equal(c.r[16],0);assert.equal(c.cyc,.5);
  assert.equal(c.runUntilPs(170n),1);assert.equal(c.r[16],42);assert.equal(c.cyc,1);
});

test('OSCCAL remains writable while the external source is independent of the inactive RC curve',()=>{
  const c=make(sequential([avr.ldi(16,99),avr.out(IO.OSCCAL,16),avr.in(17,IO.OSCCAL)]));
  feed(c,edges(6));assert.equal(c.runUntilPs(300000n),3);
  assert.equal(c.r[17],99);assert.equal(c.readIO(IO.OSCCAL),99);assert.equal(c.cyc,3);
  assert.equal(c.state().oscillatorHz,0);assert.equal(c.state().deviceFault,0);
  assert.throws(()=>make(sequential([avr.nop()]),{wakeStartupHalf:1}),/whole source CK/);
});

test('whole-stream and arbitrary input batches preserve pin timestamps, CPU phases and retirement counts',()=>{
  const binary=sequential([avr.ldi(16,2),avr.out(IO.DDRB,16),avr.ldi(17,2),avr.out(IO.PORTB,17),
    avr.eor(17,16),avr.out(IO.PORTB,17),avr.rjmp(6,4)]);
  const a=make(binary),b=make(binary),stream=edges(200),end=stream.at(-1).timePs+123n;
  feed(a,stream,end);const expectedCount=a.runUntilPs(end),expected=a.drainPinsPs();
  let count=0,offset=0;const trace=b.drainPinsPs();
  for(const size of [1,7,3,29,2,83,75]){
    const chunk=stream.slice(offset,offset+size);offset+=size;feed(b,chunk);
    count+=b.runUntilPs(chunk.at(-1).timePs);trace.push(...b.drainPinsPs());
  }
  feed(b,[],end);count+=b.runUntilPs(end);trace.push(...b.drainPinsPs());
  assert.equal(count,expectedCount);assert.deepEqual(trace,expected);
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
});

test('CLKPR changes use actual old/new source periods and never extrapolate a held source',()=>{
  const binary=sequential([avr.ldi(16,128),avr.out(IO.CLKPR,16),avr.ldi(16,3),avr.out(IO.CLKPR,16),avr.ldi(17,42)]);
  const c=make(binary),stream=edges(10,0n,50000n,50000n);
  feed(c,stream,2000000n);
  assert.equal(c.runUntilPs(400000n),4);assert.equal(c.state().clockDivisor,1);
  assert.equal(c.runUntilPs(499999n),0);assert.equal(c.r[17],0);
  assert.equal(c.runUntilPs(500000n),1);assert.equal(c.r[17],42);assert.equal(c.state().clockDivisor,8);
  const cycles=c.cyc;c.runUntilPs(2000000n);assert.equal(c.cyc,cycles);
  assert.equal(c.state().cpuPhase.remainingHalves,4n);assert.equal(c.state().clki.status,'WAIT_CLOCK');
});

test('reset wins the CALL final-edge tie while retaining its previously committed low stack byte',()=>{
  const binary=flash({instructions:[avr.rjmp(0,0)]},{at:255,instructions:[[0xd000]]});
  const c=make(binary);c.pc=255;c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
  feed(c,edges(8,0n,50000n,50000n),400000n);
  c.injectPinsPs({at:300000n,mask:32,levels:0});c.injectPinsPs({at:400000n,mask:32,levels:32});
  assert.equal(c.runUntilPs(250000n),0);assert.equal(c.data[0x9f],0);assert.equal(c.sp,0x9e);
  assert.equal(c.runUntilPs(300000n),0);assert.equal(c.pc,0);assert.equal(c.sp,0x9f);
  assert.equal(c.data[0x9f],0);assert.equal(c.data[0x9e],0x5a);
  assert.equal(c.state().cpuPhase.active,0);assert.equal(c.state().cpuPhase.retired,0n);
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,true);
  c.runUntilPs(400000n);assert.equal(c.state().resetHeld,false);assert.equal(c.state().clki.queued,0);
});

for(const cancel of [false,true])test(`real CLKI pauses IRQ entry between stack phases${cancel?' and reset cancels its pending high byte':''}`,()=>{
  const binary=flash({instructions:[avr.rjmp(0,16)]},{at:1,instructions:[avr.ldi(20,90),avr.reti()]},
    {at:16,instructions:[avr.ldi(17,42),avr.rjmp(17,17)]});
  const c=make(binary);c.pc=16;c.sreg=128;c.writeIO(IO.GIMSK,64);
  c.data[0x9f]=0xa5;c.data[0x9e]=0x5a;
  feed(c,edges(2),100000n);assert.equal(c.runUntilPs(100000n),1);
  assert.equal(c.state().cpuPhase.active,2);assert.equal(c.irqCount,0);assert.equal(c.sreg&128,0);
  feed(c,edges(4,100000n),350000n);assert.equal(c.runUntilPs(350000n),0);
  assert.equal(c.sp,0x9e);assert.equal(c.data[0x9f],17);assert.equal(c.data[0x9e],0x5a);
  assert.equal(c.pc,17);assert.equal(c.irqCount,0);assert.equal(c.irqFrames.length,0);
  feed(c,[{timePs:400000n,level:0},{timePs:450000n,level:1},
    {timePs:500000n,level:0},{timePs:550000n,level:1}],600000n);
  if(cancel)c.injectPinsPs({at:450000n,mask:32,levels:0});
  c.runUntilPs(450000n);
  if(cancel){
    assert.equal(c.state().resetCount,1);assert.equal(c.pc,0);assert.equal(c.sp,0x9f);
    assert.equal(c.data[0x9f],17);assert.equal(c.data[0x9e],0x5a);
    assert.equal(c.state().cpuPhase.active,0);assert.equal(c.irqCount,0);assert.equal(c.irqFrames.length,0);
  }else{
    assert.equal(c.sp,0x9d);assert.equal(c.data[0x9e],0);assert.equal(c.irqCount,0);
    c.runUntilPs(550000n);assert.equal(c.pc,1);assert.equal(c.irqCount,1);
    assert.equal(c.irqFrames.length,1);assert.equal(c.state().cpuPhase.active,0);
    c.runUntilPs(600000n);assert.equal(c.r[20],0);assert.equal(c.state().cpuPhase.active,1);
    feed(c,[{timePs:650000n,level:0},{timePs:700000n,level:1}],700000n);
    assert.equal(c.runUntilPs(700000n),1);assert.equal(c.r[20],90);
  }
  assert.equal(c.state().cpuPhase.retired,cancel?1n:2n);assert.equal(c.state().deviceFault,0);
});

test('native PWM/audio sampling continues through a held source and stays invariant after CLKI resumes',()=>{
  const binary=sequential([avr.ldi(16,0),avr.out(IO.PORTB,16)]),a=make(binary),b=make(binary);
  const stop=8n*1000000000000n/48000n,end=16n*1000000000000n/48000n;
  for(const c of [a,b]){
    c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);feed(c,[],stop);
    assert.deepEqual(c.capturePhysical(8,48000),Float32Array.from({length:8},()=>1));
    assert.equal(c.cyc,0);assert.equal(c.state().cpuPhase.retired,0n);
    feed(c,edges(12,stop,50000n,50000n),end);
  }
  const expected=a.capturePhysical(8,48000),actual=new Float32Array(8);
  actual.set(b.capturePhysical(1,48000));actual.set(b.capturePhysical(3,48000),1);actual.set(b.capturePhysical(4,48000),4);
  assert.deepEqual(actual,expected);assert.ok(actual[0]>-1&&actual[0]<1);
  assert.deepEqual(actual.slice(1),Float32Array.from({length:7},()=>-1));
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.equal(a.state().timePs,end);assert.equal(a.state().deviceFault,0);
});

test('Flash erase completes and recompiles during a clock hold before any new instruction fetch',()=>{
  const binary=flash({instructions:[[0x95e8],avr.rjmp(1,128)]},{at:128,instructions:[avr.ldi(20,17),avr.rjmp(129,129)]});
  const c=make(binary,{fuseHigh:0xef,nvmClockProfile:1,nvmCalibrationReferenceHz:9600000});
  c.r[30]=0;c.r[31]=1;c.writeIO(IO.SPMCSR,3);const module=c._translatedModule,stop=5000000000n;
  feed(c,[],stop);assert.equal(c.runUntilPs(stop),1);
  assert.equal(c.cyc,0);assert.equal(c.pc,1);assert.equal(c.r[20],0);
  assert.equal(c._exports.avr_device_generation(),1n);assert.notEqual(c._translatedModule,module);
  assert.equal(c.transpilation.mapping[128].word,0xffff);assert.equal(c.state().cpuPhase.active,0);
  feed(c,edges(6,stop,50000n,50000n));assert.equal(c.runUntilPs(stop+300000n),1);
  assert.equal(c.pc,128);assert.equal(c.r[20],0);assert.equal(c.state().cpuPhase.retired,2n);
  assert.equal(c.state().deviceFault,0);
});

test('absolute CLKI timestamps remain exact beyond the f64 integer range across physical rebases',()=>{
  const c=make(sequential([avr.rjmp(0,0)])),base=(1n<<53n)+123n;
  feed(c,[],base);assert.equal(c.runUntilPs(base),0);assert.equal(c.state().timePs,base);assert.equal(c.cyc,0);
  c.drainPinsPs();feed(c,[{timePs:base+1n,level:0},{timePs:base+3n,level:1}],base+10n);
  assert.equal(c.runUntilPs(base+10n),0);assert.equal(c.state().timePs,base+10n);assert.equal(c.cyc,1);
  assert.deepEqual(c.drainPinsPs().map(e=>e.timePs),[base+1n,base+3n]);
  assert.equal(c.state().cpuPhase.remainingHalves,2n);assert.equal(c.state().deviceFault,0);
});

const qualified={...clkiProfile,electricalValidation:'datasheet-ideal-v1'};
for(const [vcc,period,width] of [[1800000,250000n,100000n],[2700000,100000n,40000n],[4500000,50000n,20000n]]){
  test(`qualified CLKI accepts the ${vcc}uV limit and rejects short real pulse widths`,()=>{
    const binary=sequential([avr.nop(),avr.nop(),avr.nop()]);
    const c=make(binary,{clkiProfile:qualified,vccMicrovolts:vcc});
    feed(c,edges(6,0n,period/2n,period/2n));assert.equal(c.runUntilPs(period*3n),3);
    assert.equal(c._exports.avr_device_clki_validation_enabled(),1);assert.equal(c.state().deviceFault,0);
    for(const highFault of [true,false]){
      const bad=make(binary,{clkiProfile:qualified,vccMicrovolts:vcc});
      const stream=highFault?[{timePs:width,level:0},{timePs:period,level:1},{timePs:period+width-1n,level:0}]:
        [{timePs:width,level:0},{timePs:2n*width-1n,level:1}];
      feed(bad,stream);
      assert.throws(()=>bad.runUntilPs(stream.at(-1).timePs),new RegExp('peripheral fault 18, detail '+(highFault?258:260)));
      assert.equal(bad.state().cpuPhase.retired,highFault?1n:0n,'Invalid source cannot retire the later effect');
      assert.equal(bad.state().timePs,stream.at(-1).timePs);
    }
  });
}

test('qualified CLKI diagnoses variation before the pending fourth LDI retires',()=>{
  const c=make(sequential([avr.ldi(16,1),avr.ldi(17,2),avr.ldi(18,3),avr.ldi(19,4)]),{clkiProfile:qualified});
  const stream=edges(6,0n,50000n,50000n);
  stream.push({timePs:350000n,level:0},{timePs:403000n,level:1});feed(c,stream);
  assert.throws(()=>c.runUntilPs(403000n),/peripheral fault 18, detail 272/);
  assert.equal(c.r[18],3);assert.equal(c.r[19],0);assert.equal(c.state().cpuPhase.retired,3n);
});

test('recognized RESET establishes a new variation baseline without fabricating a CLKI phase',()=>{
  const c=make(sequential([avr.rjmp(0,0)]),{clkiProfile:qualified});
  const stream=edges(6,0n,50000n,50000n);
  for(let at=400000n,level=0;at<=1300000n;at+=100000n,level^=1)stream.push({timePs:at,level});
  feed(c,stream);c.injectPinsPs({at:310000n,mask:32,levels:0});c.injectPinsPs({at:750000n,mask:32,levels:32});
  c.runUntilPs(1300000n);assert.equal(c.state().resetCount,1);assert.equal(c.state().resetHeld,false);
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().cpuPhase.retired,2n);
});

test('qualification retains the worst observed VCC between edges rather than trusting the restored endpoint',()=>{
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const c=make(sequential([avr.ldi(16,1),avr.ldi(17,2)]),{clkiProfile:qualified,powerResetProfile});
  feed(c,edges(4,0n,50000n,50000n));
  c.setVccPs({at:125000n,microvolts:2600000});c.setVccPs({at:126000n,microvolts:5000000});
  assert.throws(()=>c.runUntilPs(200000n),/peripheral fault 18, detail 258/);
  assert.equal(c.state().timePs,150000n);assert.equal(c.state().vccMicrovolts,5000000);
  assert.equal(c.r[16],1);assert.equal(c.r[17],0);
});

test('package v5 preserves ideal validation and requires its native capability export',async()=>{
  const {createPackage}=await import('../lib/attiny13a-package.js');
  const binary=sequential([avr.ldi(16,42)]),c=make(binary,{clkiProfile:qualified});
  const runtime=new Uint8Array(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url)));
  const configuration={resumable:true,clkiProfile:qualified,fuseLow:0x70,spmCommandCycles:1};
  const input={flash:binary,runtime,configuration,translated:c.transpiledBytes};
  const pkg=await createPackage(input),loaded=await ATtiny13A.fromPackage(pkg);
  feed(loaded,edges(2,0n,50000n,50000n));assert.equal(loaded.runUntilPs(100000n),1);
  assert.equal(loaded.r[16],42);assert.equal(loaded._exports.avr_device_clki_validation_enabled(),1);
  assert.equal(pkg.configuration.clkiProfile.electricalValidation,'datasheet-ideal-v1');
  const modified=new Uint8Array(runtime),name=Buffer.from('avr_device_clki_validation_enabled'),at=Buffer.from(modified).indexOf(name);
  assert.ok(at>0);modified[at+name.length-1]=88;assert.equal(WebAssembly.validate(modified),true);
  await assert.rejects(createPackage({...input,runtime:modified}),/runtime export mismatch: avr_device_clki_validation_enabled/);
});
