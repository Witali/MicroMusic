import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage,decodePackage} from '../lib/attiny13a-package.js';
import {normalizeResetInputProfile} from '../lib/devices/attiny13a-reset-profile.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// Synthetic fixture: these thresholds/delays are explicit choices, not a
// datasheet claim about a particular chip's analog RESET transfer function.
const resetInputProfile={assertThresholdPpm:400000,releaseThresholdPpm:600000,
  assertQualificationNs:50,releaseQualificationNs:30,assertPropagationNs:20,releasePropagationNs:10};
const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
const options={oscillatorHz:10000000,osccalHz,resetInputProfile,fuseLow:0x72};
const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
  bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
  bodHysteresisMicrovolts:50000,bodFilterNs:20,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
const loop=sequential([avr.rjmp(0,0)]),core=extra=>new ATtiny13A(loop,null,{...options,...extra});
// Observe precise board endpoints without retiring guest instructions. The
// multicycle test below separately exercises the generated CPU barrier path.
function wait(c,target){
  while(c.state().timePs<target){
    const before=c.state().timePs,origin=BigInt.asUintN(64,c._exports.avr_device_rebase_time());
    c._call('avr_device_wait',Number(target-origin));
    // Native wait advances halted hardware only. An awake fixture charges CPU
    // clocks directly; an asynchronous assertion truncates that span exactly.
    if(c.state().timePs===before)c.clock(Math.ceil(Number(target-before)/100000));
    assert.ok(c.state().timePs>before,'physical wait must make progress');
  }
}
const analog=(c,at,microvolts)=>c.setAnalogPs({at,pin:5,microvolts});
const immediateProfile={...resetInputProfile,assertQualificationNs:0,releaseQualificationNs:0,
  assertPropagationNs:0,releasePropagationNs:0};

test('atomic POR/RESET source handoff never releases the common hold or creates another CPU reset',()=>{
  const c=core({powerResetProfile,resetInputProfile:immediateProfile});
  analog(c,0n,0);assert.equal(c.state().resetCount,1);
  c.setVccPs({at:0n,microvolts:0});assert.equal(c.state().resetCount,1);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetInputAsserted,false);
  c.setVccPs({at:0n,microvolts:5000000});
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetInputAsserted,true);
  assert.equal(c.state().resetCount,1);assert.equal(c.readIO(IO.MCUSR),3);
  const cold=core({powerResetProfile,resetInputProfile:immediateProfile,vccMicrovolts:0});
  analog(cold,0n,0);cold.setVccPs({at:0n,microvolts:5000000});
  assert.equal(cold.state().resetHeld,true);assert.equal(cold.state().resetCount,0);
});

test('analog RESET and the digital bypass each retain hold when the other releases',()=>{
  for(const analogFirst of [false,true]){
    const c=core({resetInputProfile:immediateProfile});
    const digital=levels=>c.injectPinsPs({at:0n,mask:32,levels});
    if(analogFirst){analog(c,0n,0);digital(0);analog(c,0n,5000000);}
    else{digital(0);analog(c,0n,0);digital(32);}
    assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
    if(analogFirst)digital(32);else analog(c,0n,5000000);
    assert.equal(c.state().resetHeld,false);assert.equal(c.state().resetCount,1);
  }
});

test('watchdog reset preserves pending analog qualification rather than restarting the voltage receiver',()=>{
  const c=core({resetInputProfile:{...immediateProfile,assertQualificationNs:17000000}});
  c.writeIO(IO.WDTCR,8);analog(c,10n,0);wait(c,16000000000n);
  assert.equal(c.state().resetCount,1);assert.equal(c.state().resetInputAsserted,false);
  assert.equal(c.state().resetInputDeadlinePs,17000000010n);
  wait(c,17000000010n);assert.equal(c.state().resetInputAsserted,true);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,2);
});

test('analog RESET aborts a generated multicycle SRAM store at its qualified physical timestamp',()=>{
  const c=new ATtiny13A(sequential([avr.ldi(16,0x5a),avr.sts(0x60,16)]),null,options);
  c.step();assert.equal(c.state().timePs,100000n);
  analog(c,100037n,0);c.step();
  assert.equal(c.state().timePs,170037n);assert.equal(c.pc,0);assert.equal(c.data[0x60],0);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetInputAsserted,true);
  assert.equal(c.state().resetCount,1);assert.equal(c.readIO(IO.MCUSR),3);
  analog(c,300000n,5000000);c.runUntilPs(339999n);assert.equal(c.state().resetHeld,true);
  c.runUntilPs(340000n);assert.equal(c.state().resetHeld,false);assert.equal(c.state().deviceFault,0);
});

test('a pulse one ps shorter than qualification is filtered without resetting the CPU',()=>{
  const c=core();analog(c,100037n,0);analog(c,150036n,5000000);c.runUntilPs(200000n);
  assert.equal(c.state().resetCount,0);assert.equal(c.state().resetHeld,false);
  assert.equal(c.readIO(IO.MCUSR),1);assert.equal(c.state().resetInputDeadlinePs,0xffffffffffffffffn);
});

test('hysteresis retains RESET in the threshold band and release waits for both profile stages',()=>{
  const c=core();analog(c,0n,0);wait(c,70000n);assert.equal(c.state().resetHeld,true);
  analog(c,80000n,2500000);wait(c,200000n);assert.equal(c.state().resetHeld,true);
  analog(c,210000n,3000000);wait(c,249999n);assert.equal(c.state().resetHeld,true);
  wait(c,250000n);assert.equal(c.state().resetHeld,false);assert.equal(c.state().resetCount,1);
});

test('reversing the pad during propagation cancels a stale pending assertion',()=>{
  const c=core();analog(c,0n,0);analog(c,69999n,5000000);wait(c,100000n);
  assert.equal(c.state().resetHeld,false);assert.equal(c.state().resetCount,0);
});

test('thresholds track VCC atomically while an unselected analog pad follows its pull-up',()=>{
  const c=core({powerResetProfile});analog(c,0n,2100000);
  c.setVccPs({at:100000n,microvolts:5500000});wait(c,170000n);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
  c.setVccPs({at:200000n,microvolts:3000000});wait(c,240000n);
  assert.equal(c.state().resetHeld,false);
  const d=core({powerResetProfile});d.setVccPs({at:100000n,microvolts:3000000});wait(d,300000n);
  assert.equal(d.state().resetHeld,false);assert.equal(d.state().resetCount,0);
});

test('BOD and analog RESET aggregate causes and release only after the final source',()=>{
  const c=core({powerResetProfile,fuseHigh:0xfb});
  c.setVccPs({at:100000n,microvolts:2600000});wait(c,120000n);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
  analog(c,150000n,0);wait(c,220000n);assert.equal(c.readIO(IO.MCUSR),7);
  c.setVccPs({at:250000n,microvolts:5000000});wait(c,250000n);assert.equal(c.state().resetHeld,true);
  analog(c,300000n,5000000);wait(c,340000n);
  assert.equal(c.state().resetHeld,false);assert.equal(c.state().resetCount,1);
});

test('RSTDISBL gates the RESET role without disabling the receiver diagnostic',()=>{
  const c=core({fuseHigh:0xfe});analog(c,0n,0);c.runUntilPs(200000n);
  assert.equal(c.state().resetInputAsserted,true);assert.equal(c.state().resetHeld,false);
  assert.equal(c.state().resetCount,0);assert.equal(c.readIO(IO.MCUSR),1);
});

test('prequalified digital RESET remains an explicit independent bypass',()=>{
  const c=core();c.injectPinsPs({at:37n,mask:32,levels:0});wait(c,37n);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
  assert.equal(c.state().resetInputAsserted,false);
  c.injectPinsPs({at:100n,mask:32,levels:32});wait(c,100n);assert.equal(c.state().resetHeld,false);
});

test('fuse startup begins after qualified analog release, with no duplicate timeout',()=>{
  const c=core({fuseStartupProfile:1});wait(c,2000000n);
  analog(c,2100000n,0);wait(c,2170000n);
  analog(c,2200000n,5000000);wait(c,2240000n);
  assert.equal(c.state().startupDeadlinePs,4240000n);assert.equal(c.state().starting,true);
  wait(c,4240000n);assert.equal(c.state().halted,false);assert.equal(c.state().resetCount,1);
});

test('physical audio capture includes the analog reset edge without per-edge host callbacks',()=>{
  const c=core();c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);
  analog(c,31180000n,0); // qualified assertion at31,250,000ps in a125us sample
  assert.deepEqual(c.capturePhysical(3,8000),Float32Array.of(-.5,-1,-1));
  assert.equal(c.state().resetCount,1);assert.equal(c.state().deviceFault,0);
});

test('RESET package retains the exact explicit profile and executes its supplied translation',async()=>{
  const runtime=new Uint8Array(await readFile(new URL('../wasm/attiny13a.wasm',import.meta.url)));
  const abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
  const profile={...resetInputProfile},pkg=await createPackage({flash:loop,runtime,
    translated:transpileAVR(loop,abi).bytes,configuration:{...options,resetInputProfile:profile}});
  assert.equal(pkg.version,5);profile.assertQualificationNs=999;
  const decoded=await decodePackage(pkg);assert.deepEqual(decoded.configuration.resetInputProfile,resetInputProfile);
  decoded.options.resetInputProfile.assertQualificationNs=777;
  assert.equal(decoded.configuration.resetInputProfile.assertQualificationNs,50);
  const c=await ATtiny13A.fromPackage(pkg);analog(c,0n,0);c.runUntilPs(70000n);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);
  const bad=structuredClone(pkg);bad.configuration.resetInputProfile.assertQualificationNs++;
  await assert.rejects(decodePackage(bad),/SHA-256 mismatch/);
});

test('invalid profiles and unsupported clock/debug configurations fail before guest execution',async()=>{
  for(const profile of [{},[],{...resetInputProfile,extra:1},
    {...resetInputProfile,assertThresholdPpm:199999},{...resetInputProfile,releaseThresholdPpm:900001},
    {...resetInputProfile,releaseThresholdPpm:400000},{...resetInputProfile,assertPropagationNs:-1},
    {...resetInputProfile,releaseQualificationNs:1.5},{...resetInputProfile,assertQualificationNs:0x100000000}]){
    assert.throws(()=>normalizeResetInputProfile(profile),/resetInputProfile/);
    assert.throws(()=>core({resetInputProfile:profile}),/resetInputProfile/);
  }
  assert.throws(()=>core({osccalHz:null}),/physical/);
  assert.throws(()=>core({fuseHigh:0xf7}),/DWEN/);
  assert.equal(core({resetInputProfile:null}).state().resetInputEnabled,undefined);
});

test('reserved physical input timestamps are rejected without faulting an otherwise valid receiver',()=>{
  const c=core();
  assert.throws(()=>analog(c,0xffffffffffffffffn,0),/Invalid analog input timestamp/);
  assert.throws(()=>c.injectPinsPs({at:0xffffffffffffffffn,mask:32,levels:0}),/Invalid pin input timestamp/);
  assert.equal(c.state().deviceFault,0);assert.equal(c.state().resetCount,0);
});
