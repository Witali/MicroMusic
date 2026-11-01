# Specialize a sparse FIR without changing its quantizer

Target: ATmega328P / classic AVR5 with hardware MUL, GNU ABI, AVR GCC 7.3.0,
existing mixed Os/O2/O3 with LTO, mcall-prologues and mrelax. Original project
control/register adaptation; existing Speex algorithm and tables retain their
Xiph 1.2.1 BSD provenance.

NB submode 8 uses three coefficients `{0, c, 0}`, with c in 0..63. A generic
three-tap kernel still performs six byte products per adaptive sample and
maintains three history words. Replace that dot product with one signed16
history word times c (two byte products). Share the **unchanged transform
macro** for innovation, pitch clipping, rounding and output saturation.

The product needs signed22 precision, represented in three AVR registers.
Do not narrow it to signed16 before combining innovation. Do not remove the
pitch clamp: `63 * -32768 = -2064384`, below the original -2048000 limit.
Separately rounding pitch and innovation would also change output.

For direct history, the last usable source is `exc[-1]`: split at `j == pitch`,
rather than the generic window's `pitch-1`. Recomputed short-lag blocks need
only ten words, without two unused neighbors or a gain array. Retain ancestry
from prediction-before-innovation; completed output cannot replace it.

Use an out-of-line ASM procedure with the coefficient passed by value. Its
separate function section permits garbage collection in images that do not
use this feature. Explicit C implements the same one-tap quantizers and remains
selectable on AVR. Selection still requires both a supported architecture and
the separate ASM-enable define; memory access stays independent.

Measured isolated result: **6 rather than 10 MULs/output**, saving exactly
`32 * count + 35` cycles for nonempty blocks of count 1..10. A ten-word block
takes 1049..1181 cycles instead of 1404..1536; zero count takes six cycles with
null pointers and no access. All 44059 four-path cases agree (new ASM/C,
original three-tap ASM/C, independent wide reference), including both pitch
clipping boundaries, all 640 codebook positions, all coefficients and counts.
88118 monitored ASM returns preserve GNU saved registers and r1. Observed
history/Flash addresses and output stores match their exact expected ranges.

Complete NB3.95/WB5.75 speech CPU improves 30.17% -> 28.76% and 73.19% ->
71.78%, with 222/224 B added Flash. NB peak stack shrinks 13 B; WB stack and
static SRAM are unchanged. Full PCM, loaded IRQ and timed SPI runs retain
exact PCM/PWM without underruns. WB SPI minimum queue grows 23 -> 31 samples.
The WB layout adds up to 12 cycles to zero-coefficient frames through three
longer LPC calls; the measured aggregate includes that cost. No board or
other-profile timing claim is made.

[Shared arithmetic macros](../../Codecs/Speex/AVR/src/innovation_core.inc),
[ASM entry](../../Codecs/Speex/AVR/src/innovation.S),
[explicit C primitive](../../Codecs/Speex/AVR/src/forced_pitch.h),
[controller](../../Codecs/Speex/AVR/src/lowrate_excitation.h),
[complete-image timing/output admission](../../Codecs/Speex/AVR/WB_FORCED_ONE.md).
