# Shorten a refill burst without changing fixed-point synthesis

Target: classic AVR5 / ATmega328P, 16 MHz, GNU AVR ABI, AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, existing O2/O3 stage attributes.
Original project scheduling/register work; the underlying Xiph Speex 1.2.1
algorithm and BSD provenance remain in the codec/vendor files.

Average speed is insufficient for a small audio ring. A full-frame producer
can meet its average budget while a long gap before its first callback drains
the ring. In this decoder, the IIR consumes excitation delayed by forty samples.
Generate only the next forty excitation samples immediately before each
synthesis quarter; preserve that delay and every arithmetic operation/state
transition. Do not increase the ring to conceal a sustained timing failure.

Prove the storage schedule first. After the frame history move, NB1 does not
read adaptive history. The class cache occupies bytes 0..159 and five raw words
160..169. Reuse bytes 170..197 for fourteen frame-constant/state words. Old
delayed input starts at 210; the next history move reads from 320. Static geometry
assertions plus a real decoder observer check all four partial states, generated
class prefixes, seed progression, twelve guard bytes and delayed history.
No persistent allocation is added. This is specific to that NB1 lifetime;
do not reuse live pitch history in other modes.

A straight C controller split was **rejected**: exact PCM on 384 frames, but
230344.068 cycles/frame versus 227325.068 for the old controller. Additional
call/state handling must earn its cost. The accepted AVR kernel keeps pulse,
noise, mean and constants in registers for forty samples. Its phase countdown
is equivalent to the original absolute-position comparison, including when
the previous phase exceeds a newly selected pitch.

Share subtle arithmetic through a GNU assembler macro rather than copying it.
Here the exact scalar mean already uses one signed product and overflow
correction. Parameterize its mean/product register pairs and keep r20 free for
the vector counter. Product bits 0..7 can be discarded because all cross terms
and the 0x4000 rounding bias start at bit 8. This also removes one scalar move,
changing 43..48 to 42..47 cycles without changing results. Preserve all
callee-saved registers and clear r1; never mask interrupts in the kernel.

The explicitly callable C vector uses the original two-product mean and stays
selectable on AVR too. Select ASM only through supported architecture macros
**and** the separate explicit enable flag. Hardware memory access remains
independent. Portable C decoder/export checks are compile/link only; isolated
C scalar/vector arithmetic executes against ASM and independent BigInt models.

Measured against `ab597728`: 31540 vector cases, all 18432 valid pitch/phase pairs,
a full signed-word table sweep, ABI/read-only/bounds checks, and 1212335 scalar
mean pairs pass. Complete NB2.15/WB3.95 PCM/reset and full WB IRQ/SPI output
checks are recorded in the linked admission. Natural WB3.95 speech improves
225973.224 -> 222942.788 cycles/frame, 70.62% -> 69.67% decoder CPU. Bare firmware
grows 286 B; static SRAM and observed peak stack remain unchanged.

On a matched 384-frame, three-stream +8%-load IRQ sample, maximum frame-boundary
publication gaps fall 117458 -> 94865 cycles (~19.2%). Observe the actual ring
head publication after all eighty output bytes are written, rather than the
entry to the output callback. Timer-paced intra-frame gaps remain about 80013
cycles. These are ISA-simulator measurements, not board/analog measurements.

[Kernel](../../Codecs/Speex/AVR/src/nb1_vocoder.S),
[explicit C](../../Codecs/Speex/AVR/src/nb1_vocoder.c),
[shared mean](../../Codecs/Speex/AVR/src/lowrate_mean_kernel.inc),
[independent partial-state observer](../../Codecs/Speex/AVR/tests/verify_nb1_streaming.mjs),
[full evidence and reproduction](../../Codecs/Speex/AVR/WB_QUARTER_REFILL.md).
