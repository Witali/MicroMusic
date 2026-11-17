# Compact universal LPX player work

Task baseline: `ead0bdcb0b627532afbf2d7b52fce7f015cf6dbc`.
The target is at most 3072 program bytes for the single-stream Nano player,
excluding audio. Also reduce the shared ATtiny88 firmware, preserve exact
8 kHz PWM and compressed payloads, and retain explicitly selectable C
arithmetic. Additional dialogue infrastructure is outside the 3072-byte cap.

`steps.json` orders focused source transitions. Each retained measurement
pairs 22 actual interrupt-active playbacks per CPU with its predecessor.
The cases include public speech, P4/P6/sparse80, changing/clustering impulses,
pitch and filter extremes, short tails, and all coordinate pairs.
Media and generated ELF/HEX/log files remain in ignored `build/`.

The successful foreground producer includes decoding, dynamic output gain
and queue publication. CPU cycles exclude IRQ execution; add the complete
IRQ cost when comparing the total budget. The host observer reads actual
ELF-resolved IN/OUT or LDS/STS accesses, without target instrumentation.
The observer extension was checked by replaying the same 44 baseline ELFs:
all preceding timing fields and output bytes remained identical.

Measurements use AVR-GCC 7.3.0 and simavr 1.6 at 16 MHz, SRAM512 profile,
FIFO32 / prefill24, ASM arithmetic/ISR, and the compiler options recorded
in local build receipts. They do not imply a physical-board measurement.
Historical WebUI receipts keep their original source and binary identities;
these paired workload receipts do not claim that new binaries equal old HEXes.

- `gain`: exact gain arithmetic saves 26 B on Nano and 6 B on Tiny.
  See the [technique and bounds](../../../../docs/avr-asm-cookbook/lpx-rom-gain.md).
