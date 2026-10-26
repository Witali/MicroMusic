import {AT88_DATA as R,AT88_BITS as B,AT88_MEMORY as M} from '../attiny88-registers.js';

// CPU lowering only; Timer1/audio and peripheral limits are the shared music
// runtime's existing ATtiny88 model, not the full physical ATtiny13A board.
export const ATtiny88Profile=Object.freeze({
  name:'ATtiny88',target:'attiny88',flashBytes:M.flashBytes,
  flashWords:M.flashBytes/2,pcMask:M.flashBytes/2-1,
  ioStart:M.ioOffset,ioEnd:M.ramStart,ramStart:M.ramStart,ramEnd:M.ramEnd,
  sreg:R.SREG,stackPointer:R.SPL,stackPointerHigh:R.SPH,stackPointerHighMask:M.spHighMask,
  dataAddressBits:16,programCounterBytes:2,
  legacy:Object.freeze({sleepControl:R.SMCR,sleepEnableMask:1<<B.SE,
    irqFlags:R.TIFR1,irqFlagMask:1<<B.TOV1,
    watchdogControl:R.WDTCSR,watchdogRunMask:(1<<B.WDE)|(1<<B.WDIE)}),
});
