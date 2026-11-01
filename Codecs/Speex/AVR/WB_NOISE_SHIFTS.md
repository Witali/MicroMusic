# Exact noise table without multiplication

Baseline: `c0619042` (one-product vocoder mean). Target remains ATmega328P,
16 MHz / 2 KB SRAM, GNU ABI, explicit AVR ASM. Only NB1 / NB2.15 and its
compact WB3.95 combination use this five-word table; packet formats, feedback
precision, RNG progression and the compact Q7/16-tap QMF remain unchanged.

## Bounds and floor composition

NB1 receives one of 32 positive scales, generated from pinned upstream gains
as `floor(28406*gain/32768)`; the largest is **115088100**. The private table
primitive supports 0..121000000. Within that domain the original Q14 signed16
high component fits, and the subsequent left shift cannot overflow signed32.

For noise `n` in {-2,-1,0,1,2}, its first product is
`p=floor(n*scale/128)`. The original final rounding is
`floor((p+64)/128)`, equal to `floor((n*scale+8192)/16384)` by floor nesting.
For `n=+/-2` this reduces further to `floor((+/-scale+4096)/8192)`.
Thus four signed shifts plus zero replace all products. Compute negative
values separately: positive-infinity rounding on exact halves prevents
simply negating the rounded positive result.

`lowrate_noise.c` uses the existing 14-bit word extraction and adds a 13-bit
word specialization to `avr_shift.h`'s shared template. Only bits 13..28 of
that result are observable, so sign-extension bytes need no construction.
The existing architecture/explicit-ASM selector retains plain C shifts by
default, including on AVR, with no dependence on hardware memory access.
No new array, state, heap, assembly source or public interface is added.

## Scalar and decoder evidence

The scalar harness links four paths: actual old ASM, new ASM, explicitly
disabled-ASM C, and the original two-stage scalar C formula. They match
independent BigInt arithmetic on **228595 scales**, including all 32 caller
values, seven complete 16384-residue sweeps, all relevant half boundaries
through the full bound, endpoints and random values. This samples the proven
domain; it does not exhaust all 121000001 possible scales. Arbitrary
callee-saved patterns/r1 pass 457190 ASM-path returns; output guards and the
readonly scale pass all four paths. No C decoder is executed or timed.

AVR GCC 7.3.0, Os/LTO/mcall-prologues/mrelax, avr8js 0.21.1: the scalar table
call falls **729 -> 98 cycles**, including RET and excluding CALL/IRQ, with
**32 -> 0 hardware MULs**. LTO may specialize the destination; use full
decoder measurements for the application gain.

Fresh complete NB2.15 and WB3.95 runs each pass **10627 frames / 18 streams**,
including 6467 natural Russian/English frames, 4096 coverage and 64 padding
frames. Every PCM word and reset replay matches its established independent
oracle. Natural-speech means below weight the verifier's rounded recording
means by frame count.

| Natural speech | Before | No table MULs | Decoder CPU at 16 MHz |
| --- | ---: | ---: | ---: |
| NB2.15 cycles/frame | 103201.616 | 102561.616 | 32.25% -> 32.05% |
| WB3.95 cycles/frame | 237337.974 | 236697.974 | 74.17% -> 73.97% |

The complete decoder saves 640 cycles/frame: **0.620% NB / 0.270% WB**.
Both ASM images shrink 86 B (NB 17130 B, WB 24604 B). Static SRAM stays
1104 / 1284 B; NB peak stack falls 112 -> 110 B, WB stays 199 B. These
measurements enable every optional low rate and NB4. No physical board or
analog measurement is claimed. Active-output admission is a separate stage.

```sh
python Codecs/Speex/AVR/tests/build_noise_values.py --avr-gcc avr-gcc --baseline-root <one-product-mean-codec-root>
node Codecs/Speex/AVR/tests/verify_noise_values.mjs Codecs/Speex/AVR/build/noise-values-unit
```

Original project simplification. Existing Xiph algorithm/table provenance and
BSD notices remain in source/vendor files.

## Next unmeasured candidates

- HB1 currently expands the five noise words to forty values and then folds
  every sample with the subframe gain. Fold the five possible words once per
  subframe, then look up the result and apply output parity. This preserves
  both original quantization steps; it must not negate an unrounded input.
  The dead `interp[8]` scratch after LSP conversion may hold the five folded
  words while the original cache stays readonly. Verify its lifetime, ABI,
  scratch boundaries, C fallback and actual IRQ timing. Expected multiplication
  reduction is 160 -> 20 folded values/frame, not yet an admitted speedup.
- WB5.75/7.75 still reconstruct excitation and fold it in separate passes.
  The existing `WB_EXCITATION` macro accepts the needed 2x20 / 4x10 geometry;
  test dedicated table entries reusing that kernel and the existing C path.
  Preserve fixed rounding bias4 independently of vector count. Additional
  Flash and any speed gain must be measured before selecting this approach.
