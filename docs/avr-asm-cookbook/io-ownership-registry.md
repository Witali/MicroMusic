# Single-source I/O ownership without a runtime table

Applies to the ATtiny13A physical native board, Clang 24 / Binaryen 133 and the
existing two-page WASM ABI. This is a structural simplification, not a speedup.
ATtiny88 keeps its separate profile and music-runtime register map.

`web-player/native/devices/attiny13a/io_registers.inc` records one project storage/
bus owner for each of the 35 distinct official byte addresses. Vendor aliases
ADC/ADCW/ADCL and EEAR/EEARL share that owner. Cross-controller consumers still
exist: MCUCR has sleep and interrupt users, for example. The catalog does not
replace their behavioral side effects or dependency ordering.

The catalog is a project adaptation, separate from unmodified Microchip
ATtiny_DFP 3.4.278. All addresses/masks come from its generated `AT13_*` names;
there is no duplicated numeric address table.

```c
AT13_IO_PUBLISH(TIMER0, TCCR0A, board.timer.tccra)
AT13_IO_PUBLISH(TIMER0, TCCR0B, board.timer.tccrb)
AT13_IO_LOCAL(CPU, SREG)
```

One C macro expansion emits the existing 31 public register stores in their
original order. Four local bytes (SPL, SREG, OSCCAL and DWDR) retain their existing
separate handling. A small build-time generator selects TIMER0-owned entries
and emits its direct eight-register bus predicate. PRR remains board-owned
because its write changes clock domains as well as Timer0 state.

Avoid adding a runtime descriptor array, loop or indirect dispatch just to share
this metadata. The generated predicate is a plain expression with the original
comparison order. In this build, a first constant-owner OR-chain experiment
emitted 119,026 bytes; the direct generated predicate and publication expansion
restore **identical 118,969-byte native WASM**, SHA-256
`9f1eefa094f9003419251408953309e3b3c4050fc217234b9b95ed0275d87778`.
Equivalent C source alone did not establish byte equality.

The build checks generated bindings and pins their input/output plus generated
manufacturer maps in its provenance. Tests cover all 64 I/O slots against the
official map and independent ownership expectations, all eight Timer0 routes,
reserved/local exclusions, and every byte written by the real publisher versus
the pinned original publisher for 256 arbitrary controller-state samples.
Existing bus-side effects and exact phase/IRQ/pin/PCM tests remain applicable.

No native state, memory, ABI, CPU lowering, clocks, publication boundary or engine
default changes. No handwritten assembly is introduced; C/WASM and JS remain
selectable. This gives no new real-time audio or hardware-support claim.

Source: [Microchip ATtiny13A DS40002307A §20](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
the [pinned manufacturer definitions](../../web-player/vendor/microchip/ATtiny_DFP/3.4.278/README.md),
and the [device bindings](../../web-player/native/devices/attiny13a/io_registers.inc).
