import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,mkdtempSync,writeFileSync} from 'node:fs';
import {join,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {compileAnalog} from './analog-test-build.mjs';
import {avr,IO,flash,sequential,sleepFixture} from './fixtures/attiny13a-system-firmware.mjs';

// Independent policy oracle: the exact current board is compiled in its own
// translation unit, renaming only its public pressure query. The real bridge
// sees an always-ready query and therefore collects eagerly at every phase
// barrier. Ordinary clock calls already retain their eager policy. Neither board scheduling nor
// generated CPU opcodes are copied or replaced by a test implementation.
const root=fileURLToPath(new URL('../../',import.meta.url));
const native=fileURLToPath(new URL('../native/avr.c',import.meta.url)).replaceAll('\\','/');
const device=fileURLToPath(new URL('../native/peripherals/device.c',import.meta.url)).replaceAll('\\','/');
const out=join(root,'build/analog-tests');mkdirSync(out,{recursive:true});
const alias=join(mkdtempSync(join(out,'audio-pressure-policy-')),'device-reference.c');
writeFileSync(alias,`#define device_pin_buffer_ready mm_reference_pin_buffer_ready\n#include ${JSON.stringify(device)}\n`);
const manifest=JSON.parse(readFileSync(new URL('../wasm/device-build.json',import.meta.url)));
const sources=manifest.sources.filter(path=>!['web-player/native/avr.c','web-player/native/peripherals/device.c'].includes(path));
sources.push(relative(root,alias).replaceAll('\\','/'));
const eager=compileAnalog('audio-pressure-eager',sources,`
#define AVR_FULL_DEVICE 1
#include ${JSON.stringify(native)}
int device_pin_buffer_ready(void) { return 1; }
`,{fixedMemoryPages:2});

const loop=sequential([]);
const table=()=>{const values=Array(128).fill(0);values[0]=9600000;return values;};
function pair(image=loop,options={}){
  return [new ATtiny13A(image,null,{...options,runtimeModule}),
    new ATtiny13A(image,null,{...options,runtimeModule:eager.module})];
}
function hardware(a,b){
  assert.deepEqual(a.state(),b.state());assert.deepEqual(a._state,b._state);
  assert.deepEqual(a.data,b.data);assert.deepEqual(a.rom,b.rom);assert.deepEqual(a.eeprom,b.eeprom);
  assert.deepEqual(Array.from(a.irqFrames),Array.from(b.irqFrames));
  assert.equal(a._exports.avr_device_generation(),b._exports.avr_device_generation());
}
function capture(cores,count,rate=48000,channels=2){
  const samples=cores.map(c=>c.capturePhysical(count,rate,channels));
  assert.deepEqual(samples[0],samples[1]);hardware(...cores);return samples[0];
}
function drain(c){return c._ps?c.drainPinsPs():c.drainPins();}
function pwm(c,{ctc=false}={}){
  c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,ctc?0:191);c.writeIO(IO.OCR0B,63);
  c.writeIO(IO.TCCR0A,ctc?MASK.COM0A0|MASK.WGM01:0xa3);c.writeIO(IO.TCCR0B,MASK.CS00);
}

test('the eager policy oracle uses fixed two-page memory without host imports',()=>{
  assert.deepEqual(WebAssembly.Module.imports(eager.module),[]);
  const exports=eager();assert.equal(exports.memory.buffer.byteLength,131072);
  assert.throws(()=>exports.memory.grow(1),RangeError);
  assert.equal(exports.device_pin_buffer_ready(),1);
  assert.equal(typeof exports.mm_reference_pin_buffer_ready,'function');
});

for(const physical of [false,true])for(const channels of [1,2])
  test(`${physical?'physical':'legacy'}: ordinary collection matches reference PCM and full state across sample/batch boundaries, channels${channels}`,()=>{
    const cores=pair(loop,physical?{osccalHz:table()}:{});cores.forEach(c=>pwm(c));
    for(const count of [1,17,53])capture(cores,count,44100,channels);
    cores.forEach(c=>c.clock(400));drain(cores[0]);
    capture(cores,11,44100,channels);
    // Only one host was drained during the pause. PCM and all hardware state
    // still agree; legacy auto-discard catches up at the completed sample.
    assert.deepEqual(drain(cores[0]),drain(cores[1]));
  });

for(const mode of ['legacy','physical','resumable'])for(const mask of [0,63])
  test(`${mode}: maximum-rate CTC crosses pressure and queue-wrap boundaries with host mask${mask}`,()=>{
    const options=mode==='legacy'?{}:{osccalHz:table(),resumable:mode==='resumable'};
    const cores=pair(loop,options);
    for(const c of cores){pwm(c,{ctc:true});c.observePins(mask,{retainDuringAudio:false});}
    //1200 output transitions/frame exceeds the1024-row ring.32 frames wrap
    // both private and default host queues repeatedly, including low heads.
    const samples=capture(cores,32,8000,2);
    for(let n=0;n<32;n++){assert.equal(samples[2*n],0);assert.equal(samples[2*n+1],-1);}
    assert.deepEqual(drain(cores[0]),drain(cores[1]));
    assert.equal(cores[0].state().deviceFault,0);
  });

test('timestamped input ties contribute only to the following sample',()=>{
  for(const physical of [false,true]){
    const cores=pair(loop,physical?{osccalHz:table(),resumable:true}:{});
    const period=physical?1000000000000n/48000n:400n;
    for(const c of cores){
      c.observePins(0,{retainDuringAudio:false});
      const inject=physical?event=>c.injectPinsPs(event):event=>c.injectPins(event);
      inject({at:period,mask:2,levels:2});inject({at:physical?2000000000000n/48000n:period*2n,mask:2,levels:0});
    }
    assert.deepEqual(capture(cores,3,48000,1),Float32Array.of(-1,1,-1));
  }
});

test('Timer0 IRQ entry, RETI and stack/frame bookkeeping remain identical',()=>{
  const image=flash({instructions:[avr.rjmp(0,16)]},{at:6,instructions:[avr.rjmp(6,64)]},
    {at:16,instructions:[avr.sei(),avr.rjmp(17,17)]},
    {at:64,instructions:[avr.sbi(IO.PINB,1),avr.inc(20),avr.reti()]});
  const cores=pair(image,{osccalHz:table(),resumable:true});
  for(const c of cores){
    c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,31);
    c.writeIO(IO.TCCR0A,MASK.COM0A0|MASK.WGM01);c.writeIO(IO.TCCR0B,MASK.CS00);
    c.writeIO(IO.TIMSK0,MASK.OCIE0A);
  }
  capture(cores,97);assert.ok(cores[0].irqCount>10);assert.ok(cores[0].r[20]>0);
  assert.deepEqual(drain(cores[0]),drain(cores[1]));
});

for(const mode of [0,2])test(`sleep${mode}: asynchronous watchdog wake and ISR match eager collection`,()=>{
  const cores=pair(sleepFixture(mode),{osccalHz:table(),resumable:true});
  for(const c of cores){c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);c.run(7);assert.equal(c.state().sleeping,true);}
  capture(cores,160,8000,1);assert.ok(cores[0].irqCount>0);assert.ok(cores[0].r[20]>0);
});

test('an asynchronous RESET aborts the OUT write and preserves its exact PCM prefix',()=>{
  const image=sequential([avr.ldi(16,1),avr.out(IO.PORTB,16)]);
  const cores=pair(image,{osccalHz:table(),resumable:true});
  for(const c of cores){
    c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);
    c.injectPinsPs({at:150000n,mask:32,levels:0});c.injectPinsPs({at:200000n,mask:32,levels:32});
  }
  const samples=capture(cores,4,48000,1);
  assert.ok(samples[0]>-1&&samples[0]<0);assert.equal(cores[0].state().resetCount,1);
  assert.equal(cores[0].readIO(IO.PORTB),1);hardware(...cores);
});

test('EEPROM read stalls and asynchronous programming completion preserve full memory and PCM',()=>{
  const image=sequential([avr.ldi(16,MASK.EERE),avr.out(IO.EECR,16),avr.in(17,IO.EEDR),
    avr.sts(0x60,17),avr.rjmp(5,1)]);
  const cores=pair(image,{osccalHz:table(),resumable:true,nvmClockProfile:1,nvmCalibrationReferenceHz:9600000});
  for(const c of cores){
    pwm(c);c.writeIO(IO.EEARL,0);c.writeIO(IO.EEDR,42);
    c.writeIO(IO.EECR,MASK.EEMPE);c.writeIO(IO.EECR,MASK.EEPE);
  }
  capture(cores,40,8000,2);assert.equal(cores[0].eeprom[0],42);assert.equal(cores[0].data[0x60],42);
});

for(const resumable of [false,true])test(`exceptional SPM700 preserves headroom after400 NOP transitions, resumable${resumable}`,()=>{
  const image=sequential([...Array.from({length:400},avr.nop),[0x95e8]]);
  const cores=pair(image,{osccalHz:table(),resumable,spmCommandCycles:700});
  for(const c of cores)pwm(c,{ctc:true});
  // The first8kHz sample is1200 CPU cycles. The700-cycle native barrier
  // individually fits the1024-row ring. The resumable policy must consume
  // its400 deferred older rows before advancing; ordinary eager collection
  // is the control for this same instruction sequence.
  for(let frame=0;frame<2;frame++){
    // Execute the independent eager oracle first, so a failing optimized
    // capture cannot hide whether this span actually fits the old policy.
    const expected=cores[1].capturePhysical(1,8000,2);
    assert.deepEqual(expected,Float32Array.of(0,-1));
    assert.deepEqual(cores[0].capturePhysical(1,8000,2),expected);hardware(...cores);
    assert.equal(cores[0].state().deviceFault,0);assert.equal(cores[0].cyc,(frame+1)*1200);
    assert.deepEqual(drain(cores[0]),drain(cores[1]));
    // Repeat after1200 consumed transitions to exercise wrapped ring heads.
    if(!frame)for(const c of cores)c.pc=0;
  }
});

for(const resumable of [false,true])test(`SPM long command keeps its original span and following commit, resumable${resumable}`,()=>{
  const cores=pair(sequential([[0x95e8],avr.inc(20)]),{osccalHz:table(),resumable,spmCommandCycles:160});
  for(const c of cores){
    c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,31);c.writeIO(IO.TCCR0A,MASK.COM0A0|MASK.WGM01);
    c.writeIO(IO.TCCR0B,MASK.CS00);c.r[30]=0;c.r[31]=1;c.writeIO(IO.SPMCSR,1);
  }
  capture(cores,64,192000,2);assert.equal(cores[0].r[20],1);
});

test('Flash programming halt, maximum-rate CTC and recompiled CPU match eager collection',()=>{
  const image=flash({instructions:[[0x95e8],avr.rjmp(1,1)]},{at:128,instructions:[avr.ldi(20,42)]});
  const cores=pair(image,{fuseHigh:0xef,osccalHz:table(),resumable:true,spmCommandCycles:4,
    nvmClockProfile:1,nvmCalibrationReferenceHz:9600000});
  for(const c of cores){pwm(c,{ctc:true});c.r[30]=0;c.r[31]=1;c.writeIO(IO.SPMCSR,3);}
  capture(cores,60,8000,2);
  assert.equal(cores[0]._exports.avr_device_generation(),1n);assert.equal(cores[0].rom[256],255);
  assert.equal(cores[0].state().halted,false);
});

for(const divide of [1,256])test(`CLKI divide${divide}: partial phases, clock holds and exact sample deadlines match eager collection`,()=>{
  const cores=pair(loop,{resumable:true,fuseLow:0x70,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  const stop=4n*1000000000000n/48000n;
  for(const c of cores){
    pwm(c);if(divide!==1){c.writeIO(IO.CLKPR,MASK.CLKPCE);c.writeIO(IO.CLKPR,8);}
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:700000n,lowPs:300000n,
      transitionCount:60n,knownUntilPs:stop}),true);
  }
  capture(cores,4,48000,2);assert.equal(cores[0].state().clki.status,'WAIT_CLOCK');
  for(const c of cores)assert.equal(c.injectClkiPeriodicPs({startPs:stop,initialLevel:1,
    highPs:500000n,lowPs:500000n,transitionCount:3000n,knownUntilPs:stop+2000000000n}),true);
  capture(cores,17,48000,2);capture(cores,47,48000,2);
  assert.equal(cores[0].state().deviceFault,0);assert.deepEqual(drain(cores[0]),drain(cores[1]));
});

test('long nonresumable span preserves ordinary-fault prefix time accounting',()=>{
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const cores=pair(sequential([[0x95e8],avr.inc(20)]),{osccalHz:table(),powerResetProfile,
    spmCommandCycles:160,nvmClockProfile:1,nvmCalibrationReferenceHz:9600000});
  for(const c of cores){
    pwm(c);c.writeIO(IO.EEDR,42);c.writeIO(IO.EECR,MASK.EEMPE);c.writeIO(IO.EECR,MASK.EEPE);
    c.setVccPs({at:1000000n,microvolts:1800000});
    assert.throws(()=>c.capturePhysical(2,8000,2),/peripheral fault 5, detail 128/);
  }
  hardware(...cores);assert.equal(cores[0].eeprom[0],255);assert.equal(cores[0].r[20],0);
  assert.ok(cores[0].cyc>=160,'the original long span charges through an ordinary fault');
});
