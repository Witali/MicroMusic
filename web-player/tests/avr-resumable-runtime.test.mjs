import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {sameCPU,put} from './helpers/avr-test-state.mjs';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
const physical={oscillatorHz:10000000,osccalHz,fuseLow:0x7a,wakeStartupHalf:0,fastIdle:false,spmCommandCycles:1};
const options={...physical,resumable:true};
const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const valueOf=p=>parseInt(p.replaceAll(' ','').replace(/[^01]/g,'0'),2);
const image=new Uint8Array(1024).fill(255);
instructions.forEach((entry,n)=>{
  let word=valueOf(entry.opcodePattern);
  // Zero-valued operand placeholders name reserved I/O0 on this device. Use
  // its actual PORTB so coverage tests defined instructions and bus behavior.
  if(/^(IN|OUT)$/.test(entry.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
  if(/^(SBI|CBI|SBIC|SBIS)$/.test(entry.form))word|=IO.PORTB<<3;
  put(image,n*3,word);put(image,n*3+1,0);
});

test('all123 official instruction forms resume at half edges and intervening physical deadlines',()=>{
  const complete=new ATtiny13A(image,null,physical),sliced=new ATtiny13A(image,null,options);
  assert.equal(WebAssembly.validate(sliced.transpiledBytes),true);
  assert.equal(sliced.transpilation.executionMode,'resumable-v1');
  assert.equal(sliced.transpilation.stats.blocks,0);
  for(const [n,entry] of instructions.entries()){
    for(const core of [complete,sliced]){
      core._call('avr_reset',0,0);core.pc=n*3;
      if(entry.form==='RET'||entry.form==='RETI')core.pushPC(1);
      if(entry.form==='POP')core.push(0xa5);
      if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])core.r[pointer]=97;
      core.sreg=0x73;
    }
    assert.doesNotThrow(()=>complete.step(),entry.form);const end=complete.state().timePs;
    const deadlines=new Set([1n,end]);
    for(let at=50000n;at<end;at+=50000n)for(const d of [-1n,0n,1n])deadlines.add(at+d);
    let retired=0;
    for(const at of [...deadlines].filter(t=>t<=end).sort((a,b)=>a<b?-1:1)){
      retired+=sliced.runUntilPs(at);
      assert.equal(sliced.state().timePs,at,entry.form+' bounded wall time');
      assert.equal(sliced.state().cpuPhase.retired,at===end?1n:0n,entry.form+' retirement boundary');
    }
    assert.equal(retired,1,entry.form+' exactly one retirement');
    assert.equal(sliced.state().cpuPhase.active,0,entry.form+' completed context');
    sameCPU(sliced,complete,entry.form);
    assert.deepEqual(sliced.eeprom,complete.eeprom,entry.form+' EEPROM');
    assert.equal(sliced.state().deviceFault,0,entry.form);
  }
});

test('bounded run resumes an instruction; explicit step/run restores an unbounded CPU span',()=>{
  const binary=sequential([avr.ldi(16,42),avr.ldi(17,81)]);
  for(const finish of [c=>c.step(),c=>assert.equal(c.run(1),1)]){
    const c=new ATtiny13A(binary,null,options);
    assert.equal(c.runUntilPs(1n),0);assert.equal(c.r[16],0);assert.equal(c.pc,0);
    assert.equal(c.state().cpuPhase.active,1);assert.equal(c.state().cpuPhase.remainingHalves,2n);
    finish(c);assert.equal(c.r[16],42);assert.equal(c.pc,1);assert.equal(c.cyc,1);
    assert.equal(c.state().cpuPhase.retired,1n);
    c.runUntilPs(150000n);assert.equal(c.r[17],0);
    assert.equal(c.run(1),1);assert.equal(c.r[17],81);assert.equal(c.cyc,2);
  }
});

test('continuation layout and execution mode participate in translation identity',()=>{
  const binary=sequential([avr.ldi(16,42)]);
  const legacy=new ATtiny13A(binary,null,physical),a=new ATtiny13A(binary,null,options),b=new ATtiny13A(binary,null,options);
  assert.equal(b.translationCacheHit,true);assert.equal(a._translatedModule,b._translatedModule);
  assert.notEqual(a._translatedModule,legacy._translatedModule);
  assert.equal(legacy.transpilation.abi.phase,undefined);
  assert.equal(legacy.state().cpuPhase,undefined);
  assert.deepEqual(WebAssembly.Module.imports(a._translatedModule).slice(-3).map(e=>e.name),['phaseClock','phaseDeadline','phaseRetire']);
  assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
  const exports=new WebAssembly.Instance(runtimeModule).exports,abi=runtimeABI(exports,{resumable:true});
  assert.equal(abi.phase.bytes,80);
  assert.throws(()=>transpileAVR(binary,runtimeABI(exports),{resumable:true}),/phase ABI/);
  assert.throws(()=>transpileAVR(binary,{...abi,phase:{...abi.phase,locals:abi.phase.pointer+79}},{resumable:true}),/context layout/);
  assert.throws(()=>transpileAVR(binary,{...abi,phase:{...abi.phase,stage:abi.phase.active}},{resumable:true}),/context layout/);
  assert.throws(()=>new ATtiny13A(binary,null,{resumable:true}),/physical OSCCAL/);
  assert.throws(()=>new ATtiny13A(binary,null,{...physical,resumable:1}),/boolean/);
  assert.throws(()=>new ATtiny13A(binary,null,{...options,precompiled:{bytes:legacy.transpiledBytes,manifest:legacy.transpilation}}),/execution mode mismatch/);
  assert.equal(a.skipIdle(),false);
  assert.throws(()=>a.nextDuty(),/capturePhysical/);assert.throws(()=>a.capturePWM(1),/capturePhysical/);
});

test('package v4 rejects the additional continuation ABI and execution mode',async()=>{
  const {createPackage}=await import('../lib/attiny13a-package.js');
  const binary=sequential([avr.ldi(16,42)]),c=new ATtiny13A(binary,null,options);
  await assert.rejects(createPackage({flash:binary,translated:c.transpiledBytes,
    runtime:new Uint8Array(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url)))}),/unexpected ABI layout fields/);
});

test('SLEEP retires its zero-clock tail while immediate INT0 wake is recovering BOD',()=>{
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const c=new ATtiny13A(sequential([avr.sleep()]),null,{...options,powerResetProfile,fuseLow:0x72,fuseHigh:0xfb});
  c.writeIO(IO.MCUCR,0x30);c.writeIO(IO.GIMSK,64);
  c.writeIO(IO.BODCR,3);c.writeIO(IO.BODCR,2);
  assert.equal(c.runUntilPs(1000000n),1);
  assert.equal(c.pc,1);assert.equal(c.state().timePs,1000000n);
  assert.equal(c.state().cpuPhase.active,0);assert.equal(c.state().cpuPhase.retired,1n);
  assert.equal(c.state().bodRecovering,true);assert.equal(c.state().deviceFault,0);
});

for(const rate of [44100,192000])test(`resumable native PWM capture is invariant under arbitrary ${rate}Hz batch boundaries`,()=>{
  const binary=sequential([avr.rjmp(0,0)]);
  const make=()=>{
    const c=new ATtiny13A(binary,null,options);
    c.writeIO(0x17,3);c.writeIO(0x36,191);c.writeIO(0x29,63);c.writeIO(0x2f,0xa3);c.writeIO(0x33,1);
    return c;
  };
  const a=make(),b=make(),frames=139,expected=a.capturePhysical(frames,rate,2),actual=new Float32Array(frames*2);
  let offset=0;
  for(const n of [1,17,3,118]){actual.set(b.capturePhysical(n,rate,2),offset*2);offset+=n;}
  assert.deepEqual(actual,expected);assert.deepEqual(a.state(),b.state());assert.deepEqual(a.data,b.data);
  assert.equal(a.state().timePs,BigInt(Math.floor(frames*1e12/rate)));
  assert.ok(a.state().cpuPhase.active===0||a.state().cpuPhase.active===1);
  assert.equal(a.state().deviceFault,0);
});
