import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// Explicit synthetic board fixture; typical threshold values are selected here,
// never installed as universal chip defaults by the production runtime.
const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
  bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
  bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
const osccalHz=Array(128).fill(0);osccalHz[0]=10000000;
const options={oscillatorHz:10000000,osccalHz,powerResetProfile,fuseLow:0x72,fuseHigh:0xff,
  nvmClockProfile:1,nvmCalibrationReferenceHz:10000000};
const loop=sequential([avr.rjmp(0,0)]);
const core=extra=>new ATtiny13A(loop,null,{...options,...extra});

test('generated multicycle instruction cannot commit a later SRAM write after a supply reset',()=>{
  const c=new ATtiny13A(sequential([avr.ldi(16,0x5a),avr.sts(0x60,16)]),null,options);
  c.step();const drop=c.state().timePs+37n;c.setVccPs({at:drop,microvolts:0});c.step();
  assert.equal(c.state().timePs,drop);assert.equal(c.pc,0);assert.equal(c.data[0x60],0);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);assert.equal(c.readIO(IO.MCUSR),1);
  c.setVccPs({at:1000000n,microvolts:5000000});c.runUntilPs(1000000n);
  assert.equal(c.state().resetHeld,false);assert.equal(c.state().vccMicrovolts,5000000);assert.equal(c.state().deviceFault,0);
});

test('BOD filter/reset cause runs through generated CPU barriers at the exact physical timestamp',()=>{
  const c=core({fuseHigh:0xfb});c.setVccPs({at:1000000n,microvolts:2600000});
  c.runUntilPs(3000000n);assert.equal(c.state().timePs,3000000n);
  assert.equal(c.state().resetHeld,true);assert.equal(c.state().resetCount,1);assert.equal(c.readIO(IO.MCUSR),5);
  c.setVccPs({at:4000000n,microvolts:5000000});c.runUntilPs(4000000n);assert.equal(c.state().resetHeld,false);
});

test('native physical capture integrates an asynchronous supply reset within one audio sample',()=>{
  const c=core();c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);
  c.setVccPs({at:31250000n,microvolts:0});
  assert.deepEqual(c.capturePhysical(3,8000),Float32Array.of(-.5,-1,-1));
  assert.equal(c.state().resetCount,1);assert.equal(c.state().vccMicrovolts,0);assert.equal(c.state().deviceFault,0);
});

test('cold-supply package preserves its explicit power profile and release-only startup',async()=>{
  const configuration={...options,vccMicrovolts:0,fuseStartupProfile:1};
  const runtime=new Uint8Array(await readFile(new URL('../wasm/attiny13a.wasm',import.meta.url)));
  const abi=runtimeABI(new WebAssembly.Instance(runtimeModule).exports);
  const pkg=await createPackage({flash:loop,configuration,runtime,translated:transpileAVR(loop,abi).bytes});
  assert.equal(pkg.version,3);const c=await ATtiny13A.fromPackage(pkg);
  assert.equal(c.state().powerResetEnabled,true);assert.equal(c.state().resetHeld,true);assert.equal(c.state().vccMicrovolts,0);
  c.setVccPs({at:1000000n,microvolts:5000000});c.runUntilPs(1000000n);
  assert.equal(c.state().startupDeadlinePs,3000000n);assert.equal(c.state().starting,true);
  c.runUntilPs(3000000n);assert.equal(c.state().halted,false);assert.equal(c.state().resetCount,0);
});

test('EEPROM voltage uncertainty reaches the JS diagnostic without completing unknown bytes',()=>{
  const c=core();c.writeIO(IO.EEARL,4);c.writeIO(IO.EEDR,42);c.writeIO(IO.EECR,4);c.writeIO(IO.EECR,2);
  c.setVccPs({at:c.state().timePs+1n,microvolts:1800000});
  assert.throws(()=>c.runUntilPs(1000000n),/peripheral fault 5, detail 128/);
  assert.equal(c.eeprom[4],255);assert.equal(c.state().deviceFault,5);
});

test('supply injection is explicit and rejects invalid inputs before mutating a valid device',()=>{
  const c=core({powerResetProfile:null});assert.throws(()=>c.setVccPs({at:0n,microvolts:0}),/powerResetProfile/);
  const d=core();for(const microvolts of [-1,1.5,0x80000000])assert.throws(()=>d.setVccPs({at:0n,microvolts}),/Invalid supply input/);
  assert.throws(()=>d.setVccPs({at:0xffffffffffffffffn,microvolts:0}),/Invalid supply input/);
  assert.equal(d.state().deviceFault,0);assert.equal(d.state().vccMicrovolts,5000000);
});
