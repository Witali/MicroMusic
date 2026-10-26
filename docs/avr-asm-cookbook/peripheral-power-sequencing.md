# ADC power sequencing and W1C flags

Target: ATtiny13A, ordinary AVR C/AVR-GCC register accesses, no ISA extensions
or assembly backend. This concerns correct power gating, not a measured speed
or memory optimization. Registers come from the original Microchip header.

DS40002307A7.5.3 requires ADEN=0 before PRR.PRADC=1. A live conversion cannot
be treated as resumably paused by this operation: the sequence violates the
published precondition. The full board now diagnoses that request before
changing PRR or ADC/Timer0 state. This is an emulator diagnostic, not a claimed
silicon exception. PRTIM0 alone can still stop Timer0 while ADC conversion runs.

Illustrative C sequence (not assembled as a standalone firmware example):

```c
/* Precondition: PRADC=0; caller owns ADC configuration. ADIF is W1C. */
ADCSRA = ADCSRA & (uint8_t)~(_BV(ADEN) | _BV(ADIF));
PRR |= _BV(PRADC);
/* ADC register access is unavailable until PRADC is cleared. */
PRR &= (uint8_t)~_BV(PRADC);
ADCSRA = (ADCSRA & (uint8_t)~_BV(ADIF)) | _BV(ADEN);
/* Start the next conversion explicitly when needed. */
```

Writing zero to ADIF in these read/modify/write values preserves its pending
state. A plain `ADCSRA &= ~_BV(ADEN)` would write back a sampled ADIF=1 and
acknowledge it accidentally. Handle or mask a pending ADC interrupt and exclude
concurrent ISR changes to ADC/PRR configuration while performing this sequence.

Regression evidence: standalone native tests cover enabled-idle, waiting,
converting and completed ADC states, whole-byte/masked PRR transactions, both
PRR bits, retained ADIF/ADIE/ADATE/prescaler controls, legal restart and unrelated
Timer0 gating. Actual generated AVR programs stop at the bad OUT under compatible,
physical/resumable and externally clocked CLKI execution; subsequent instruction
effects do not occur. No measured silicon or real-time audio claim is made.

Source-reading caution from this audit: PDF text extraction loses the inverted
RSTDISBL label in Table10-4. Its DIEOV ADC0D row also disagrees with the generic
enable-value description and the DIDR0 guarantee in13.2.3/14.12.5. Keep the
current explicit DIDR0 disabled-input/PINB=0 contract; this audit does not
silently reinterpret input polarity from that table or resolve it on hardware.

Sources: [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
sections7.5.3,10.2.5,10.3,13.2.3,14.12.2/14.12.5;
[pinned manufacturer originals and provenance](../../web-player/vendor/microchip/ATtiny_DFP/3.4.278/README.md);
[full-board regression](../../web-player/tests/device-adc-power-sequence.test.mjs).
