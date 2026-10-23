import {AT13_DATA,AT13_MEMORY,AT13_CONST,AT13_MASK} from '../attiny13a-registers.js';

// Device geometry and register placement, derived from the pinned Microchip DFP.
// Peripheral behavior lives in the native ATtiny13A runtime, not in the emitter.
export const ATtiny13AProfile=Object.freeze({
  name:'ATtiny13A',flashBytes:AT13_MEMORY.FLASHEND+1,
  flashWords:(AT13_MEMORY.FLASHEND+1)/2,pcMask:(AT13_MEMORY.FLASHEND+1)/2-1,
  ioStart:AT13_CONST.IO_DATA_OFFSET,ioEnd:AT13_MEMORY.RAMSTART,
  ramStart:AT13_MEMORY.RAMSTART,ramEnd:AT13_MEMORY.RAMEND,
  sreg:AT13_DATA.SREG,stackPointer:AT13_DATA.SPL,
  dataAddressBits:8,programCounterBytes:2,
  legacy:Object.freeze({sleepControl:AT13_DATA.MCUCR,sleepEnableMask:AT13_MASK.SE,
    irqFlags:AT13_DATA.TIFR0,irqFlagMask:AT13_MASK.TOV0,
    watchdogControl:AT13_DATA.WDTCR,watchdogRunMask:AT13_MASK.WDE|AT13_MASK.WDTIE}),
});
