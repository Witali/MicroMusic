import {AT13_FUSE_MASK as FUSE} from '../attiny13a-registers.js';
// DS40002307A figure6-1/6.2.3: CKSEL11 uses the same oscillator as WDT.
// Keep arbitrary independent rates available to the legacy digital fixture.
export function validateLowPowerClockOptions({osccalHz=null,fuseLow=0x7a,oscillatorHz=9600000,watchdogHz=128000}){
  const cksel=FUSE.LOW_CKSEL0|FUSE.LOW_CKSEL1;
  if(osccalHz!==null&&Number.isInteger(fuseLow)&&(fuseLow&cksel)===cksel&&oscillatorHz!==watchdogHz)
    throw Error('CKSEL11 shares the watchdog oscillator: oscillatorHz must equal watchdogHz in physical mode');
}
