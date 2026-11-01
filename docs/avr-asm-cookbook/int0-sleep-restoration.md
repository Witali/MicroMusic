# ATtiny13A: keep sleep-restoration events separate from sampled pin history

Microchip [DS40002307A section10.2.5](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=60)
specifies an external interrupt flag after deep sleep when a high, masked
edge-sense input was clamped. All three edge senses are covered, including
falling-edge detection. Section9.3.3 separately requires INTF0 to stay clear
in low-level sense. Use the existing manufacturer-derived register masks.

This applies to the full ATtiny13A C/WASM board, including resumable AVR
firmware, and is a correctness technique rather than an assembly optimization
or measured speed improvement. The source builds with the pinned Clang24
freestanding wasm32 C11 toolchain. CPU, peripheral and generated-code ownership
remain separate; there is no additional ISA requirement or firmware ABI.

The normal synchronizer retains PINB and INT0 history while clkI/O stops.
If that history is high both before and after sleep, comparing it with the
restored high input misses the documented flag. Do not fabricate a physical
pin transition or rewrite PINB just to produce the flag. Instead:

```text
on release of a Power-down clamp:
    if INT0 is masked, its enabled buffer is high, and edge sense is selected:
        retain an explicit restoration event
on the next actual rising clkI/O edge:
    consume the event once
    set INTF0 only if edge sense still applies
```

The first resumed rising edge is this digital fixture's publication policy.
The datasheet establishes the flag after resumption, without specifying its
internal sub-cycle phase. It does not establish the precise ADC auto-trigger
phase relative to the clamp release. That hardware qualification remains open.
Held clocks cannot consume the event. Ordinary GPIO changes still use the
existing synchronization path.

Include the event in the settled-state predicate so stable-span skipping
cannot bypass it. Reset clears it. GIFR W1C before publication clears no future
event; after publication it clears the latched flag normally. Low levels,
DIDR-disabled inputs, interrupt-enabled buffers, Idle and ADC Noise Reduction
must not create a clamp-restoration event. GIMSK and SREG still govern CPU
interrupt admission independently of GIFR.

The [evidence](../../web-player/reports/int0-resume-20261101.md) covers GPIO-driven
and external inputs, held clocks, reset, W1C, stable spans and firmware reading
GIFR in the first instruction after SLEEP. The same 18 firmware tests pass
4/18 with the previous native module and 18/18 with the correction. Exports,
memory and the resumable ABI are unchanged; the module grows by 51 bytes.
No official simulator, silicon timing or real-time audio result is inferred.
