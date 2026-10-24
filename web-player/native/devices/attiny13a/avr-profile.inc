/* Fixed physical-board geometry and the common executor's register ABI.
 * Addresses/masks come from the pinned Microchip-generated definitions.
 * This also initializes direct native callers that have no JavaScript bridge. */
static void full_profile(void) {
 for(int i=0;i<C_COUNT;i++)config[i]=0;
 C(flashBytes)=AT13_MEMORY_FLASHEND+1;C(eepromBytes)=AT13_MEMORY_E2END+1;
 C(sramStart)=AT13_MEMORY_RAMSTART;C(ramEnd)=AT13_MEMORY_RAMEND;
 C(cpuHz)=9600000;C(pointerMask)=255;
 C(sreg)=AT13_DATA_SREG;C(spl)=AT13_DATA_SPL;C(sph)=-1;
 C(eecr)=AT13_DATA_EECR;C(eedr)=AT13_DATA_EEDR;C(eear)=AT13_DATA_EEARL;
 C(clkpr)=AT13_DATA_CLKPR;C(gtccr)=AT13_DATA_GTCCR;C(prr)=AT13_DATA_PRR;
 C(spmcsr)=AT13_DATA_SPMCSR;C(wdt)=AT13_DATA_WDTCR;C(mcusr)=AT13_DATA_MCUSR;
 C(adc)=AT13_DATA_ADCSRA;C(acsr)=AT13_DATA_ACSR;
 C(ext0)=AT13_DATA_GIMSK;C(extMask0)=AT13_MASK_INT0|AT13_MASK_PCIE;C(ext1)=-1;
 C(a)=AT13_DATA_TCCR0A;C(b)=AT13_DATA_TCCR0B;C(c)=-1;
 C(counter)=AT13_DATA_TCNT0;C(counterHigh)=-1;
 C(ocra)=AT13_DATA_OCR0A;C(ocrb)=AT13_DATA_OCR0B;
 C(ocraHigh)=C(ocrbHigh)=C(icr)=C(icrHigh)=-1;
 C(timsk)=AT13_DATA_TIMSK0;C(tifr)=AT13_DATA_TIFR0;
 C(vector)=3;C(fastMode)=3;C(normalTop)=255;
 C(prrMask)=AT13_MASK_PRTIM0;C(overflowMask)=AT13_MASK_TOV0;
 C(flagMask)=AT13_MASK_TOV0|AT13_MASK_OCF0A|AT13_MASK_OCF0B;
 C(interruptRejectMask)=AT13_MASK_OCIE0A|AT13_MASK_OCIE0B;
 C(interruptStoreMask)=AT13_MASK_TOIE0|AT13_MASK_OCIE0A|AT13_MASK_OCIE0B;
 C(modeAMask)=AT13_MASK_WGM00|AT13_MASK_WGM01;
 C(modeBMask)=AT13_MASK_WGM02;C(modeBShift)=1;
 C(controlBMask)=AT13_MASK_WGM02|AT13_MASK_CS00|AT13_MASK_CS01|AT13_MASK_CS02;
 C(forceBMask)=AT13_MASK_FOC0A|AT13_MASK_FOC0B;
}
