# NB optimization ledger

Scope: exact Xiph 1.2.1 fixed-point NB3, ATmega328P, 16 MHz / 2 KB SRAM.
Speed comes first. A small cycle cost is acceptable for a substantial Flash
saving; repeated expensive operations should be shared subroutines. Keep
all four LSP interpolations and preserve rounding, saturation and output delay.
Publish support only after the complete timer/ISR player has passed.
Every ASM kernel has a selectable C fallback. Architecture defines and a
separate explicit ASM-enable define must both permit an optimized backend;
otherwise use C. Hardware memory access stays independent of arithmetic.

The latest implementation and measurements are described in README.md,
`reports/nb-word-math-*.json` and `reports/c-word-math-*.json`. Earlier
reports are stage baselines, not current
binary measurements. Vendor and R4 files remain unmodified.

## Completed, measured

- Carry/byte-aware signed shifts and narrow intermediate results.
- Exact direct LPC with coefficient ages; one ASM call per 40 samples.
- Constant LSP stages and shared cosine: 5,278 B saved for 0.78% cycle cost.
- Shared signed-byte innovation vectors, merging scale, pitch and saturation.
- Minimal NB3 state; 145-sample history, 160 current samples, aligned 220 B scratch (later reduced to 180 B below).
- Merged high-product carry chain in the LPC MAC.
- First pitch tap writes; later taps add. Only the unwritten tail is cleared.
- Mixed `-Os/O3`: 1,730 B and 45 B stack saved for 0.58% cycle cost.
- Exact 64-entry gain-pair table generated from pinned upstream constants.
- Exhaustive 128 x 32 pitch/gain coverage; independent saturation/overflow tests.
- Complete 31-stream PWM test with 128,000 additional CPU cycles per frame.
- Raw 18-bit LSP-key reuse, exhaustively justified for all NB3 code triples.
  Mean human-speech time -1.16%, corpus mean -2.35%, silence mean -22.1%;
  corpus worst +0.19%, Flash +218 B, stack +3 B, static SRAM unchanged.
  Decoder/reset verification and the final 31-stream PWM gate are complete.
- Shared Q14 signed48 ASM: 1,102 B Flash saved for 0.44% maximum frame cost;
  stack -1 B, no callee-saved registers. Generic signed30 semantics and the
  bounded LSP entry each passed 917,504 independent AVR cases.
- Closed-form first LSP stage: 824 cycles/frame and 44 B Flash saved;
  exact ceil handling, deterministic extrema and full upstream LSP/PCM checks.
- Zero pitch gain write/add fast paths and caller-side empty-segment guard:
  silence mean -14.85% versus the previous stage, corpus worst +0.11%,
  Flash +36 B. Every pitch/gain pair remains exact.
- Completed series: decoder Flash 8,684 B; all-stream weighted mean -3.22%,
  human-speech mean -1.73%; corpus maximum 146,499 versus 146,247 cycles.
  The 31-stream player passed with 128,000 extra cycles/frame, zero underruns
  and 482 B free SRAM. The ordinary speech demo is 11,916 B including audio.
- Portable backend selection and exported C library: 12 architecture/enable
  configurations passed. C matches all 13,196 AVR corpus/pitch frames plus
  58 repeated-envelope/reset frames. Native manifest/CMake static archives
  each match all 9,100 corpus frames through the public API. Default C and
  explicitly enabled AVR ASM preserve their previous binary hashes.
  C is slower on ATmega328P (maximum 332,239 cycles, ISR excluded); retain
  explicit ASM opt-in for the admitted real-time player. See PORTING.md.
- Pure-value Q14 call declarations: fixture maximum 146,384 -> 146,072
  cycles, 104 B additional Flash and 4 B additional peak stack. Each LSP
  conversion saves 78 cycles; arithmetic and selectable C path unchanged.
  All 1,058 fixtures and reset checks pass; final PWM gate below also passes.
- Signed24 final LPC/innovation clamps: another 974 cycles off the fixture
  maximum (146,072 -> 145,098), 18 B less Flash, stack unchanged. Independent
  AVR tests cover 163,840 LPC samples (105,600 clipped, 68,671 wraps) and
  163,840 innovation samples across all 64 scales and signed-byte shapes.
  The C reference branches are unchanged; final PWM gate below also passes.
- Two-MUL signed8 pitch gain: fixture maximum 145,098 -> 143,106 cycles,
  Flash 8,770 -> 8,764 B, peak stack unchanged. Independent AVR mailbox checks
  983,040 outputs, all signed8 gains, every count 0..40, write/add and zero
  paths; all 4,096 actual pitch/gain code pairs also match upstream PCM.
  The build validates the codebook range; final PWM gate below also passes.
- Pitch write/add mode moved to SREG.T: another 504 cycles off the fixture
  maximum (143,106 -> 142,602), same Flash/global stack. Free r19 for input;
  preserve only r17/Y. All 1,966,080 independent outputs, counts 0..40 and
  accumulation flags 0/1/2/255 pass. GCC ISR SREG restoration is required;
  the final interrupt-enabled admission test below passes.
- Round4 complete series: 9,100 corpus + 4,096 coverage + 58 reset frames
  exact; corpus maximum 146,499 -> 142,690 cycles, weighted corpus mean -2.52%,
  human-speech mean -2.54%. Decoder Flash 8,764 B (+80), stack 147 B (+4),
  static SRAM 1,279 B unchanged. All 31 loaded PWM streams pass 128,000 extra
  cycles/frame with zero underruns, minimum queue 23 and 478 B free SRAM.
  The C firmware is byte-identical to its fully verified 13,196-frame baseline.
  All 31 ordinary players also pass, minimum queue 73, maximum publication
  gap 80,013 cycles; the final ordinary speech demo occupies 11,996 B Flash.
  An 88-frame sample profile now excludes startup/reset and records 48.1%
  LPC, 12.7% pitch products and 11.8% innovation; keep its sampled scope.
- Packed unscaled signed24 pitch: native C and AVR C/ASM reproduce upstream;
  scratch 220 -> 180 B, static SRAM 1,279 -> 1,239 B. ASM fixture maximum
  142,602 -> 134,258 cycles, Flash 8,764 -> 8,572 B, peak stack 147 -> 143 B.
  The initial C implementation is 9,238 B (1,972 B smaller), peak stack 151 B,
  corpus maximum 333,531 cycles and pitch-coverage maximum 334,106 cycles;
  it trades a small C cycle cost for code/SRAM savings. Independent raw pitch
  checks cover 1,966,080 packed outputs and all counts/modes; innovation checks
  include unsanitized pitch extrema and both clamp boundaries. All 31 packed
  ASM players pass with 128,000 extra cycles/frame, zero underruns, minimum
  queue 27 and 524 B free SRAM (reports/nb-round5-headroom40.json).
- C-only hot loops and zero gain: applying the existing AVR `-O3` function
  attribute to packed pitch and direct IIR, with a C zero/write/add fast path,
  reduces the packed C corpus maximum 333,531 -> 315,375 and pitch coverage
  maximum 334,106 -> 315,950 cycles. Flash 9,510 B (272 B above compact packed
  C, still 1,700 B below the previous C baseline), stack/static unchanged.
  All 13,196 C frames pass. The ASM binary remains identical; C timer/ISR
  admission is distinct from the decoder-only budget and fails as below.
- C PWM admission fails on the long en_letter_a stream despite passing the
  315,950-cycle decoder-only budget: at the 130,640,000-cycle deadline there
  are 1,226 underruns, an empty queue and 514 B free SRAM; decoderError=0.
  The short adversarial/chirp probes pass. This is a sustained timing limit,
  not an arithmetic or SRAM failure; keep ASM for admitted ATmega328P PWM.
  Native manifest/CMake C archives still match all 9,100 corpus frames.

- Reuse the LPC dot-product end pointer for history writes instead of forming
  history+cursor again: exactly 2 cycles/sample, 320 cycles/frame saved;
  fixture maximum 134,258 -> 133,938, Flash 8,572 -> 8,568 B, stack/static
  unchanged. All 163,840 independent LPC samples and 1,058 frames/reset pass.
  The selectable C recurrence is unchanged; the full 31-stream/40% PWM gate passes.
  AVR GCC already hoists C innovation scale high/low decomposition before
  both vector/sample loops, so adding explicit locals offers no new hoist.

- Hoist the full-pitch-span decision before the three-tap loop. For pitch>=41
  every pp>=40, so all taps use count=40, with no repeated segment or tail
  clear. Retain the original short-pitch path and the shared block subroutines.
  This adds 94 B Flash and leaves RAM/stack unchanged in both backends.
  Combined with LPC pointer reuse: ASM weighted mean 129,334.859 -> 128,471.883
  cycles (-0.6672%), corpus maximum 134,346 -> 134,026, Flash 8,662 B.
  C weighted mean 303,552.455 -> 303,009.847 (-0.1788%), corpus/coverage
  maxima unchanged at 315,375 / 315,950, Flash 9,604 B. Both backends match
  13,196 corpus/pitch frames and 58 envelope/reset frames. Two fresh native
  exported C archives each match 9,100 frames. C still fails the long
  en_letter_a timer test (1,103 underruns). All 31 ASM players pass with
  128,000 extra cycles/frame, zero underruns, minimum queue 27, maximum
  publication gap 202,123 cycles and 524 B free SRAM; hashes match upstream.
  All 31 ordinary players also pass: minimum queue 73, maximum publication
  gap 80,013 cycles; final speech demo 11,874 B Flash including 2,940 B audio,
  static SRAM 1,374 B, peak stack 150 B, free SRAM 524 B. The final ASM mailbox
  was rebuilt and its hash equals the verified 13,254-frame image.

- Portable C innovation scale decomposition at bit 12: split scale once per
  subframe, multiply the signed-byte shape, narrow the low product after >>8,
  then use a byte-aligned *256 and one signed >>1 for *128. All bounds follow
  from the pinned 64-scale table; the build now asserts positivity as well.
  Fixture maximum 314,243 -> 297,279 cycles, Flash 9,604 -> 9,578 B; static
  SRAM/peak stack unchanged. All 1,058 fixture/reset frames and 163,840
  independent full signed8 shape/scale/pitch-edge samples match upstream.
  Complete corpus and C timer admission remain pending for the series.

- Portable C excitation saturation before Q14 extraction: after the unchanged
  rounding addition, clamp at +/-536854528, then extract bits 14..29 with
  unsigned left alignment. This removes the generic 32-bit >>14 loop without
  losing either sign or the -32768 -> -32767 rule. Fixture maximum 297,279 ->
  283,935 cycles, Flash 9,578 -> 9,594 B; stack/static SRAM unchanged. All
  459,012 independent signed32 saturation cases, 163,840 innovation samples
  and 1,058 fixture/reset frames pass. The formerly failing 402-frame
  en_letter_a C player now passes with interrupts, zero underruns, minimum
  queue 55 and 514 B free SRAM. Full-corpus admission is still pending.

- Portable generic C Q14 word extraction: preserve upstream's signed16
  high-word cast and extract bits 14..29 from both b and the bounded low
  product, avoiding both wide shift loops. This is exact for all signed16 a
  and signed32 b, including ignored top input bits. Independently verified
  917,504 C Q14 cases alongside the two ASM entries. Fixture maximum
  283,935 -> 271,191 cycles, Flash 9,594 -> 9,684 B; RAM/stack unchanged.
  The fixed override now follows the optional fastmul include on every CPU,
  so the exported C library uses it without an AVR-specific enable flag.
  All 13,196 C corpus/pitch frames, 58 reset/envelope frames and both native
  exported archives (9,100 frames each) pass. The three C changes reduce
  weighted corpus mean by 13.73%, corpus maximum 315,375 -> 272,281 cycles.
  ASM hash is unchanged (d884b63633f7171de18399ec6ae51bf130e7bc7daf2315e4dab5ecfb7edeecf5).
  C admission now passes all 31 streams twice: ordinary and 32,000 extra
  cycles/frame (10%), exact PWM, zero underruns, minimum queues 56 / 40,
  514 B free SRAM. The ordinary C demo is 12,874 B Flash with 2,940 B audio.
  See c-word-math-summary.json and c-word-math-headroom-summary.json.

- Six-MUL ASM p1 Q14: p1 is a sum of signed16 roots times 64, so factor
  the power of two and form a signed40 16x24 product followed by a byte drop.
  The standalone bounded/divisible64 core takes 53 vs 65 cycles including
  RET, no callee saves or extra RAM. All 655,360 independent cases pass;
  mailbox dispatch differs, so its 7-cycle delta is not the kernel's 12.
  Production fixture maximum 133,938 -> 133,650, corpus max 134,026 ->
  133,738, weighted mean -0.198%, Flash 8,662 -> 8,750 B, RAM/stack unchanged.
  All 13,196 corpus/pitch and 58 reset/envelope frames match upstream.
  The current image hash equals the independently tested experimental image;
  the C fallback remains byte-identical to its admitted 10%-reserve image.
  Both freshly exported C archives still match all 9,100 native host frames.
  All 31 p1 ASM players pass the 40% timer/ISR gate: no underruns, minimum
  queue 27, maximum publication gap 202,051 cycles, free SRAM 524 B.

- LPC rounding constant held in preserved r3 across the 40-sample block:
  remove 40 repeated LDI instructions for 6 setup/save/restore cycles, saving
  34 cycles/block and 136/frame. Fixture maximum 133,650 -> 133,514, Flash
  8,750 -> 8,756 B; observed global peak stack/static SRAM unchanged. All
  163,840 independent LPC samples and 1,058 fixture/reset frames pass.
  The C branch is unchanged; the final combined timer/ISR gate below passes.

- Persistent LPC history cursor in Y with ST Y+: derive dot-product Z from
  Y+20, advance Y through the two history stores, compensate mirror/age
  offsets by -2, and reset Y at each ten-sample wrap. This removes the
  repeated history+cursor formation and the post-dot MOVW. Saves another
  115 cycles/block / 460 per frame, Flash 8,756 -> 8,754 B; RAM/global peak
  stack unchanged. All 163,840 independent LPC samples and 13,196 corpus/
  pitch plus 58 reset/envelope frames pass. Final corpus maximum 133,142,
  coverage maximum 133,366 cycles. C image remains byte-identical to its
  admitted 10%-reserve build. The combined ASM series passes all 31 streams
  with 128,000 extra cycles/frame: no underruns, minimum queue 27, maximum
  publication gap 201,902 cycles and free SRAM 524 B. All ordinary players
  also pass: minimum queue 73, maximum gap 80,013 cycles, demo 11,966 B Flash.
  The final mailbox rebuild has the same hash as the 13,254-frame verified
  image (854a761dc5faafac9bec9d3c85d41900473972a76f4270e70d6845a05c288c99).

- Direct excitation input to LPC: read frame_exc-40+40*sub directly into
  separate out+40*sub instead of copying 320 B per frame. Input remains
  unchanged, and the exact 40-sample delay and coefficient-age transition
  remain intact. Expanded tests cover 163,840 samples per AVR mode with
  input/output guards, plus two million native C samples across both modes.
  Production hashes equal the independently verified fixture experiments:
  ASM max 133,054 -> 130,369, Flash 8,754 -> 8,750 B, peak stack 143 -> 141;
  C max 271,191 -> 268,681, Flash 9,684 -> 9,694 B, peak stack 151 -> 153.
  All 1,058 fixture/reset frames pass in each backend. Full-corpus and
  timer/ISR admission for this series remain pending.

- Reclaim pitch workspace for synthesis: qlsp stays live at offset 0 (20 B),
  pitch uses 20..139 during excitation; after it dies, rewind the local
  allocator and put distinct ak/interpolated-LSP arrays at 20/40. Scratch
  shrinks 180 -> 140 B, static SRAM 1,239 -> 1,199 B. No in-place LSP
  assumption or new aliasing between its input/output is required. Native
  bounds tracking reports peak 140; both exported C archives pass 9,100 frames.
  The selected aligned-allocation variant gives ASM fixture max 130,361,
  Flash 8,742 B, peak stack 141; C max 268,707, Flash 9,698 B, peak stack 153.
  Compared with direct-input-only, ASM saves 8 cycles/frame and 8 B Flash;
  C pays about 26 cycles/frame and 4 B Flash for the same 40 B SRAM saving.
  Direct typed views were smaller but cost ASM about 260 cycles per four
  conversions and 2 B stack; retain the faster common allocator path.
  All 1,058 fixture/reset frames per backend pass; final corpus/PWM tests
  are running from isolated source copies with matching file hashes.

## Next candidates (not yet admitted)

1. **Ten-sample pitch staging.** Upstream pitch sources always have negative
   offsets: the first segment stops before `j==pp`, the second before
   `j==pp+pitch`. Thus a completed innovation vector can be written before the
   next vector's pitch is computed. A 30-byte packed pitch buffer could replace
   the current 120 B, saving 90 B, but additional segment calls may cost cycles. Verify
   every short-pitch tail and compare speed before accepting.

No claim of a global speed optimum has been established. Do not mark the
ongoing optimization goal complete while useful candidates remain untested.

## Rejected or superseded experiments

- Original fully unrolled LSP: 24,636 B decoder Flash before improved arithmetic.
- Constant-stage inline LSP after improved arithmetic: 20,114 B, superseded by
  shared stage/cosine subroutines at 14,836 B and under 1% additional cycles.
- Generic peeled LSP helper: larger stack and slower than constant shared stages.
- Outlined interpolation alone: negligible size benefit, extra cycles/stack.
- Uniform `-O2`: slower than the selected mixed configuration.
- A 20-byte interpolated-LSP cache was superseded by a frame/raw-key cache
  without additional static SRAM. Comparing quantized angles once per frame
  was correct but slower on hits than also skipping codebook reads. Hoisting
  the update flag outside the subframe loop increased stack by 5 B and miss
  time by 112 cycles, so the simpler inner flag was retained.

Do not outline tiny MAC/shift instructions solely to eliminate textual
repetition: per-tap calls and ABI saves can dominate their work. Prefer shared
block/vector operations; measure whole-image size and worst-frame cycles.
