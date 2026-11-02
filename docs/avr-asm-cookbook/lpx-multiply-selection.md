# LPX: select arithmetic from the real target capabilities

Applicable target: classic AVR5/ATmega328P with hardware multiplication,
GNU AVR ABI and AVR GCC 7.3.0. LPX's handwritten arithmetic remains explicitly
enabled with `LPX4_ENABLE_ASM=1`; `0` selects the equivalent C implementation
on the same AVR. The default is C. Unsupported targets also select C when
assembly was requested. Flash reads remain governed by the real AVR platform
definitions, independently of the arithmetic selection.

Use `-mmcu=atmega328p`, `-mmcu=attiny88` or the actual device name. Do not
simulate a missing/present multiplier by redefining `__AVR__`,
`__AVR_ARCH__` or `__AVR_HAVE_MUL__`. GCC supplies these capabilities from
the selected device; see the [GCC 7.3 AVR options and built-in
macros](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/AVR-Options.html).

The existing [LPX arithmetic header](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4Math.h)
already requires the AVR5 architecture, hardware multiplier, supported GNU
compiler and separate enable flag. No new multiplication algorithm was needed.
The C expression uses hardware `MUL` on ATmega328P; on ATtiny88/ATtiny13A
the compiler links its software multiplication helper. A compiler library
symbol on ATmega328P does not by itself imply software bit-by-bit multiplication:
inspect the linked instructions.

## Assembled verification, not an audio throughput claim

The [target check](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr_mul_targets.py)
compiles and links a volatile signed 16-by-16 multiply with `-Os`, checks
preprocessor selection, and disassembles the actual ELF. Results on
2026-11-02 with AVR GCC 7.3.0:

| Device | ASM requested | Selected LPX backend | Linked `MUL` instructions |
|---|---:|---|---:|
| ATmega328P | 0 | C | 4 |
| ATmega328P | 1 | AVR5 assembly | 4 |
| ATtiny88 | 0 | C | 0 |
| ATtiny88 | 1 | AVR25 software assembly | 0 |
| ATtiny13A | 1 | AVR25 software assembly | 0 |

The C no-MUL image contains the compiler's software multiply helpers; the
explicit AVR25 ASM images use the project software product and link no multiply
runtime helper. These rows were refreshed after integrating the AVR25 backend.
The selected headers remained unchanged during the check. Real CPU/ISA macros
are preserved; Tiny88 uses the pinned Microchip ATtiny_DFP 3.4.278 include path.
An assembled arithmetic probe does not imply that the complete LPX decoder
fits ATtiny13A's Flash or SRAM. Reproduce with Python:

```text
Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr_mul_targets.py --avr-bin AVR_BIN --output build/multiply-check
```

Use a fresh output directory. Detailed ELF, disassembly and fingerprints stay
in ignored `build/`. This check proves target selection and ISA use only;
sample equivalence, full Flash and real-time support require the complete
player with active timers and interrupts.
