# Recompute short predictor ancestry instead of retaining a frame

Original project technique for Xiph Speex low-rate forced pitch; algorithm
provenance and BSD terms remain in `vendor/speex-1.2.1/COPYING`.
Applies to the restricted 40-sample NB subframes, pitch 17..144, GNU AVR ABI,
classic AVR5 with hardware MUL; AVR GCC 7.3.0 and avr8js 0.21.1 screening.

Forced pitch reconstructs the entire prediction before adding innovation.
Using final output as feedback during a fused loop is incorrect. The source
at sample j is either old completed history or a rounded prediction of that
history. With j<=39 and lag>=17 there are at most two internal ancestors.
Recompute those rounded steps from the old history, retaining every original
rounding operation. Do not replace the chain with a single combined gain.

The current controller batches up to ten sources into a 12-word edge (two
guard neighbors); direct completed-history ranges need no copy. Existing
C/ASM three-tap kernels use gains `{0, forced_gain, 0}`. Avoid direct ranges
whose unused neighbor would read unfinished output. No new assembly backend
is needed: the same primitives and explicitly selectable C fallback apply.

This trades some computation for memory: a 24-byte stack edge replaces an
additional 80-byte prediction frame. Screening on 120 NB and 120 compact WB
frames preserves original/reference PCM and reset. The WB IRQ player checks
120 continuous frames with exact PWM, zero underruns and 397 B free SRAM.
Those are initial measurements, not full-corpus or physical-board admission;
final evidence belongs in [LOW_RATES.md](../../Codecs/Speex/AVR/LOW_RATES.md).
No performance or portability claim beyond these bounds is implied.
