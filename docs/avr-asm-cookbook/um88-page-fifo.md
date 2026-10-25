# UM88: page-local FIFO addressing

This original MicroMusic technique applies to ATtiny88 / AVR25 and AVR-GCC
7.3.0 with `-Os -fno-jump-tables -ffunction-sections -fdata-sections` and
`-Wl,--gc-sections`. It reduces Flash and IRQ work without changing the
portable musical-engine interface, score formats, or PWM values.

## Address and ABI contract

Declare the PWM byte ring with `aligned(256)`. Legal capacities remain
8..192 bytes in multiples of four; stereo needs more than eight bytes.
Every valid cursor therefore lies in one SRAM page. The IRQ can load
`hi8(um_ring)` into XH, use the cursor directly as XL, and retain the
post-incremented XL as the next cursor. This removes the former base addition
and subtraction. The address remains symbolic; no SRAM page number is fixed
in the assembly.

The measured layouts already placed the ring at SRAM `0x200`, so stronger
alignment consumed no additional SRAM. The builder's FIFO/stack bounds check
must remain: future static-state growth can make the alignment padding matter.

The ISR preserves r16, X, and SREG, and does not assume r1 is zero when
interrupted. It still restores an interrupted nonzero r1 unchanged. The
compiler-generated C ISR remains the equivalent fallback when explicit
`UM_ENABLE_AVR_ASM` selection is disabled. Register definitions continue to
come from the retained Microchip DFP.

The stereo output helper also receives literal stride `2`; UM88 accepts only
one or two channels. This gives the compiler a constant without changing the
four interpolation points or the mono fast path. Hardware initialization is
unchanged, including the Micronucleus `.init3` watchdog/PRR cleanup and
COM-before-DDR ordering.

## Isolated measurements

These results isolate the platform/IRQ patch against `41e456a9`. Final combined
core sizes, including other optimizations, are recorded separately.

| Profile | Engine before | Engine after | Change |
| --- | ---: | ---: | ---: |
| ASM, 8 MHz, 192-byte ring, compact dictionary | 2930 B | 2922 B | -8 B |
| ASM, 16 MHz, 192-byte ring, compact dictionary | 2982 B | 2974 B | -8 B |

At 16 MHz the aligned song boundary moved from 3008 to 2976, reducing the
Children image from 5851 to 5819 bytes. The active ASM mono IRQ decreased from
52 to 49 cycles. Complete short audits passed for dense eight-voice playback
and the polyphony-study restart with both 128-byte/fast and
192-byte/compact dictionaries, plus C four-voice playback with a 128-byte/fast
dictionary. All checked
musical states and PWM bytes remained exact, with zero underruns.

One-second stereo runs on both boards also passed: minimum queued audio was
26 frames and minimum stack margin was 22 bytes. The 16-MHz startup check
used inherited watchdog, stack, and peripheral state. These are instruction
model measurements; physical hardware was not tested.

Implementation: [platform.c](../../ATtiny88/Music/universal/platform.c) and
[irq-avr.S](../../ATtiny88/Music/universal/irq-avr.S). The broader power and
interpolation constraints are in [the platform recipe](um88-platform.md).
