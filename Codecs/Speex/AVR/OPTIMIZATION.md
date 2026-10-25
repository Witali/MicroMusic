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
  All 1,058 fixture/reset frames pass in each backend. The combined series
  below also passes complete corpus and loaded timer/ISR admission.

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
  All 13,196 corpus/pitch frames and 58 envelope/reset frames per backend
  pass with a single firmware hash. ASM weighted corpus mean falls 2.0941%
  versus the previous admitted image (127,621.476 -> 124,949.016 cycles);
  C falls 0.9502% (261,406.472 -> 258,922.472). Corpus maxima become
  130,449 / 269,797 cycles; pitch-coverage maxima 130,673 / 270,362.
  All 31 loaded players per backend pass exact PWM, independently counted
  loads, zero underruns and intact SRAM: ASM +128,000 cycles/frame (40%),
  minimum queue 28, maximum publication gap 199,290 cycles, free SRAM 564 B;
  C +32,000 (10%), queue 41, gap 173,573, free SRAM 552 B. Runs use isolated
  source copies whose 67 source/tool/test file hashes match the main tree.
  All 31 ordinary players also pass. ASM minimum queue 73, maximum gap
  80,013 cycles, speech demo 11,954 B Flash; C queue 58, gap 140,476,
  demo 12,888 B. Static player SRAM is 1,334 B, observed stack 150 / 162 B.
  The rebuilt main ASM mailbox matches the 13,254-frame verified hash;
  the rebuilt main speech demo matches the independently simulated clone.
  Reports: phase-reuse-{asm,c}-{summary,means,headroom-summary}.json.


- Fuse long-pitch sums with innovation. For pitch>=41 and nonzero gain code,
  a shared ASM vector entry accumulates three signed8 x signed16 products in
  signed24 registers, keeping a rolling history window. It shares scaling,
  clamps, rounding and stores with the existing packed-pitch entry; SREG.T
  selects the source and is preserved by GCC ISRs. Only the fused entry saves
  its additional history/gain registers. Zero gain code clears the buffer once;
  short nonzero pitch retains all original segments and zero tails. The pinned
  table's zero-code contract is checked during source preparation.
  The C vector is inlined into one O2 forty-sample subroutine: setup is shared
  across vectors without expanding ten MAC bodies. Relative to the preceding
  admitted image, weighted corpus mean falls 4.1057% ASM / 5.3352% C; human
  speech falls 4.0968% / 5.3225%. Flash 8,742 -> 9,078 / 9,698 -> 10,316 B;
  static SRAM remains 1,199 B, observed stack 141 / 153 B. ASM corpus/coverage
  maxima rise only 36 cycles to 130,485 / 130,709; C maxima fall 141 to
  269,656 / 270,221. This is a mean-speed optimization, not a worst-frame gain.
  Both match 13,196 corpus/pitch and 58 envelope/reset frames with one image
  hash each. Independently test 673,280 samples per backend over every table
  gain/scale/shape, full signed16 history, exact clamp boundaries +/-1 and
  random bounded gains: preserve all buffers, AVR callee-saved registers and r1.
  Existing packed innovation still matches 163,840 signed24 edge samples;
  native primitives/PCM, 12 backend configurations and both exported C archives
  (9,100 frames each) pass. All 31 loaded players per backend pass exact PWM,
  zero underruns and intact SRAM. ASM +40% CPU: minimum queue 28, maximum
  publication gap 199,320 cycles; C +10%: queue 41, gap 173,411. Free SRAM
  remains 564 / 552 B. All 31 ordinary players also pass: queues 73 / 58,
  maximum gaps 80,013 / 140,314 cycles. Demo Flash 12,282 / 13,508 B includes
  2,940 B compressed speech; static SRAM 1,334 B, peak stack 150 / 162 B.
  All 71 source/tool/test files in each of four isolated copies match the
  main tree. Main ASM mailbox/demo rebuilds match the verified images.
  Reports: fused-long-{asm,c}-{fixtures,speech,means,pitch-coverage,lsp-reuse}.json,
  fused-long-kernel.json, fused-long-innovation.json, portable-fused-long-library.json.

- Retire history words before loading the next fused-pitch word. After the
  first two products, move b into a and load c directly into b, then form its
  product. Remove the final b=c MOVW and both r8/r9 save/restore pairs. The
  ten-sample kernel takes 1,442..1,515 vs 1,460..1,533 cycles, including RET;
  all 673,280 independent outputs per backend and 1,058 fixture/reset frames
  pass. Decoder Flash 9,078 -> 9,068 B; static SRAM/global peak stack unchanged.
  Packed pitch and the C fallback are unchanged. The combined register/bias
  series below also passes complete corpus and PWM admission.

- Hold the shared innovation rounding byte (32) in preserved r8 across each
  ten-sample block. Save/restore it in both entry paths, below mode-specific
  history saves. Six setup/save/restore cycles replace ten repeated LDIs,
  saving 4 cycles per vector / 64 per frame in both packed and fused use.
  A matched three-entry mailbox on the preceding commit and new source checks
  673,280 samples per fused ASM, packed ASM and C path, including all callee-
  saved registers, r1, read-only buffers and guards. Fused kernel ranges
  1,442..1,515 -> 1,438..1,511; packed 944..1,017 -> 940..1,013; C unchanged.
  Flash 9,068 -> 9,076 B; net vs prior admitted image -2 B. Combined mean
  119,819.031 -> 119,531.219 cycles (-0.2402%), human speech -0.2389%; corpus
  and pitch-coverage maxima 130,421 / 130,645 (both -64). All 13,196 corpus/
  pitch and 58 envelope/reset frames pass; static SRAM/global stack unchanged.
  A rebuilt C mailbox is byte-identical to its admitted image, retaining the
  existing corpus, export and 10%-CPU PWM admission. All 31 ordinary ASM
  players pass: queue >=73, maximum gap 80,013 cycles. All 31 with +40% CPU
  also pass: queue >=28, maximum gap 199,256, zero underruns and unchanged
  PWM hashes. Free SRAM remains 564 B; demo Flash 12,280 B with 2,940 B
  audio, static SRAM 1,334 B, peak stack 150 B. Both main mailbox/demo
  rebuilds match independently simulated images; both 71-file copies match
  the main sources. Reports: shared-bias-{before-kernel,kernel,
  fixtures,innovation}.json, register-asm-*.json, register-c-reuse.json.

- Add a runtime-count fused innovation entry for 0..10 samples. A separate
  saved-register prologue jumps into the existing bias/shape/clamp body;
  the fixed-ten and packed entries retain their exact instruction timings.
  Empty blocks return in 6 cycles. The nonempty runtime entry costs four
  cycles more than fixed-ten on the same ten samples. Independently check
  336,628 variable-length outputs each in ASM/C, all eleven counts, output
  tails, input/gain guards, all callee-saved registers and r1, alongside
  673,280 outputs each in the three existing entries. Full segment and PWM
  admission passes with the short-pitch caller below. See variable-innovation-kernel.json.

- Fuse short pitch by selecting contiguous ranges outside the sample loop.
  For pitch 17..40, j<pitch-1 and pitch+1<=j<min(2*pitch-1,40) use the rolling
  kernel. At the two switches and two possible tail boundaries, ASM stages
  three history words for a one-sample call; C computes the scalar sum directly.
  The zero tail uses zero gains in ASM and a scale-only C loop. Four shape
  indices and all original source positions, clamps and bit consumption remain
  exact. Test zero gain first in the frame controller; nonzero short pitch no
  longer needs packed pitch products. Historical pitch_add.S is unreferenced
  in the production link but remains independently tested with its C fallback.
  An independent mailbox compiles real AVR ASM-on and ASM-off translation
  units: 1,966,080 exact samples each, all 24 pitches, 32 gains and 64 scales,
  full signed16 history, source/output/packet guards, twenty consumed bits,
  callee-saved registers and r1. Both complete decoders match 13,254 corpus/
  pitch/reset frames; native primitives, twelve backend configurations and
  both public C library archives (9,100 frames each) pass.
  Compared to the admitted register-series ASM and fused-long C images:
  mean -0.7430% / -1.1065% (human speech -0.7855% / -1.1673%); corpus maxima
  130,421 -> 125,587 / 269,656 -> 254,742; coverage maxima 130,645 -> 127,734 /
  270,221 -> 255,307 cycles. ASM has tiny per-stream regressions (worst mean
  +0.0055%); C improves every stream mean. Flash 9,076 -> 9,300 / 10,316 ->
  11,316 B, static SRAM 1,199 B and global peak stacks 141 / 153 B unchanged.
  The smaller shared C edge-staging experiment used 10,868 B but raised fixture
  maximum to 257,223 and stack to 157; prefer the faster scalar-edge C form.
  All 31 ordinary players per backend pass exact PWM without underruns:
  queues 73 / 65, maximum gaps 80,013 / 124,895 cycles. Loaded players also
  pass: ASM +40% CPU, queue 31, gap 194,266; C +10%, queue 49, gap 157,992.
  Free SRAM remains 564 / 552 B. Speech demos are 12,498 / 14,514 B including
  2,940 B audio, static SRAM 1,334 B, stack 150 / 162 B. All four 76-file
  source copies match the main tree; main mailbox/demo rebuild hashes match
  the independently verified images.
  Reports: segment-{asm,c}-{fixtures,speech,means,pitch-coverage,lsp-reuse}.json,
  segment-short-kernel.json, portable-segment-library.json.

### One zero vector and a 60-byte scratch arena

The gain-zero path now reuses one immutable 30-byte signed24 vector for its
four ten-sample calls. Clear it at most once per frame, at the first zero-gain
subframe; nonzero paths never touch it. Synthesis overwrites this region only
after all excitation is complete, so the readiness flag must reset each frame.
qlsp occupies bytes 0..19; the zero vector uses 20..49, and the later ak/interp
arrays use 20..39 / 40..59. Scratch shrinks 140 -> 60 B in both backends.

AVR GCC 7.3.0, same mixed Os/O2/O3+LTO settings: 14,278 exact frames per
backend (9,100 corpus, 4,096 pitch/gain, 58 LSP/reset, 1,024 new zero-gain
transition cases). Native scratch tracking reaches exactly 60 B; native
upstream arithmetic and two exported public C archives also pass. Static SRAM
is 1,119 B (80 B saved); stack stays 141 / 153 B, leaving 788 / 776 B free.
Flash is 9,306 / 11,334 B (+6 / +18). Mean over 31 streams improves 0.0558% /
0.0474%; human speech improves 0.0097% / 0.0261%. ASM stream means can regress
up to 0.0165%, and corpus maximum rises 125,587 -> 125,613; C maximum falls
254,742 -> 254,720. Pitch-coverage maxima are 127,760 / 255,285 cycles.
On the deliberately mixed zero-gain workload means fall 104,592 -> 103,549 /
212,344 -> 211,255. This is primarily a memory saving with a small aggregate
speed gain, not a speedup on every packet. Full ordinary/loaded PWM admission
now passes all 31 streams in both backends: 9,100 frames / 1,456,000 samples
per scenario, exact PWM hashes, zero underruns. ASM +40% CPU retains queue 31
and gap 194,237; C +10% retains queue 49 and gap 157,970 cycles. Ordinary
queues are 73 / 65, gaps 80,013 / 124,873. Player SRAM is 1,254 B, stack
150 / 162 B and free space 644 / 632 B. Speech demos use 12,506 / 14,532 B
Flash including 2,940 B audio. All four 77-file source copies match the main
tree; main mailbox/demo binary hashes match the verified images. Source
commit and hashes are pinned in zero-vector-admission-audit.json.
Reports: zero-vector-{asm,c}-*.json, zero-vector-host.json,
zero-vector-native.json and portable-zero-vector-library.json.

### Scalar one-sample ASM entry

The pinned prototype from `nb3-scalar-boundary.patch` is now in production.
It saves exactly 37 kernel cycles on 67,328 independent paired cases, reads
three words/gains directly, keeps the Flash pointer in already-saved r3/r8,
and shares the unchanged transform with T=0. The controller selects it for
count=1; its branch can add one cycle to the fastest short-pitch unit case.
ASM/C short-controller tests cover 1,966,080 samples each. Rebuilt main unit
images match those independently executed binaries byte-for-byte.

The main ASM decoder matches 14,278 fresh AVR frames and the measured prototype
binary. Mean over 31 streams improves 0.0179% (speech 0.0182%); corpus max is
125,500 (fixture max 125,373), coverage max 127,280 cycles. Flash is 9,460 B
(+154), SRAM/stack stay 1,119 / 141 B. Full ordinary and +40% CPU PWM now
pass all 31 streams / 9,100 frames / 1,456,000 samples each, exact PWM and no
underruns. Queues remain 73 / 31, gaps 80,013 / 194,065 cycles. Player static
SRAM/stack remain 1,254 / 150 B, free 644 B; ordinary speech demo is 12,660 B
including 2,940 B audio. Main mailbox/demo hashes match the admitted images.
Explicit C decoder, ordinary demo and +10% loaded demo are byte-identical to
their admitted zero-vector images. Both freshly exported C archives pass
9,100 frames through the public API. `scalar-main-admission-audit.json` pins
the 77-file source copies, decoder/unit hashes and C equivalence.
Reports: scalar-main-*.json, portable-scalar-main-library.json.

### Direct rounded output for known-zero adaptive gain

For signed8 shape and 0<=scale<=121,000,000, the original two floors and Q14
rounding reduce to floor((shape*scale+262144)/524288). The output fits s16
without saturation; use this only for proven zero adaptive sum. Remove the
packed zero vector, readiness flag and clear entirely. Scratch remains 60 B
because the live qlsp plus the later synthesis arrays still require it.
ASM uses four signed-byte products, the high-byte rounding addition and three
right shifts. C uses four signed8-by-unsigned8 products with signed16 floor
carries, then ((c+4)>>3)+d*32; all intermediates fit their documented bounds.
This retains explicitly selectable C and its real AVR Flash accesses.

Three paths (new ASM, actual AVR C with ASM disabled, original packed-zero
ASM) match 280,960 independent samples each. All signed8 shapes, 64 NB3 scales,
scale boundaries, 6,120 rounding-neighbor blocks and 20,000 random blocks pass
guards/ABI/r1. Kernel cycles including RET: new ASM 501 constant / ten samples,
packed zero 941..981, separate O2 C worker 549. The selected production O3 C
wrapper uses 11,836 B vs 11,072 for O2, but improves the 1,024-frame transition
mean 196,006 -> 195,736 cycles. Speed takes priority; wide-product C variants
are slower. Their exact workload/Flash/timing comparison is in the variants
report; other MCU timings are unmeasured.

Both main binaries match 14,278 exact AVR frames each. Mean over 31 streams
improves 0.2730% ASM / 0.5649% C (human speech 0.1342% / 0.2760%). ASM has a
small synthetic-stream mean regression, at most 0.0341%; C improves every
stream mean. Corpus maxima 125,465 / 254,619; pitch coverage 127,245 / 255,184.
Flash 9,578 / 11,836 B (+118 / +502); SRAM/stack stay 1,119 / 141 or 153 B.
Two fresh native public C archives each match 9,100 frames, and native scratch
tracking remains 60 B. Twelve architecture/backend configurations pass.

All four ordinary/loaded PWM scenarios pass all 31 streams, exact output and
zero underruns, 9,100 frames / 1,456,000 samples each. ASM +40% CPU retains
queue 31 / gap 194,094; C +10% retains queue 49 / gap 157,864 cycles. Ordinary
queues 73 / 65 and gaps 80,013 / 124,767. Player SRAM/stack/free remain 1,254 /
150 or 162 / 644 or 632 B. Speech demos are 12,782 / 15,036 B including 2,940 B
audio. Audit pins four 81-file copies, actual binary hashes and a post-run
comment clarification that preserves both rebuilt decoder images.
Reports: zero-transform-*.json, portable-zero-transform-library.json.

### Bounded variable-count zero tails

Pitch 17..19 now sends its final 5/3/1 zero-adaptive samples to a separate
count 0..10 ASM entry. Keep the fixed-ten body unchanged: count zero returns
in six cycles without data access; count ten adds four cycles. The controller
needs no zero gain array or dummy history loads. A bounded portable C block
helper remains explicitly selectable with ASM disabled on AVR.

Independent tests add 140,471 variable samples per ASM/C backend to the
existing 280,960 fixed samples in each path; all counts, full signed8 shapes,
rounding boundaries, tails/guards/ABI/r1 pass. Short-controller ASM/C tests
cover 1,966,080 samples each, now with per-pitch statistics. ASM means improve
at every pitch 17..40; minima/maxima 6,950..7,862 -> 6,918..7,531 cycles.
The direct C replacement improves that isolated test too, but slows the
31-stream decoder by 0.0062% (worst mean +0.0259%, max +144 cycles). Scale
rematerialization and an outlined split-scale helper regress 0.0819% / 0.0724%.
Preserve the faster previous C loop: C decoder and ordinary/+10% demos match
the admitted zero-transform binaries byte-for-byte. Do not infer decoder
speed from a standalone kernel/controller. Reports retain all three rejected
C variants, exact workloads and expressions.

ASM matches 14,278 frames; corpus mean -0.0421%, human speech -0.0431%, no
stream mean regressions. Corpus max 125,245; pitch coverage max 125,753 cycles.
Flash 9,602 B (+24), SRAM/stack unchanged at 1,119 / 141 B. Both ordinary and
+40% CPU PWM pass all 31 streams: exact PWM, zero underruns, queues 73 / 31,
gaps 80,013 / 193,874, 644 B free SRAM. Speech demo is 12,806 B including
2,940 B audio. Main mailbox/demo match the tested images; two 82-file source
copies match the main tree. Fresh manifest/CMake C archives each match 9,100
frames. Reports: short-tail-*.json, portable-short-tail-library.json.

### IIR wrap check from the already advancing pointer

Precompute the low byte of history+20 in r16 once, then compare it to Y's low
byte after each word store. Ten positions in a 20-byte span are distinct
modulo 256, even across a page; reset the full Y from the history base when
they match. Remove the parallel byte cursor and its update/reset. Callee-saved
registers and C fallback stay unchanged. The extra setup cycle costs one;
36 ordinary iterations save one each and four wraps save two each: net 43
cycles per 40-sample call, 172 per full frame. Flash decreases two bytes.

Paired unit tests match 655,360 samples, all 256 SRAM base low bytes, both
I/O modes, coefficient ages, clipped/wrapped values, guards, callee-saved
registers and r1. Every one of the 512 per-mode/address rows saves exactly
43 cycles/call. The earlier full IIR/innovation/C saturation suites also pass.
All 14,278 decoder frames remain exact; every stream minimum/mean/maximum
falls by 172 cycles. Corpus mean improves 0.1455%, human speech 0.1430%;
corpus max 125,073 and coverage max 125,581. Flash 9,600 B, SRAM/stack
1,119 / 141 B unchanged. Both complete ordinary/+40% CPU PWM runs pass all
31 streams, exact output and zero underruns, queues 73 / 31, gaps
80,013 / 193,831 cycles, free SRAM 644 B. Ordinary demo is 12,804 B including
2,940 B audio. Main decoder/player/unit match verified images, and both
83-file source copies match the main tree. C decoder and both C demos are
rebuilt and byte-identical to the admitted images. Reports: iir-cursor-*.

### IIR coefficient-age and steady phases

The first ten samples still age one coefficient after each output, preserving
the upstream transposed recurrence. At their end the full coefficient array
is stable. Reuse the dead den pointer and coefficient base register pairs for
words 0/1 and enter a separate thirty-sample loop. Its first two coefficients
come from MOVW; the remaining eight still use SRAM. Source macros share MAC
and finish text without per-tap CALL overhead. The state and ABI are unchanged.

Relative to d000fc4: remove twenty warm-phase test cycles and ninety steady
test cycles; save 120 net coefficient/address cycles over thirty samples.
Transition setup costs ten; the warm loop exit saves one: exactly 221 cycles
per call, 884 per frame. The IIR function grows 686 to 1,256 B, matching the
570 B whole-image increase. Speed takes priority; the 10,170 B mailbox and
13,374 B speech demo still fit the target. Static SRAM/stack remain
1,119/141 B for the mailbox and 1,254/150 B at player peak.

All 512 paired address/I/O rows save 221 cycles on each call. The independent
655,360-sample sweep covers all 256 state-base low bytes, page crossings,
changing signed16 coefficients, wrap/saturation, guards, read-only inputs and
callee-saved/r1 checks at RET. Earlier 327,680-sample IIR, innovation ASM/C and
C saturation tests also pass. All 14,278 decoder frames are exact; every
stream min/mean/max falls by 884 cycles. Mean over 31 streams falls 0.7491%,
human speech 0.7361%; corpus max is 124,189, pitch coverage max 124,697.

Both full PWM matrices pass 31 streams / 9,100 frames with exact PWM and no
underruns, including +40% CPU foreground work. Queue minima 73/31 and
free SRAM 644 B are unchanged; max ready gaps are 80,013/193,610 cycles.
Two 83-file source copies match the main tree; main mailbox, speech demo and
unit match the measured images. Fresh C decoder and normal/+10% demos match
the admitted images byte-for-byte. Two fresh native C archives each match
9,100 frames; all twelve backend-selection cases pass. Reports iir-phases-*
and portable-iir-phases-library.json retain source/image hashes and evidence.

### Bounded group of four innovation indices

NB3 index groups begin at bit offsets 1,2,3,4 and consume twenty bits. After
one bounds/overflow check, read three unsigned bytes a,b,c. Two overlapping
16-bit windows, ((a<<8)|b)>>(6-offset) and ((b<<8)|c)>>(4-offset), each
contain two five-bit fields. Mask/extract them to four u8 values and advance
the reader once. Zero, long and short pitch callers use the same private
C subroutine. Offset zero also fits; offsets 5..7, insufficient data and
pre-existing overflow take four generic calls, preserving partial consumption
and sticky overflow. The public generic reader is unchanged. Bytes are
assembled by value, without native-endian or unaligned-word assumptions.

The new independent AVR C-only test checks 72,192 blocks / 288,768 indices
per implementation. A bit-by-bit oracle covers all eight offsets, available
bits 0..27, every adjacent index pair, 32,768 random blocks and 512 sticky
overflow cases including noncanonical positive/negative flags. Actual SRAM
read hooks reject reads outside valid input bytes; read-only data/metadata,
input/output guards, all callee-saved registers and r1 are checked at RET.
For valid offsets 1..4, the isolated new function takes 174/164/154/144 cycles
versus 422/467/427/472 for four original reads. These unit timings describe
their linked context, not a projection of whole-decoder timing.

Against 098c3d9, both backends match all 14,278 frames. Every tested stream
mean and maximum improves. Corpus means fall 1.0228% ASM / 0.8087% C;
human speech 1.0081% / 0.8020%. Corpus maxima are 123,008 / 253,039 cycles;
pitch coverage maxima 123,488 / 253,604. Decoder Flash grows 232/248 B to
10,402/12,084 B; static SRAM remains 1,119 B. ASM stack grows 4 B to 145,
C remains 153. Ordinary speech demo Flash grows 296/248 B to 13,670/15,284 B.

All four PWM matrices pass 31 streams / 9,100 frames with exact output and
zero underruns. ASM normal/+40% CPU queues 74/32, max gaps 80,013/191,998,
640 B free SRAM. C normal/+10% queues 65/50, gaps 123,187/156,220, 632 B
free. Timer intervals remain 1,994..2,006 cycles. Four 87-file source copies
match the main tree; freshly rebuilt main decoder/demo/unit match the tested
images. Fresh native PCM/primitives and two C archives pass; each archive
matches 9,100 frames, and twelve backend-selection cases pass. Reports
nb3-indices-* and portable-nb3-indices-library.json retain the evidence.

### Bounded thirteen-bit subframe header

Pitch(7), gain(5), energy(1) occupy thirteen consecutive bits beginning at
offsets 4,5,6,7 in this NB3 layout. After one complete-data/overflow check,
assemble ab=(a<<8)|b and return ((ab<<(offset-3))|(c>>(11-offset)))&8191.
The word's high seven, middle five and low one bits yield the original fields.
Explicit unsigned bytes and value assembly avoid native endian/alignment
assumptions and a 32-bit temporary. Other offsets, insufficient data or an
existing overflow flag call the generic reader in the original 7/5/1 order.
This preserves partial consumption and sticky overflow; the public reader
and the four-index reader are unchanged.

An outlined C helper and an inline C helper each match 9,100 frames per
backend. Inline improves every stream mean relative to outlined, saves 40 B
ASM / 28 B C Flash, and needs no extra peak stack. It has one production
source call site, inside the subframe loop. Against 30f2a58, selected-inline
corpus means fall 1.0891% ASM / 0.5391% C, versus 0.9807% / 0.4980% for
outlined. The superseded form has no separate component-unit/PWM admission;
its pinned two-file patch and comparative reports remain reproducible.

The independent C-only reader mailbox now tests both groups. Header tests
check 109,568 blocks / 328,704 fields per implementation, including all
8,192 headers at every offset 0..7, available bits 0..20, 32,768 random blocks
and 512 noncanonical sticky-overflow cases. A bit-by-bit oracle checks output,
position and overflow; SRAM load hooks check actual read bounds. Read-only
input/metadata, guards, all callee-saved registers and r1 are checked at RET.
For production offsets 4..7, the linked inline wrapper takes 151 cycles
versus 421/462/464/466 for ordered generic reads. The existing 72,192-case
four-index test also passes in this new binary context. Unit timings are
not a whole-decoder timing projection.

Both selected backends match all 14,278 frames. Every stream mean/maximum
improves; human-speech means fall 1.0689% ASM / 0.5283% C. Corpus maxima
121,741/251,823 cycles, pitch maxima 122,221/252,388. Decoder Flash grows
220/224 B to 10,622/12,308 B. Static SRAM 1,119 B and stack 145/153 B are
unchanged. Ordinary demo Flash grows 220/228 B to 13,890/15,512 B.

All four PWM matrices pass 31 streams / 9,100 frames with exact output and
zero underruns. ASM ordinary/+40% queues 74/33, max ready gaps 80,013/190,667,
640 B free SRAM. C ordinary/+10% queues 65/50, gaps 121,897/154,994, 632 B
free. Stack is unchanged in every matched player row. Four 88-file source
copies match the main tree; main decoder/demo/unit binaries match the tested
images. Native PCM/primitives, both fresh C archives (9,100 frames each) and
twelve backend-selection cases pass. Reports nb3-header-* and
portable-nb3-header-library.json retain hashes and evidence. The sampled
88-frame ASM profile now spends 0.431% in generic/constant reader functions.

## Third IIR coefficient cache (2026-10-25)

Once the first ten coefficient-age samples complete, the state-base pointer
is dead if X rewinds from the coefficient-table end and Y rewinds at ring wrap.
Reuse r12:r13 for a third LPC word. The steady dot product uses three MOVW
coefficient reads and seven SRAM reads instead of two/eight. State format,
rounding, clipping, coefficient ages, ABI and the selectable C path are unchanged.

ATmega328P / AVR GCC 7.3.0 / existing mixed Os/O3+LTO flags: 111 cycles saved
per 40-sample NB block, 444/frame; Flash 10,608 -> 10,610 B, SRAM/stack unchanged.
All 512 address/mode rows (256 low bytes, both input/output modes) save exactly
111 in their minima/maxima and 32*111 total. Independent recurrence checks cover
655,360 address-sweep samples plus 327,680 broader samples and wrap/clipping.
Every matched stream min/mean/max over 14,278 exact NB frames saves 444.
The 31-stream mean falls 0.3905%, corpus maximum 122,066 -> 121,622 cycles.
Normal/+40% PWM passes all 31 streams, queues 74/33, free SRAM 629 B.

The same change saves 118 cycles/block for order eight, or 916 cycles/frame
across both WB bands. All 10,563 WB frames and 744 repeat cases remain exact;
all 16 WB PWM streams and the two +5% streams pass. Both C decoder images stay
byte-identical; two fresh portable C archives each pass 9,100 NB and 10,563 WB
frames. Reports `iir-cache3-*` bind sources, images and upstream PCM/PWM.
These are ISA/peripheral measurements, not physical-board or other-CPU claims.

The preceding kernel is pinned to 61a51e6. Restore and build the original unit
without relying on an archived worktree (use a new output directory):

```sh
python Codecs/Speex/AVR/tools/prepare_iir_baseline.py --ref 61a51e6 --out Codecs/Speex/AVR/build/cache3-unit-baseline
python Codecs/Speex/AVR/build/cache3-unit-baseline/tools/build_iir_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/build/cache3-unit-baseline/tests/verify_iir_cursor.mjs
```

The baseline reproduction was rebuilt byte-identically to the executed unit.
`tests/audit_iir_cache3.py --rebuild --avr-gcc avr-gcc` binds the retained
`build/cache3-*` qualification artifacts and rebuilds representative player
images; it does not claim to rerun or recompile all 80 frozen player images.
Run that historical source-bound audit at commit 0449cd9, before later stages.

## Accumulate and fuse NB quarter-step LSP interpolation (2026-10-25)

The pinned NB3 codebooks produce multiples of 16. With four equal quarters,
both original Q14 products are integral before their separate rounding. Compute
`delta=(next>>2)-(old>>2)` once, replacing the endpoint scratch with ten deltas.
Advance the existing raw endpoint state at each quarter and apply the original
sequential margin pass only to the output. After four advances the raw state
equals the new endpoint exactly; the old end-of-frame copy is unnecessary.
Reset uses zero deltas and one interpolation; cache hits retain their LPC reuse.
Static assertions pin order 10, four quarters and margin 16.

The selected outlined C helper fuses raw advancement, endpoint clamping and the
margin pass, keeping the next raw angle in a scalar. Preserve the two separate
right shifts when enforcing an upper margin: earlier corrections can make an
odd angle. Retain integer promotions and narrow assignments as upstream does.
Raw state, deltas and output are disjoint; `restrict` expresses this existing
precondition. This C helper is shared by both arithmetic backends, with no new
assembly or architecture requirement.

26 candidates each passed 1,058 AVR fixture frames and reset. Full 9,100-frame
comparisons of the leading variants (same AVR GCC 7.3.0 / mixed Os/O3+LTO flags):

| ASM decoder candidate | Flash | Weighted mean cycles | Maximum cycles |
| --- | ---: | ---: | ---: |
| Original generic interpolation, third IIR cache | 10,610 B | 113,264.523 | 121,622 |
| Four separate constant-quarter loops, O3 | 11,452 B | 110,168.254 | 118,149 |
| Accumulate raw state, separate margin, O3/restrict | 10,852 B | 110,179.923 | 118,141 |
| Accumulate raw state and fuse margin, O3/restrict | 10,872 B | 109,985.618 | 117,927 |

The selected version is faster and 580 B smaller than the separate-quarter O3
candidate. The C decoder falls from 11,870 to 11,166 B, mean 232,365.300 to
221,193.812 cycles, maximum 246,334 to 233,722. Static SRAM stays 1,119 B;
observed mailbox stacks fall 158 to 154 B (ASM) and 166 to 138 B (C).

Native tests compare 1,573,120 helper calls / 589,888 cases to untouched Xiph,
including all 262,144 code triples as changing endpoints, zero-delta reset,
65,536 full-signed multiple-of-16 transitions and 64 edge transitions. The AVR
mailbox separately compares 82,688 calls / 826,880 angles to the original
compiled for AVR, including its 16-bit int promotions, unclamped quarter state,
read-only inputs/deltas, guards and r1. Original LSP-to-LPC, bit-reader and
two-million-sample IIR tests also pass. Decoder/PWM admission is recorded in
`reports/lsp-quarter-*`; the previous `iir-cache3-*` evidence is historical.

Both backend images each match 14,278 NB frames with reset and pitch/zero-gain
coverage. Four fresh 31-stream PWM matrices pass: ASM normal/+40% CPU reserve,
C normal/+10%, zero underruns, minimum queues 74/33 and 66/54, free SRAM
633/649 B. Two exported C archives each pass 9,100 NB and 10,563 WB frames;
23 backend-selection configurations pass. The shared NB change also reduces
WB ASM mean/max to 261,068/268,595 cycles, stack to 243 B and player stack to
252 B. All 16 WB PWM streams pass (minimum queue 26); both +5% streams pass
(minimum queue 10). The audit binds 142 frozen player images and rebuilds
representative images. Measurements are ISA/peripheral simulation, without
a physical-board claim. The C WB decoder remains too slow for this MCU.

All screened helper sources and three controller variants are retained in
`reports/lsp-quarter-candidates.json`. Reproduce a candidate in a new directory
from the pinned pre-change commit; the selected replay was byte-identical:

```sh
python Codecs/Speex/AVR/tools/prepare_lsp_candidate.py --candidate step-fused-o3 --out Codecs/Speex/AVR/build/lsp-replay
python Codecs/Speex/AVR/build/lsp-replay/tools/build.py --avr-gcc avr-gcc --backend asm
python Codecs/Speex/AVR/tools/build_interpolate_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_interpolate.mjs
```

## Combined validated NB subframe reader (2026-10-25)

Parse a complete 33-bit group in one outlined C helper: pitch(7), gain(5),
energy(1), then four five-bit innovation indices. The four windows begin at
byte 3+4*sub / bit 4+sub and read exactly five bytes, ending within byte 19.
Each constant subframe case uses byte shifts/masks rather than variable
multiword shifts. This private map requires the existing public validation
of a complete 20-byte mode-3 packet. Generic reader APIs and their partial/
sticky-overflow behavior remain unchanged.

Excitation's four indices occupy scratch offset 20, reused later for LPCs.
WB reconstructs them into dead interpolated-angle storage and consumes them
synchronously. Set the final bit cursor before excitation, releasing its
pointer from the hot loop. No extra static RAM, arithmetic changes or ASM.
The same reader works with both backends and the exported portable C library.

24 measured variants cover variable shifts, constant cases, byte formulas,
inline/outlined calls, scratch/stack, alias qualifiers, scope, local copies,
32-bit value arguments and cursor lifetime. Qualifiers/scope alone produced
identical C binaries. A four-byte local copy made the C arithmetic routines
faster; value arguments were slower despite a smaller low-first C variant.
The selected reader is outlined O2; O3 produced identical instructions and
inline was slower/larger. Retain C-local arrays and direct ASM scratch access.

| Full 31-stream NB corpus | Before | After |
| --- | ---: | ---: |
| ASM mean cycles | 109,985.618 | 109,035.092 (-0.8642%) |
| ASM maximum cycles | 117,927 | 117,146 |
| ASM Flash / peak stack | 10,872 / 154 B | 10,544 / 149 B |
| C mean cycles | 221,193.812 | 220,828.306 (-0.1652%) |
| C maximum cycles | 233,722 | 233,195 |
| C Flash / peak stack | 11,166 / 138 B | 10,956 / 139 B |

Each matched stream minimum/mean/maximum improves; no constant saving for every
frame is claimed. Static SRAM stays 1,119 B. Both backends pass 14,278 exact
NB frames, reset/cache cases, and fresh normal/loaded 31-stream PWM: ASM +40%,
C +10% CPU reserve; zero underruns, minimum queues 74/34 and 66/54. Each of
two exported C archives matches 9,100 NB and 10,563 WB frames; 23 selection
configurations pass. The new interface passes 1,966,080 independent short-pitch
samples per backend, every pitch/gain/scale, guards, original tap rule and ABI.
Its controller timings now exclude index parsing; do not compare those unit
timings directly to the old parser-inclusive controller.

The reader itself passes 4,227,072 native groups (all twenty-bit index values
and thirteen-bit headers at all four subframes). AVR independently compares
115,712 groups per implementation, every adjacent index pair, every byte value
at every window lane, random packets, five-byte read bounds and ABI at RET.
WB shares the exact input mapping and retains compact-profile PCM. All timing
and memory evidence uses ATmega328P / AVR GCC 7.3.0 / mixed Os/O2/O3 + LTO /
AVR8js 0.21.1, not physical-board or other-CPU measurements.

`reports/subframe-*` and `tests/audit_subframes.py` bind images, source snapshots,
upstream PCM and PWM. Replay the selected decoder from db52a40 in a new directory:

```sh
python Codecs/Speex/AVR/tools/prepare_subframe_candidate.py --candidate c-copy-early --out Codecs/Speex/AVR/build/reader-replay
python Codecs/Speex/AVR/build/reader-replay/tools/build.py --avr-gcc avr-gcc --backend asm
python Codecs/Speex/AVR/build/reader-replay/tools/build.py --avr-gcc avr-gcc --backend c
python Codecs/Speex/AVR/tools/build_subframe_test.py --cc clang --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_subframe.mjs
```

The selected replay reproduced both production binaries byte-identically.
Run the previous source-bound LSP admission audit at db52a40.

## Complete validated NB prefix and exact quarter dequantization (2026-10-25)

The last generic cursor was needed only for three six-bit LSP codes and the
five-bit frame gain. After public mode/length validation, extract them from
bytes 0..3 and pass the immutable packet to the private decoder. Keep general
SpeexBits functions untouched for other users and the independent Xiph oracle.
The profile patch changes only its private nb_decode prototype; public APIs
and the vendored reference remain unchanged.

Original raw angles are `16*((i+1)*128+2*base+correction)`. Dequantize into
quarters by multiplying the inner expression by four. Signed intermediates
fit AVR's 16-bit int, including negative codebook corrections. On reset,
multiply quarters by four into raw state and use zero delta; on change,
subtract old raw quarters before excitation. Equal cached frames need no
temporary copy. No angle approximation, rounding change, filter change or
discarded coefficient step is introduced. The helper is C on both backends;
platform Flash access stays independent of arithmetic selection.

Nineteen measured variants compare original/fused/scaled loops, raw versus
quarter output, fused delta preparation, restrict, scalar linear terms,
O2/O3, inline/outlined and a loop-optimization experiment. On the 1,058-frame
fixture, the selected quarter-inline mean is 93,707.196 ASM / 191,781.372 C.
Outlined linear-O3 gives 93,708.974 / 191,815.569, with 22/64 B less Flash.
Compact delta-O2 uses 9,930 B but takes 93,885.836 ASM cycles. Restrict gives
identical binaries; disabling loop optimization is slower. The selected
inline variant wins both backends under the speed priority. Full 9,100-frame
ASM screening also retains the linear-O3 finalist. Compiler-specific
experimental attributes remain in the retained prototype, outside production.

| Full 31-stream NB corpus | Before (03fad82) | After |
| --- | ---: | ---: |
| ASM mean cycles | 109,035.092 | 107,802.983 (-1.1300%) |
| ASM maximum cycles | 117,146 | 115,817 |
| ASM Flash / peak stack | 10,544 / 149 B | 10,610 / 114 B |
| C mean cycles | 220,828.306 | 219,567.168 (-0.5711%) |
| C maximum cycles | 233,195 | 231,834 |
| C Flash / peak stack | 10,956 / 139 B | 11,078 / 105 B |

Every stream's min/mean/max improves; static SRAM stays 1,119 B. Preserve
bit-exact decoded PCM as the quality gate for these optimizations. All
8,388,608 LSP/gain combinations match untouched Xiph on the host. Another
270,336 AVR cases cover every code triple, signed correction, all gain values,
random trailing packet data, guards, read bounds and ABI/r1. Original oracle
tables live separately in RAM; production tables use real Flash reads.
Exhaustive observed raw range is 96..24,880; the production helper documents
the wider signed-byte bounds instead of relying only on observed samples.

Both backends retain 14,278 exact NB frames, reset/cache/API checks, compact
WB exactness, portable C archives and independent normal/loaded PWM tests.
Each NB matrix covers all 31 streams; minimum queues are ASM 74/34 and
C 66/55 for ordinary/loaded runs, with free SRAM 671/680 B. All 16 WB speech
players and two +5% load players retain exact PWM: queues 28/13, 432 B free.
Admission uses ATmega328P / AVR GCC 7.3.0 / mixed Os/O2/O3 + LTO / AVR8js
0.21.1. It does not establish physical-board or other-architecture timing.
See `reports/prefix-*` and `tests/audit_prefix.py`. Reproduce the selected
decoder from 03fad82 in a fresh directory:

```sh
python Codecs/Speex/AVR/tools/prepare_prefix_candidate.py --candidate quarter-inline --out Codecs/Speex/AVR/build/prefix-replay
python Codecs/Speex/AVR/build/prefix-replay/tools/build.py --avr-gcc avr-gcc --backend asm
python Codecs/Speex/AVR/build/prefix-replay/tools/build.py --avr-gcc avr-gcc --backend c
python Codecs/Speex/AVR/tools/build_prefix_test.py --cc clang --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_prefix.mjs
```

Selected candidate replay reproduces both production binaries byte-identically.
Run the preceding source-bound subframe audit at 03fad82.

## Next candidates (not yet measured/admitted)

The previously listed C40 long-pitch entry shipped in commit 9813583 and is
no longer an outstanding candidate.

1. **Share interpolated-LSP and new-LPC scratch by lifetime.** The compact
   converter appears to consume every angle before storing its LPC result.
   Inspect and test aliasing, polynomial scratch and WB callbacks before
   reusing the two twenty-byte arrays. No memory or timing gain is admitted.

2. **Specialize endpoint margin handling for validated NB3 state.** Exhaustive
   raw codebook angles stay in 96..24,880; convex quarter steps appear to make
   the endpoint clamps redundant. Preserve the general helper's signed16
   contract and test a separate bounded path, transitions/reset/cache and
   full PCM before admitting any benefit. Interior sequential margins remain.

No claim of a global speed optimum has been established. Do not mark the
ongoing optimization goal complete while useful candidates remain untested.

## Rejected or superseded experiments

- C IIR phase splits (base 098c3d9) preserve all 9,100 AVR frames and each
  passes two million native full-signed16 direct/transposed samples. The simple
  split increases corpus mean by 2.7157%; also caching two coefficients in C
  scalars increases it by 1.9606%. Both grow Flash 514 B with unchanged static
  SRAM/stack. Retain the previous C loop. No PWM admission for rejected
  candidates. Reports c-iir-phase-*.json and both cookbook patches retain
  the evidence; the successful ASM split does not predict C compiler behavior.
- Portable byte-product C MAC (base d000fc4) is exact on 1,310,720 independent
  pairs per implementation and all 9,100 decoder frames, but takes 119 versus
  69..73 standalone cycles, increases corpus mean by 34.3396% and Flash by
  1,564 B (11,836 to 13,400), with unchanged 1,119 B static / 153 B stack.
  Native C multiply remains. Reports c-byte-mac-*.json and the reproducible
  cookbook patch retain the failed experiment; no PWM admission was attempted.
- The per-sample direct short-pitch prototype (short-pitch-experiment-*)
  preserved PCM and reduced mean by 0.2238%, but some streams regressed.
  It is superseded by the range-selected ASM/C controller above. Its pinned
  C-only patch remains in docs/avr-asm-cookbook/examples for reproduction.
- The isolated rolling C40 long-pitch prototype (long-pitch-experiment-*) is
  retained as a reproducible historical patch in docs/avr-asm-cookbook/examples.
  Its O2 variant gained 5.4082% mean at +682 B Flash; O3 gained another ~1,233
  fixture-mean cycles for +2,744 B over O2. It is superseded by the shared
  production ASM/C design above. Outlined ten-sample C O3/O2 variants were
  slower than the selected inlined C40 form, which also saves 84 B vs C10 O2.
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
