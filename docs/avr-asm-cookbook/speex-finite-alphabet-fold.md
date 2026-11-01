# Transform a finite alphabet before expanding it

For a deterministic pointwise transform with a block-constant parameter,
precompute its result for every possible input symbol. Expand by lookup
afterward. This works for nonlinear integer quantizers too: preserve each
original floor, bias, narrowing and modulo operation inside the transform.

Speex NB1 has five noise words per frame and forty classes per subframe.
HB1 gain varies by subframe. Compute five exact two-stage folds per subframe
instead of forty, then negate only odd output positions. Applying parity to
table indices or merging the two gains would change the output.

[Common C controller and explicit C fallback](../../Codecs/Speex/AVR/src/wb_fold.c),
[shared AVR array template](../../Codecs/Speex/AVR/src/wb_fold.S).
Target classic AVR5 / ATmega328P, hardware MUL, GNU ABI, AVR GCC 7.3.0.
Architecture plus separate ASM enable selects the backend; memory access
remains independent. The five-word path reuses the existing arithmetic macros
with zero r2 as its parity source. Default/unsupported targets use C.

Reuse dead interpolation scratch only after LSP conversion, keeping the live
denominator in a distinct object. Static SRAM stays unchanged; the observed
peak stack grows one byte. Assert capacity and test adjacent caller words.

The five-argument GNU AVR interface uses call-saved r14:15 and r16:17 as
incoming argument registers. Random ABI tests must retain valid argument
values while checking their preservation; randomize other saved registers.
The direct two-argument ASM leaf tests all saved registers with arbitrary
patterns. Blindly replacing incoming pointer/gain registers invalidates a test.

Measured with Os/O2/O3, LTO/mcall-prologues/mrelax, avr8js 0.21.1: 88960
five-path cases, complete signed 16 sweeps at every table position, all 32
caller scales and 183 structured gains match independent arithmetic. Cache,
output and scratch guards pass; real mixed-frame observation also checks
the delayed history and forty-byte dead-prefix guard.

Folding products fall 1760 -> 220/frame (one class-address MUL/subframe remains).
Natural WB 3.95 speech time falls 4.53%, CPU 73.97% -> 70.62%, with 272 B Flash and
+1 B peak stack. Full 10627-frame raw and +8% IRQ corpora plus 3600 SPI frames
retain exact PCM/PWM with zero underruns. The +11% coverage stress fails 8083
underruns and is explicitly unadmitted. A lower mean does not establish burst
latency; record failed timing gates too. No physical-board claim is made.

Original project work; preserve existing Xiph algorithm/table BSD notices.
[Bounds, complete evidence and reproduction](../../Codecs/Speex/AVR/WB_NOISE_FOLD.md).

The forty-sample producer is now implemented separately in
[quarter refills](speex-quarter-refills.md). Its +11% gate passes; the failure
above remains evidence for the earlier folding stage.

## Hoist a frame-constant quantizer; skip an exact zero class

After quarter refills, cache `floor(29491 * raw / 32768)` once per frame.
The next rounded scale still runs per subframe; do not merge the two gains.
The middle noise class is exactly zero, and `(0*g+256)>>9` is zero for every
gain. Store it directly and retain five table slots. A four-slot compression
experiment was slower and used more stack because it reordered the table.

The new eight-bit loop-counter check skips zero products inside the shared
GNU assembler array template; default forty-word behavior is unchanged. Keep
the explicitly selectable C implementation with the same zero-class contract.
The raw words remain live for vocoder state. Ten cached Q15 bytes reuse dead
history 198..207, extending the existing workspace to 208 before delayed input
210 and next-move source 320. Recheck the remaining two guard bytes, every
partial state/seed and readonly fold workspace rather than relying on the old
forty-byte guard measurement.

Measured against `56ffaa45`, same MCU/ABI/toolchain/options: 88960 seven-path
cases with complete signed-word sweeps in all four variable slots, fixed zero
slot, 32 scales, 183 gains and four subframes pass. The original general
five-word leaves remain regression references; the new scale leaf also gets
independent C/ASM/BigInt and arbitrary callee-register tests. Real preparation
adds 16 MULs, four fold calls each remove 27: **92 fewer MULs/frame** overall.

Complete 10627-frame WB3.95 PCM/reset checks save exactly 343 cycles/frame and
4 B Flash, with unchanged static SRAM and peak stack. Natural speech CPU falls
69.6696% -> 69.5624%. Separate full loaded IRQ/SPI checks cover timing; these
are ISA-simulator measurements, not physical-board or analog measurements.
The earlier preparation extends the maximum frame-boundary gap by 113 cycles
(7.06 microseconds); full +8%/+11% gates keep the same queue minima and zero
underruns. Average savings do not imply that every individual burst shrinks.
[Full evidence, rejected compression and reproduction](../../Codecs/Speex/AVR/WB_NOISE_PREFOLD.md).

Unimplemented related idea: specialize forced prediction via
`((int32_t)x*((int16_t)coefficient<<7)+4096)>>13`, which equals
`((int32_t)x*coefficient+32)>>6` for 0..63 coefficients.
The latter product fits signed 22 bits (three AVR bytes), permitting a 16 x 8
kernel with a C fallback. These need separate proofs and measurements.
