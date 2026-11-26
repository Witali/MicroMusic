# LG1 full decoder: grouping overhead and helper input scale

Measured on 2026-11-26 with ATtiny88 (AVR25, no MUL) and ATmega328P (AVR5),
AVR-GCC 7.3.0 / GNU++11 / GNU ABI and simavr 1.6. This is an original repository
experiment using existing LPX math helpers, not a new assembly implementation.
The complete method, per-file results, input hashes and commands are in the
[experiment report](../../Codecs/LPX/research/lbg1-2026-11-26/README.md).

## Match a helper's excitation scale at the call boundary

The existing `lpx4SynthesisCircularQ12` AVR5 helper expects **Q4 excitation**.
The scalar and AVR25 specialization used by LG1 takes an unscaled integer
excitation. Passing the same numeric value into both gives different output
even when the coefficients and history are identical.

LG1 explicitly multiplies excitation by 16 before entering the circular AVR5
helper. Coefficients remain Q12 and are bounded to −32767..32767. Keep this
adaptation at the arithmetic boundary, independently of Flash/RAM access.
See [decoder.cpp](../../Codecs/LPX/experimental/LBG1/decoder.cpp).

Always retain portable C selection on AVR itself. Here `LPX4_ENABLE_ASM=0`
selects C while `__AVR__` still selects PROGMEM reads. An additional
`LPX4_ARCH=0` control with ASM enable set proves generic arithmetic selection
does not replace real device/memory macros. Both paths are checked against the
same independent output. No architecture macro is fabricated to avoid a device
limit.

## Moving coefficient conversion offline does not guarantee a faster player

LG1 removes LSF-to-LPC conversion from the MCU by storing ready Q12 anchors,
but adds group parsing and trajectory state. The current LPX ROM player also
has private fast paths that the new public-API adapter does not use. Whole
implementation measurements are therefore required before attributing a gain.

At 16 MHz / 8 kHz with the original FIFO32/prefill24, fixed gain and interrupts
active, compact LG1 versus current LPX measured:

| Complete-file workload / ASM backend | LPX decode cycles/sample | LG1 decode cycles/sample | Change |
| --- | ---: | ---: | ---: |
| Tiny: seven matching files that fit both images | 1366.6 | 1549.1 | +13.4% |
| Mega: all eight matching files | 626.7 | 742.2 | +18.4% |

Every fitting ASM playback has zero underruns and exact PWM. The eighth Tiny
file exceeds physical Flash with LG1, so it is a fit failure and has no invented
full-file timing. C fallback improves average decode cost slightly (Tiny −2.8%,
Mega −4.8% on eight files), but Tiny C still requires over twice the available
CPU. Do not claim Tiny real-time C support from arithmetic correctness alone.

Program Flash excluding audio grows from about 3579 to 5025 bytes on Tiny and
3026 to 4274 on Mega. Static SRAM plus observed stack grows from 445 to 462
bytes on Tiny and 441 to 462 on Mega. These are measured whole-player costs
for the recorded compiler/profile/workload, not portable bounds.

The useful technique here is the validation method: freeze actual stream and
decoder bytes, include frame-boundary peaks and IRQ preemption, verify queued
PWM even when a slow backend underruns, and treat Flash overflow as a hardware
failure rather than enlarging the simulator's target memory.
