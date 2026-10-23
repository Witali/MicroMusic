# NB optimization ledger

Scope: exact Xiph 1.2.1 fixed-point NB3, ATmega328P, 16 MHz / 2 KB SRAM.
Speed comes first. A small cycle cost is acceptable for a substantial Flash
saving; repeated expensive operations should be shared subroutines. Keep
all four LSP interpolations and preserve rounding, saturation and output delay.
Publish support only after the complete timer/ISR player has passed.

The latest implementation and measurements are described in README.md and
`reports/nb-round2-*.json`. Earlier reports are stage baselines, not current
binary measurements. Vendor and R4 files remain unmodified.

## Completed, measured

- Carry/byte-aware signed shifts and narrow intermediate results.
- Exact direct LPC with coefficient ages; one ASM call per 40 samples.
- Constant LSP stages and shared cosine: 5,278 B saved for 0.78% cycle cost.
- Shared signed-byte innovation vectors, merging scale, pitch and saturation.
- Minimal NB3 state; 145-sample history, 160 current samples, aligned 220 B scratch.
- Merged high-product carry chain in the LPC MAC.
- First pitch tap writes; later taps add. Only the unwritten tail is cleared.
- Mixed `-Os/O3`: 1,730 B and 45 B stack saved for 0.58% cycle cost.
- Exact 64-entry gain-pair table generated from pinned upstream constants.
- Exhaustive 128 x 32 pitch/gain coverage; independent saturation/overflow tests.
- Complete 31-stream PWM test with 128,000 additional CPU cycles per frame.

## Next candidates (unmeasured)

1. **Cache identical interpolated LSP vectors.** Store the last ten angles and
   a valid flag (21 B). `interp_qlpc` already holds the corresponding LPC.
   When all ten angles match, skip only the conversion and subsequent LPC copy;
   synthesis and coefficient ageing must still execute. Reset invalidates the
   cache. Likely useful for silence/repeated quantized envelopes; measure both
   the hit case and the comparison/copy cost on changing envelopes.
2. **Ten-sample pitch staging.** Upstream pitch sources always have negative
   offsets: the first segment stops before `j==pp`, the second before
   `j==pp+pitch`. Thus a completed innovation vector can be written before the
   next vector's pitch is computed. A 10-word pitch buffer could replace 40
   words, saving 120 B, but additional segment calls may cost cycles. Verify
   every short-pitch tail and compare speed before accepting.
3. **Shared bounded Q14 polynomial arithmetic.** Explore an ASM helper that
   avoids the generic C decomposition/copies. Prove the polynomial-input bound
   first: unrestricted `MULT16_32_Q14` truncates its high operand to signed16,
   so a generic wide multiply/shift is not automatically equivalent. Count
   call/register-save costs as well as code size.

No claim of a global speed optimum has been established. Do not mark the
ongoing optimization goal complete while useful candidates remain untested.

## Rejected or superseded experiments

- Original fully unrolled LSP: 24,636 B decoder Flash before improved arithmetic.
- Constant-stage inline LSP after improved arithmetic: 20,114 B, superseded by
  shared stage/cosine subroutines at 14,836 B and under 1% additional cycles.
- Generic peeled LSP helper: larger stack and slower than constant shared stages.
- Outlined interpolation alone: negligible size benefit, extra cycles/stack.
- Uniform `-O2`: slower than the selected mixed configuration.

Do not outline tiny MAC/shift instructions solely to eliminate textual
repetition: per-tap calls and ABI saves can dominate their work. Prefer shared
block/vector operations; measure whole-image size and worst-frame cycles.
