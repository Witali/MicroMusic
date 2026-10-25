# Speex for AVR

An adaptation of the **original Xiph Speex 1.2.1 fixed-point decoder** for
ATmega328P at 16 MHz, with a linked PWM player and reproducible host/AVR tests.
The ASM player passes ISA simulation on all 31 streams: **9,100
frames / 1,456,000 samples, zero underruns, 691 bytes SRAM free at the observed
peak**, including a separate 40% extra-CPU admission test. A physical board
and its analog output have not been tested.

An additional [compact wideband profile](WIDEBAND.md) decodes **16 kHz /
9.8 kbit/s** (NB3 + HB1) on the same MCU. It uses a normalized 16-tap Q7
synthesis QMF; its PCM differs from full 64-tap Xiph synthesis. The NB3
profile retains exact original PCM.
The WB PWM player passes all 16 speech recordings: **6,467 frames,
2,069,440 samples, zero underruns, 452 B free SRAM at peak** in AVR simulation
with timers and interrupts active. WB playback on ATmega328P requires ASM;
the portable C fallback retains correctness but exceeds its frame deadline.

The narrowband decoder has a selectable C backend and an architecture-neutral
`speex_nb3.h` interface. Architecture defines and a separate explicit ASM
enable control selection; without a matching enabled backend it uses C.
See [PORTING.md](PORTING.md) for C fallbacks, platform headers and an exportable
CMake/static-library package for other microcontrollers. The C player now
also passes all 31 streams with timers/ISR and 10% extra CPU work: zero
underruns and 700 B free SRAM at peak. Both NB3 backends retain exact upstream s16 PCM.

## Narrowband profile

- Narrowband submode 3, mono 8 kHz, CBR 8 kbit/s.
- Exactly 20 compressed bytes produce 160 signed 16-bit samples (20 ms).
- Enhancement and highpass are disabled; all four coefficient steps are
  retained. Identical NB3 LSP indices reuse exact interpolation/LPC results;
  filter synthesis and coefficient ageing always execute. Decoded s16 PCM
  matches unmodified upstream.
- Input consists of raw packets, as in `reference/R4/data/*.spxraw`. Ogg/Speex
  containers, other submodes, WB, DTX, stereo, encoder and packet loss concealment
  are outside this profile. The API rejects wrong lengths and mode headers
  before changing state.

`src/speex_avr.h` exposes a static, non-reentrant decoder: reset with
`speex_avr_init()`, then call `speex_avr_decode(packet, 20, pcm)` for each packet.
The caller supplies space for 160 samples. No heap is used. The explicitly
four-byte-aligned 40-byte scratch arena is checked on the host;
the 305-sample excitation history is sufficient
for the restricted lossless profile (maximum backward pitch access: 145 samples).

## PWM player

`src/player.c` reads embedded packets from Flash and sends the high eight bits
of PCM, converted to unsigned samples, to **OC1A / PB1 / Arduino D9**.
Timer1 runs 8-bit fast PWM at 62.5 kHz; Timer2 CTC advances PCM at 8 kHz.
Timer divisors assume a 16 MHz CPU clock. A 128-byte ring receives each completed
40-sample subframe, so decoding and playback overlap without a second s16 frame.
Playback starts after an 80-sample prefill and drains the final sample before
returning PWM to midpoint.

The demo stops at the end of the embedded stream. The supplied `speech_ru`
fixture is historical synthesized test speech from the handoff, not a recording
of a human speaker. The 8-bit PWM conversion is separate from the exact s16
decoder comparison.

## Build and verify

Use Python 3, Clang, AVR GCC/avr-libc and Node on PATH. On this Windows checkout,
the shared tools can be enabled from the task worktree with
`. ../../build/toolchains/env.ps1` in PowerShell. Clang's native Windows build
also needs the installed Microsoft C runtime/SDK and linker.

From the task worktree root:

```sh
python Codecs/Speex/AVR/tests/verify_pcm.py --cc clang
npm --prefix Codecs/Speex/AVR ci --ignore-scripts
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend asm
node Codecs/Speex/AVR/tests/verify_avr.mjs
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend asm --player Codecs/Speex/AVR/reference/R4/data/speech_ru.spxraw
node Codecs/Speex/AVR/tests/verify_player.mjs
```

For the full player matrix (rebuilds and simulates every stream):

```sh
python Codecs/Speex/AVR/tests/verify_players.py --avr-gcc avr-gcc --node node
```

The zero-gain lifetime regression adds all 16 zero/nonzero subframe masks,
16 energy masks, changing/repeated LSPs and frame/reset transitions:

```sh
python Codecs/Speex/AVR/tests/verify_zero_pitch_cases.py --node node --backend asm
```

The private four-index reader has an independent bit-by-bit oracle, tests
partial/sticky overflow and all offsets, and checks actual AVR input-read
addresses plus guards and callee-saved/r1 registers with ASM disabled:

```sh
python Codecs/Speex/AVR/tools/build_indices_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_indices.mjs
node Codecs/Speex/AVR/tests/verify_indices.mjs --header
```

The independent zero-gain arithmetic/ABI test builds a separate AVR C worker
with ASM disabled and compares it with both assembly entries:

```sh
python Codecs/Speex/AVR/tools/build_zero_transform_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_zero_transform.mjs
```

The forty-sample fused pitch entry has an independent arithmetic, RAM/Flash
read-bound and ABI test against four rolling-ten calls and explicit C:

```sh
python Codecs/Speex/AVR/tools/build_long40_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_long40.mjs
```

The SRAM page-crossing and IIR ABI sweep uses the guarded LPC mailbox:

```sh
python Codecs/Speex/AVR/tools/build_iir_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_iir_cursor.mjs
```

Outputs are ignored under `build/`. The decoder validation firmware is
`build/profile/speex-test.{elf,hex,bin,map}`. The PWM demo is
`build/player/speex-player.{elf,hex,bin,map}`; `input.json` records its payload
hash. The matrix leaves `speech_ru` as the final demo. Player tests retain the
captured unsigned PCM as `build/player/player-pwm.u8`.

## Verified results

AVR GCC 7.3.0, `-Os -flto -fwrapv -fno-strict-aliasing`,
`-mcall-prologues -mrelax`, with function-specific
`-O3` for the controller, bit reader, cosine and polynomial stages (also C
pitch/LPC block loops), and `-O2` for the fused C excitation routines;
ATmega328P, AVR8js 0.21.1. Static SRAM includes the packet, s16 PCM, decoder state, scratch and,
for the player, PWM ring. Stack peaks are observed during actual ISR execution.

| Build | Flash | Static SRAM | Peak stack | Free SRAM at peak |
| --- | ---: | ---: | ---: | ---: |
| Optimized decoder test mailbox, ASM enabled | 10,470 B | 1,099 B | 114 B | 835 B |
| Full PWM speech demo, including 2,940 B compressed audio | 13,712 B | 1,234 B | 123 B | 691 B |
| C fallback decoder test mailbox | 10,898 B | 1,099 B | 105 B | 844 B |
| Full C PWM speech demo, including 2,940 B audio | 14,148 B | 1,234 B | 114 B | 700 B |

- All 9,100 corpus frames and 4,096 additional pitch/gain coverage frames match
  unmodified upstream s16 PCM. Including 58 LSP/reset and 1,024 zero-gain
  lifetime cases, each backend matches 14,278 frames with one firmware image.
- Complete player tests on all 31 streams match upstream PCM converted to u8,
  with zero ring underruns and no stack/static-memory collisions.
- Maximum observed ASM decoder-only corpus frame cost: **115,604 cycles / 7.225 ms**;
  the 20-ms budget at 16 MHz is 320,000 cycles. ISR and output costs are verified
  separately by the complete-player runs.
- Primitive tests cover 240,000 complete LSP conversions and 3,670,016 bit fields;
  stream tests insert invalid API calls and verify unchanged output/state.
- Quarter-step interpolation independently matches 1,573,120 native calls
  against original Xiph, including every NB3 code triple and full-signed
  multiple-of-16 transitions. Another 82,688 calls execute both implementations
  on AVR, checking its 16-bit integer promotions, raw state, guards and inputs.
- The combined packet reader passes 4,227,072 native groups (every 20-bit
  index group and 13-bit header at each subframe). Both readers also pass
  115,712 AVR groups each, with independent bit-by-bit fields, exact five-byte
  read windows, guards and ABI checks at RET.
- The complete LSP/gain prefix matches untouched Xiph dequantization for all
  8,388,608 native combinations. On AVR, all 262,144 LSP triples plus 8,192
  random cases match raw angles and gain, with separate original RAM tables,
  production Flash reads, first-four-byte bounds, guards and ABI checks.
- Another 458,752 signed multiply and 655,485 signed shift cases execute the
  actual AVR instructions and check exact results and the r1 zero-register ABI.
- Shared generic and bounded Q14 ASM entries each pass 917,504 independent
  cases; the portable C Q14 helper independently passes another 917,504
  cases. The aligned p1 core adds 655,360 independent exact cases.
  The C fallback matches the same 14,278 AVR frames. Its corpus maximum is
  233,195 cycles (233,766 with pitch coverage), excluding ISR. Complete C PWM playback now
  passes all 31 streams with 32,000 extra cycles/frame (10%), zero underruns
  and at least 54 queued samples. ASM retains the stronger 40% reserve gate.
- The historical pitch ASM independently checks 1,966,080 outputs, all signed8 gains,
  every count 0..40, write/add flags 0/1/2/255, zero gains and intact tails.
  Independent LPC tests cover 327,680 samples across in-place and separate
  input/output modes, including 211,200 clipped outputs and 137,342 wrapped
  updates; they check input preservation and guards. Innovation adds 163,840
  samples; native C checks two million LPC samples against the transposed
  recurrence.
- The fused core, packed ASM entry and C fallback each match another 673,280
  independent signed16-history/shape/scale samples, including exact pitch-clamp
  boundaries. Guard words, read-only gains/history and all AVR callee-saved
  registers plus r1 are checked at the actual kernel return. The matched
  before/after test verifies the same inputs in all three paths.
- The variable-count fused entry and C helper add 336,628 samples each over
  every count 0..10, with untouched output tails. Independent short-pitch
  controller tests add 1,966,080 samples each in ASM and C over all 24 pitches,
  32 gains and 64 scales, full signed16 history, packet/region guards, exact
  twenty-bit consumption and callee-saved registers/r1.
- The forty-sample entry checks another 72,960 blocks / 2,918,400 samples
  each in ASM40, four ASM10 calls and C, including all signed8 shapes,
  all 32 indices at every vector position, full signed16 history, scales,
  clamp boundaries at vector seams, exact RAM/Flash read addresses, guards
  and actual-return callee-saved/r1 checks. ASM40 saves exactly 450 cycles
  against four rolling-ten calls in every tested block. The legacy variable
  entry now takes two fewer cycles per sample and one per repeated iteration;
  its one-sample/scalar timing difference is 35 cycles rather than 37.
- Exported C archives built from the source manifest and through CMake each
  match all 9,100 corpus frames on the native host using only the public API.
- The bounded zero-gain transform checks 280,960 samples each in ASM,
  explicitly selected AVR C and the older packed kernel, including every
  signed8 shape, scale boundaries and exact rounding ties with +/-1 neighbors.
  Its ASM ten-sample call takes 501 cycles, versus 941..981 for packed zeros;
  the separate O2 C worker takes 549. Production C uses the faster O3 wrapper.
- The count 0..10 zero entry and explicit C helper add 140,471 samples each,
  with untouched output tails, all callee-saved registers/r1 and guards checked.
  Count zero returns in six ASM cycles; count ten adds four cycles to fixed-ten.
  Short-tail ASM improves every isolated pitch mean; the previous C controller
  is retained because the faster isolated C alternatives slowed the full decoder.
- The IIR pointer-end check matches another 655,360 samples over all 256 SRAM
  state-base low bytes, including page crossings, in-place and separate I/O,
  changing coefficients, saturation/wrap, guards and all callee-saved registers.
  It saves exactly 43 cycles/call (172/frame) with 2 B less Flash.
- Separate ten-sample coefficient ageing and thirty-sample steady IIR loops
  reuse the dead den/base registers for two coefficient words. The same full
  address/I/O/ABI sweep saves exactly 221 more cycles/call (884/frame).
  Corpus mean falls 0.7491%, human speech 0.7361%, with 570 B additional Flash
  and unchanged SRAM/stack. Both complete PWM scenarios retain zero underruns.
- The grouped index reader matches 288,768 indices per implementation on AVR:
  all offsets, every adjacent pair of 5-bit values, partial/sticky overflow,
  read addresses, read-only data/metadata, output guards and GNU ABI/r1.
  Valid NB3 groups use three bytes and two overlapping 16-bit windows.
  All 31 stream means improve: ASM 1.0228%, C 0.8087%; Flash grows 232/248 B
  for decoder mailboxes. Static SRAM is unchanged; ASM stack grows 4 B,
  C stack is unchanged. Generic single-field semantics remain intact.
- The grouped pitch/gain/energy header adds 109,568 blocks / 328,704 fields
  per implementation: all 8,192 headers at every offset, partial/sticky
  overflow, input-read addresses, guards, metadata and GNU ABI/r1. Inlining
  its single production call site is faster and smaller than an outlined
  function in both measured backends. Corpus means fall another 1.0891% ASM /
  0.5391% C, Flash grows 220/224 B, static SRAM and peak stacks are unchanged.
- Shared compiler prologues/epilogues and linker relaxation then save 472 B
  ASM / 438 B C decoder Flash. On the complete 31-stream corpus, ASM mean
  time increases 0.5860% (about 42 microseconds/frame); C mean time falls
  2.2345%. Every measured ASM stream-mean increase is below 0.633%.
  Static SRAM is unchanged; decoder stack grows 13 B, player stack 11 B.
  Normal and loaded PWM retain exact output and zero underruns, including
  +40% ASM / +10% C CPU load. These AVR-only build flags leave the C sources,
  manual ASM kernels, backend selection and portable export unchanged.
- The next ASM stage processes four long-pitch vectors in one call, retaining
  gains and rolling history. It also lets the older rolling dot fall through
  into the transform and shortens the common rolling tail. Decoder mean time
  falls 1.4125% (human speech 1.4098%), Flash grows 458 B, static SRAM and
  global stack peaks are unchanged. Corpus maximum falls 122,498→122,066
  cycles; pitch coverage maximum falls 122,970→122,570. The largest stream
  mean regression is 0.0056%. The compact shared-machine-body candidate was
  304 B smaller but slower; the faster candidate follows the speed priority.
  Both arithmetic bodies use common GAS source macros. C remains explicitly
  selectable, with the same decoder and all 62 normal/loaded player binaries.
- Codebooks reside in Flash, use explicit signed `pgm_read_*` accesses, and no
  malloc/calloc/realloc/free symbols are linked.

The current LSP stage reuses one twenty-byte array for interpolated angles
and new LPC coefficients: the converter consumes every angle before its first
coefficient store. WB reads the copied coefficients before reusing that same
array for synchronous indices. Scratch falls 60 -> 40 B; C and ASM preserve
the same arithmetic and portable interface.

All 262,144 NB3 code triples produce raw angles in 96..24,880. Reset initializes
real endpoints; each exact quarter step is a convex interpolation between
them. The endpoint clamps at 16 and 25,720 therefore cannot change a value.
A private validated C path omits those checks, while the general signed16
helper and all interior sequential margins remain available and tested.

Against 928d18e, ASM mean falls 107,802.983 -> 107,616.507 (-0.1730%), C
219,567.168 -> 219,310.511 (-0.1169%); every stream min/mean/max improves.
Flash falls 140/180 B and static SRAM falls 20 B, with unchanged decoder stack.
Additional pitch coverage reaches 116,142 ASM / 232,118 C cycles.
Independent tests cover 1,572,880 native bounded calls and 720,000 overlapping
LPC outputs. Each AVR backend adds 49,680 bounded calls and 12,288 overlapping
outputs, original Xiph reference, raw state, memory guards and ABI at RET.
The general helper still passes 82,688 AVR calls including full-signed
multiple-of-16 endpoints. No decoded PCM sample changes.
All four 31-stream NB PWM matrices pass, including +40% ASM / +10% C CPU
reserve, with unchanged minimum queues 74/34 and 66/55; free SRAM 691/700 B.
The instrumented native decoder separately checks every scratch PUSH on all
9,100 corpus frames and reports a 40-byte peak, with exact PCM.
`reports/lifetime-*.json` and `tests/audit_lsp_lifetime.py --rebuild --avr-gcc avr-gcc`
bind full corpus, portable archives, IRQ/PWM images and fresh representative
rebuilds. Candidate sources/replay are retained in OPTIMIZATION.md.

The preceding complete packet map decodes LSP and frame gain directly
from bytes 0..3. Pure C dequantizes LSP into exact quarter units, retaining
the original rounding, all four interpolation steps and the raw cache key.
Reset initializes raw state; changed frames subtract old quarters; repeated
frames skip the unused angle copy. The private decoder accepts the validated
packet directly, eliminating its remaining SpeexBits object and initialization.
Public APIs, generic bit-reader behavior and arithmetic backend selection
remain unchanged. This optimization introduces no PCM difference: NB remains
bit-exact to original Xiph; WB remains bit-exact to the existing compact profile.

Against 03fad82, NB mean cycles fall 109,035.092 -> 107,802.983 (-1.1300%)
for ASM and 220,828.306 -> 219,567.168 (-0.5711%) for C. Each stream's minimum,
mean and maximum improve. Decoder Flash grows 66/122 B; stack falls 35/34 B.
The smallest outlined variants were slower, so the single-callsite inline
quarter decoder follows the speed priority. Nineteen measured candidates and
their source payloads are retained in `reports/prefix-candidates.json`.
Additional pitch coverage reaches 116,355 ASM / 232,407 C cycles.
All four fresh 31-stream PWM matrices pass: minimum queues ASM 74/34,
C 66/55, with zero underruns at ordinary / +40% ASM or +10% C load.
Player free SRAM is 671/680 B, an additional 33/32 B over the preceding stage.
`reports/prefix-*.json` and `tests/audit_prefix.py --rebuild --avr-gcc avr-gcc`
bind the final sources, exact PCM, frozen IRQ/PWM images and representative
rebuilds. Historical source-bound audits should run at their recorded commits.

The preceding reader stage combines each 13-bit header and twenty index bits
in one outlined C helper, using four fixed byte slices after full packet
validation. Four index bytes reuse the existing scratch at offset 20 during
excitation. WB reuses dead interpolated-angle storage for its synchronous
callback, eliminating a second local SpeexBits cursor. Set the final cursor
once before excitation so its pointer no longer occupies registers in that loop.
The C arithmetic controllers retain a measured faster local copy of four
indices; ASM consumes the scratch indices directly. Generic partial reads and
sticky-overflow semantics are unchanged.

The 31-stream mean falls 109,985.618 -> 109,035.092 cycles (0.8642%) for ASM
and 221,193.812 -> 220,828.306 (0.1652%) for C. Each stream's minimum, mean
and maximum improve. Flash falls 328/210 B, static SRAM stays unchanged,
ASM stack falls 5 B and C stack grows 1 B. All four fresh NB PWM matrices
pass: minimum queues ASM 74/34, C 66/54; free SRAM 638/648 B. Additional
pitch coverage reaches 117,682 ASM cycles. That stage's evidence is
`reports/subframe-*.json`; `tests/audit_subframes.py --rebuild --avr-gcc avr-gcc`
binds 142 frozen PWM images and representative rebuilds to sources and PCM.
It does not rerun all corpus simulations. Candidate sources and decoder-only
replay commands are retained in OPTIMIZATION.md and the candidate report.

The preceding LSP stage computes an exact quarter-frame delta once and advances
the existing raw LSP state in an outlined C helper. Fusing advancement and the
sequential margin pass avoids a temporary store/reload pass and the final
endpoint copy. It preserves the two original half-shifts, reset/cache behavior
and all four raw/output interpolation states. Both arithmetic backends use C
for this helper. The 31-stream weighted mean falls 113,264.523 -> 109,985.618
(2.8949%) for ASM and 232,365.300 -> 221,193.812 (4.8077%) for C. Each stream's
mean and maximum improve. Static SRAM is unchanged; mailbox stack peaks fall
4 B and 28 B respectively. All four normal/loaded NB player matrices are fresh
simulations: minimum queues ASM 74/33, C 66/54; free SRAM 633/649 B.
The additional 4,096-frame pitch corpus reaches 118,435 ASM cycles.

Previous-stage results are `reports/lsp-quarter-*.json`. That audit binds 142 frozen
NB/WB player images, both decoder backends and representative byte-identical
rebuilds. The candidate report retains 26 measured variants and replayable
sources. `tests/audit_lsp_quarters.py --rebuild --avr-gcc avr-gcc` checks the
retained artifacts; it does not claim to rerun every full corpus simulation.

The preceding IIR stage reuses the dead state-base register pair for a third
coefficient after ageing completes. Fixed X/Y rewinds replace base-pointer
reconstruction. Every matched stream minimum/mean/maximum saves 444 cycles/frame;
the 31-stream weighted mean falls 113,708.523 -> 113,264.523 (0.3905%). Flash
grows two bytes; SRAM, stack and all 14,278 PCM frames remain unchanged.
The separate 4,096-frame pitch maximum is 122,126 cycles. Both 31-stream
normal/+40% PWM matrices pass, with minimum queues 74/33 and 629 B free.
The shared order-eight kernel also saves 118 cycles/block; the compact WB
decoder saves 916 cycles/frame with its NB and HB filters combined. Both C
decoder binaries are byte-identical to their preceding admitted images.

Previous-stage ASM results: `reports/iir-cache3-*.json`; that audit binds 80 frozen
NB/WB player images and byte-identical representative rebuilds. The preceding
ASM stage remains in `reports/long40-asm-*.json`. Prior C runtime results remain
`reports/shared-routines-c-*.json`. Fresh portable results:
`reports/iir-cache3-portable.json`. The preceding `reports/long40-admission-audit.json`
pins five 92-file source copies, measured decoder/demo/unit images, full
normal/+40% ASM PWM and fresh native PCM/two-library checks. Both C player
scenarios were rebuilt for every stream and proved byte-identical to the
previous full PWM runs; `long40-c-*-image-reuse.json` records that reuse,
without claiming a fresh C PWM simulation. The same C decoder image retains
the prior 14,278-frame evidence. `long40-variant-decision.json` compares four
full-corpus candidates; alternative patches are in the AVR cookbook.
`reports/shared-routines-admission-audit.json` retains the preceding image,
its four 88-file source copies and complete normal/loaded PWM evidence.

Reproduce the latest corpus/player checks after preparing the retained speech
and original host reference:

```sh
python Codecs/Speex/AVR/tests/prepare_nb.py --out Codecs/Speex/AVR/build/cache3-corpus
python Codecs/Speex/AVR/tests/verify_nb_players.py --avr-gcc avr-gcc --node node --backend asm --streams Codecs/Speex/AVR/build/cache3-corpus/streams --out Codecs/Speex/AVR/build/lifetime-nb-asm-normal
python Codecs/Speex/AVR/tests/verify_nb_players.py --avr-gcc avr-gcc --node node --backend asm --streams Codecs/Speex/AVR/build/cache3-corpus/streams --out Codecs/Speex/AVR/build/lifetime-nb-asm-load40 --frame-load-cycles 128000
python Codecs/Speex/AVR/tests/verify_nb_players.py --avr-gcc avr-gcc --node node --backend c --streams Codecs/Speex/AVR/build/cache3-corpus/streams --out Codecs/Speex/AVR/build/lifetime-nb-c-normal
python Codecs/Speex/AVR/tests/verify_nb_players.py --avr-gcc avr-gcc --node node --backend c --streams Codecs/Speex/AVR/build/cache3-corpus/streams --out Codecs/Speex/AVR/build/lifetime-nb-c-load10 --frame-load-cycles 32000
```

Run the matrices sequentially in one source directory: their builder shares
`build/profile` and `build/player`. Separate immutable source copies allow
parallel runs. Each matrix retains its source hashes and every executed ELF,
HEX, binary, PCM/PWM and verification report.

`shared-routines-variant-decision.json`
records the comparisons: outlining the sample finish was rejected after
88-frame screening (+2.0863% / +3.2449% C mean time). Those prototypes have
no full-corpus/component/PWM admission. Their patches are in the AVR cookbook.
`reports/nb3-header-admission-audit.json` retains the preceding image, both
C-only reader pairs and read-address checks. The `nb3-indices-*` reports retain
the preceding admitted image. Rejected C
experiments and their full-workload regressions remain `reports/short-tail-c-*.json`
and `reports/c-byte-mac-*.json`, `reports/c-iir-phase-*.json`. The byte-product
C MAC and C IIR phase splits were exact but slower; their reproducible patches
are retained in the AVR cookbook. The `iir-phases-*` reports retain the
preceding ASM image and historical byte-identical C-image proof.
The earlier `segment-*`, `register-*`, `shared-bias-*` and `fused-long-*` results remain historical.
The `phase-reuse-*` reports retain the preceding admitted image.
The `nb-word-math-*` and `c-word-math-*` reports are the preceding baselines.
The earlier `nb-p1-*`, `nb-loop-hoist-*`, `nb-round5-*`, `nb-round4-*`, `nb-round3-*`, `nb-round2-*`, `nb-final-*` and
`nb-optimization-summary.json` reports remain historical baselines.
These are corpus maxima and ISA simulation results,
not exhaustive packet timing proofs or physical board measurements.
`reports/avr-initial.json` preserves the initial 547,940-cycle port for comparison.
`reports/avr-optimized.json`, `reports/player-all.json` and the original
`reports/real-speech-{avr,player}.json` retain the earlier NB baseline.
`node Codecs/Speex/AVR/tests/verify_avr.mjs --frames 8 --profile` also writes `avr-profile.json`
under the selected output directory. It counts only frame-command intervals,
excluding boot/reset; the recorded long40-stage 88-frame fixture profile spends 57.5% in
LPC synthesis and 16.0% in its forty-sample pitch/innovation ASM body
(`reports/long40-asm-profile.json`). Separate variable-entry/controller costs
are also recorded there. The older common
body is attributed to its second symbol for its overlapping entries. These shares describe
that sampled workload, not every possible packet.

## Further exact NB optimization

The Xiph NB3 adaptation has the following separately measured stages:

| Step | Maximum decoder cycles on the 1,058-frame fixture corpus | Decoder Flash | Static SRAM |
| --- | ---: | ---: | ---: |
| Previous exact NB baseline | 295,334 | 14,712 B | 1,535 B |
| Fuse innovation and final excitation; remove intermediate | 289,878 | 14,620 B | 1,375 B |
| Return inline ASM products in a single 32-bit operand | 279,557 | 13,422 B | 1,375 B |
| Replace constant fixed-point shift loops with byte-aware ASM | 207,602 | 14,874 B | 1,375 B |
| Use postincrement stores in the LPC state update | 204,722 | 14,856 B | 1,375 B |
| Left-aligned shifts and narrow intermediate words | 196,489 | 13,916 B | 1,375 B |
| Exact direct LPC with coefficient ages, whole-block ASM | 177,365 | 13,838 B | 1,395 B |
| Constant LSP stages, shared stage/cosine subroutines | 167,193 | 14,836 B | 1,395 B |
| Signed-byte innovation vector subroutine | 154,436 | 14,706 B | 1,395 B |
| Minimal state/history/scratch, merged LPC carry chain | 150,965 | 11,446 B | 1,279 B |
| First pitch tap writes instead of adding to cleared memory | 145,789 | 11,456 B | 1,279 B |
| Compact cold code, hot function-specific optimization | 146,632 | 9,726 B | 1,279 B |
| Exact finite gain-pair table | 146,234 | 9,576 B | 1,279 B |
| Exact LSP-key reuse, shared Q14, folded first stage, zero-pitch paths | 146,384 | 8,684 B | 1,279 B |
| Value-only Q14 declarations | 146,072 | 8,788 B | 1,279 B |
| Signed24 final LPC/innovation clamps | 145,098 | 8,770 B | 1,279 B |
| Two-MUL signed-byte pitch gain | 143,106 | 8,764 B | 1,279 B |
| Invariant pitch mode in SREG.T | 142,602 | 8,764 B | 1,279 B |
| Packed unscaled signed24 pitch | 134,258 | 8,572 B | 1,239 B |
| Reuse the LPC dot-product end pointer | 133,938 | 8,568 B | 1,239 B |
| Select full pitch spans before the tap loop | 133,938 | 8,662 B | 1,239 B |
| Six-MUL Q14 for the p1 polynomial coefficient | 133,650 | 8,750 B | 1,239 B |
| One LPC rounding constant per block | 133,514 | 8,756 B | 1,239 B |
| Persistent LPC history cursor with postincrement stores | 133,054 | 8,754 B | 1,239 B |
| Filter directly from delayed excitation | 130,369 | 8,750 B | 1,239 B |
| Reuse dead pitch workspace for synthesis arrays | 130,361 | 8,742 B | 1,199 B |
| Fuse long pitch with shared innovation and isolate zero gain | 130,397 | 9,078 B | 1,199 B |
| Retire fused history words before their replacements | 130,397 | 9,068 B | 1,199 B |
| Hold the shared innovation bias once per block | 130,333 | 9,076 B | 1,199 B |
| Fuse short pitch over preselected history ranges | 125,587 | 9,300 B | 1,199 B |
| Reuse one zero vector and reduce scratch to 60 B | 125,613 | 9,306 B | 1,119 B |
| Use a scalar entry for one-sample pitch segments | 125,373 | 9,460 B | 1,119 B |
| Round known-zero adaptive gain directly, without a packed vector | 125,338 | 9,578 B | 1,119 B |
| Send short-pitch zero tails to the bounded variable-count entry | 125,124 | 9,602 B | 1,119 B |
| Compare IIR cursor low byte against a hoisted end byte | 124,952 | 9,600 B | 1,119 B |
| Split IIR ageing/steady phases and cache two coefficient words | 124,068 | 10,170 B | 1,119 B |
| Read four innovation indices as one bounded group | 122,875 | 10,402 B | 1,119 B |
| Read pitch/gain/energy together through one inline C helper | 121,608 | 10,622 B | 1,119 B |
| Share register saves/restores and relax AVR transfers | 122,365 | 10,150 B | 1,119 B |
| One long-pitch subframe call and a shorter rolling loop | 121,939 | 10,608 B | 1,119 B |
| Cache a third IIR coefficient in a dead base-pointer pair | 121,495 | 10,610 B | 1,119 B |
| Accumulate quarter-step LSP and fuse the margin pass | 117,800 | 10,872 B | 1,119 B |
| Combine each validated subframe packet group | 117,031 | 10,544 B | 1,119 B |
| Decode the complete prefix in exact quarter units | 115,702 | 10,610 B | 1,119 B |
| Reuse LSP/LPC scratch and omit redundant endpoint checks | 115,489 | 10,470 B | 1,099 B |

Through the persistent-history stage, the combined corpus maximum fell from 204,770 to
133,142 cycles: **34.98% less decoder time**. The latest p1-specific ASM core
uses six hardware multiplies instead of eight: **65 -> 53 kernel cycles**,
up to 288 cycles/frame saved, weighted corpus mean **-0.198%**, human speech
**-0.207%**. It costs 88 B Flash and no RAM/stack; other coefficients retain
the generic bounded kernel. Two LPC loop changes save another 596 cycles
on every frame. The combined ASM series reduces the corpus mean by
**0.6619%** at 92 B extra Flash and no RAM/global-stack cost. C still uses
exact generic Q14 arithmetic.
The preceding loop changes reduced the mean by 0.6672%; the packed-pitch
stage saved another 5.90%, 192 B Flash, 40 B static SRAM and 4 B stack.
Three portable C arithmetic changes at that stage reduce its mean by **13.73%**
and maximum from 315,375 to 272,281 cycles, at 80 B additional Flash and no
RAM/stack cost. Both backends preserve all PCM and captured PWM hashes.
The direct-input/workspace series then removes a 320-byte frame copy and
saves another 40 B static SRAM. Against the preceding admitted image, weighted
corpus mean falls **2.0941% for ASM / 0.9502% for C**, with corpus maxima
130,449 / 269,797 cycles. ASM Flash falls 12 B, C grows 14 B; stack changes
by -2 / +2 B. LPC reads excitation directly without changing its 40-sample
delay. During synthesis the dead pitch buffer holds separate LPC and LSP
arrays; the quantized LSP remains live in disjoint storage.
Long-pitch fusion then removes the packed intermediate for nonzero pitch>=41.
The ASM entries share one scaling/clamp/output body; C inlines the same vector
arithmetic into an O2 forty-sample subroutine. Gain code zero clears once,
while short nonzero pitch keeps the original segments and zero tails. This
reduces weighted corpus mean by **4.1057% ASM / 5.3352% C**, with +336/+618 B
Flash and unchanged static RAM/peak stack. ASM worst corpus frame rises just
36 cycles to 130,485; C falls 141 cycles to 269,656. The mean gain does not
represent a worst-frame reduction. Every stream mean improves, and all PCM
and PWM hashes remain exact.
Retiring history words earlier removes one MOVW per fused sample and two
register-save pairs. A freed register then holds the shared rounding bias.
The combined series saves 64 cycles on every frame plus 72 per fused
subframe, reducing corpus mean another **0.2402%** and maximum by 64 cycles.
Flash shrinks 2 B overall; RAM/global peak stack stay unchanged. At that stage the C image
was byte-identical to its admitted build. Both ordinary and 40%-load ASM
players retain the complete corpus, exact PWM and zero underruns.
Range-selected short pitch then moves segment/tail decisions outside each
sample loop. The two contiguous ranges use the shared rolling kernel;
ASM stages isolated boundary samples, while C forms those sums directly.
The zero-gain path is selected first. Weighted corpus mean falls another
**0.7430% ASM / 1.1065% C**, maxima to **125,587 / 254,742 cycles**;
Flash grows 224 / 1,000 B, RAM and peak stack stay unchanged. The largest
ASM stream-mean regression is 0.0055%; C improves every stream mean. Complete
ordinary and loaded PWM still match upstream without underruns. Under load,
minimum queues rise to 31 / 49; ordinary C retains 65 samples and its largest
publication gap falls to 124,895 cycles. The retained 120-byte packed area
now serves only zero gain; reclaiming that workspace is a next candidate.
Decoder timings exclude ISR;
complete players include timers, interrupts and ring-buffer backpressure.
The sample rate, frame length, four coefficient steps and arithmetic remain exact.

Repeated expensive operations are shared subroutines. Outlining cosine and
constant LSP stages saved 5,278 B for 0.78% additional decoder cycles in that
stage. The selected compiler mix saved another 1,730 B and 45 B of stack for
0.58% additional cycles. Both tradeoffs preserve the user's priority on speed
while accepting small costs for substantial code-size savings.

The direct LPC state preserves coefficient ages: its first ten samples after
a coefficient change reproduce the transposed upstream filter. A plain
history dot product with all-new coefficients would be incorrect. Scratch
requires explicit four-byte alignment on AVR; decoder and player tests assert
the linked address, since a differently ordered BSS previously exposed a
2-byte arena overrun. The 145-sample history bound includes pitch+1 reads.

To reproduce the standalone arithmetic tests:

```sh
python Codecs/Speex/AVR/tools/build_math_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_math.mjs
python Codecs/Speex/AVR/tools/build_iir_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_iir.mjs
python Codecs/Speex/AVR/tools/build_pitch_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_pitch.mjs
python Codecs/Speex/AVR/tools/build_long_pitch_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_long_pitch.mjs
python Codecs/Speex/AVR/tools/build_short_pitch_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_short_pitch.mjs
python Codecs/Speex/AVR/tests/verify_pitch_cases.py --node node
```

Stage reports are `reports/nb-{fused-excitation,multiply,byte-shifts,lpc-postincrement}.json`.
The reusable recipes and exact ASM sources are linked from
[`docs/avr-asm-cookbook`](../../../docs/avr-asm-cookbook/README.md).

## Explicit 40% CPU-reserve gate

The complete player passes **128,000 extra foreground instruction cycles /
8 ms in every 20-ms frame**, reserving at least 40% CPU time for other work.
Interrupts remain enabled; the ISA verifier independently counts the marked
load instructions, excluding ISR and function-call overhead.

All 31 streams / 9,100 frames passed with exact PWM hashes, zero underruns,
9,100 measured loads, at least **31 queued samples under load** and **564 B
free SRAM** at peak. The ordinary firmware is rebuilt and separately verified
without test-load instructions. This measures admission for the corpus,
embedded Flash transport and tested timer/ISR workload. Physical hardware and
additional application interrupts need their own measurements.

After collecting the original 11 and human-speech 20 `.spxraw` files in the
ignored `build/nb-all-streams` directory, reproduce with:

```sh
python Codecs/Speex/AVR/tests/verify_players.py --avr-gcc avr-gcc --node node --streams Codecs/Speex/AVR/build/nb-all-streams --out Codecs/Speex/AVR/build/segment-final-headroom40 --frame-load-cycles 128000
python Codecs/Speex/AVR/tools/verify_nb_headroom.py --report Codecs/Speex/AVR/build/segment-final-headroom40/player-all.json --reserve-percent 40 --out Codecs/Speex/AVR/build/segment-final-headroom-summary.json
```

Omit the frame-load option to restore ordinary firmware. The full matrix and
compact audit are retained in `reports/segment-asm-headroom40.json` and
`reports/segment-asm-headroom-summary.json`. The previous 20% gate reports remain
as historical evidence.

## Human speech and PWM headroom

The expanded corpus contains 20 eight-second clips: eight human speakers
(four Russian, four English; two male and two female voices per language),
16 natural excerpts plus two attenuated by 24 dB and two with seeded white
noise at 15 dB SNR. Source pages, speaker/author credits, licenses, changes and
SHA-256 hashes are retained in `tests/real-speech-sources.json` and
`reports/real-speech-corpus.json`. Audio stays in ignored build output.

At the historical segmented-pitch stage, all **8,042 frames / 1,286,720 samples** matched unmodified upstream s16 PCM on
the AVR ISA simulator. Every full player run, with both timers and interrupts,
also matches the expected PWM duties, with **zero underruns**. Worst observed
human-speech decoder frame then was 125,560 cycles (7.848 ms). That stage's queue and publication-gap
measurements are in `reports/segment-asm-summary.json`; load-test queue and gaps
are in `reports/segment-asm-headroom-summary.json` (at least 31 samples queued).
Ordinary playback retains at least 73 samples; the maximum block-ready gap
is 80,013 cycles (5.001 ms).
Full-player SRAM/stack then were 1,334/150 B, leaving 564 B.
The current image and bounds are listed in Verified results above.
These are observed corpus bounds on the simulated ISA and
peripherals; physical playback and other interrupt workloads need measurement.

The aligned natural-speech STOI mean is 0.9016 for decoded s16 and 0.8373 for
the 8-bit PWM duties. At -24 dB it is 0.8976 / 0.5190: quiet input exposes
the separate 8-bit quantization limit. These are intelligibility estimates,
not MOS, percentages of correctly recognized words or a subjective listening
test. No gain normalization is applied. Delay is measured and removed only
for comparison; the complete AVR timing tests include all decoded samples.

To reproduce (FFmpeg with libspeex is required):

```sh
python Codecs/Speex/AVR/tools/prepare_real_speech.py
python Codecs/Speex/AVR/tests/verify_players.py --avr-gcc avr-gcc --node node --streams Codecs/Speex/AVR/build/real-speech/streams --out Codecs/Speex/AVR/build/real-speech/player
```

Decode each raw stream with `build/reference/decode` into
`build/real-speech/oracle/<stem>.pcm`, build the decoder test firmware, then:

```sh
node Codecs/Speex/AVR/tests/verify_avr.mjs --streams Codecs/Speex/AVR/build/real-speech/streams --oracle Codecs/Speex/AVR/build/real-speech/oracle --out Codecs/Speex/AVR/build/real-speech/avr --capture
python -m pip install -r Codecs/Speex/AVR/tests/requirements-quality.txt
python Codecs/Speex/AVR/tools/analyze_real_speech.py
```

`build/real-speech/index.html` provides original excerpts, 8-kHz encoder input,
AVR-decoded s16 and captured PWM side by side. WAVs represent the simulated
digital signal, without the board's analog output filter/noise. Full measurements
are in `reports/real-speech-{avr,player,quality}.json`.

## Native 16/32-kHz memory experiment

The full 64-tap Speex WB (16 kHz) and UWB (32 kHz) implementations below remain
experimental PC builds. The separate [compact WB1 profile](WIDEBAND.md) adds
16-kHz AVR playback with a measured quality/speed tradeoff. No 22.05-kHz output
profile is introduced. Both retain high-band information from the packet.

`tools/build_rates.py --memory` applies three changes to a disposable upstream
copy, without changing the working NB3 player:

- QMF history uses dense 32-sample rings instead of 64 slots with only odd
  slots used: **128 bytes saved per high-band layer**.
- An in-place perfect shuffle precedes causal QMF synthesis, eliminating
  the two temporary arrays: **768 bytes at 16 kHz / 1,408 bytes at 32 kHz**.
  Signed 17-bit low/high sums retain carries and exact modulo-32 arithmetic.
- The high-band excitation scratch array is allocated once per frame and
  reused across four subframes: **480 / 960 bytes of scratch growth avoided**.
  Symmetric bounded LSP half-polynomials support LPC orders 8 and 10 using
  48 bytes of local arrays, replacing upstream scratch matrices.

These savings describe individual components; they are not a measured total
SRAM footprint of a complete AVR WB/UWB player. The PC experiment still uses
upstream allocation/API and its default scratch arena. It is not linked into
the 2-KB production decoder.

All 32 native-rate natural-speech streams match untouched upstream fixed-point
PCM, including both QMF layers in UWB. Another 480,000 complete upstream LSP
comparisons exercise both orders. A separate AVR GCC machine-code benchmark
matches the original QMF on full-scale DC, opposing extrema, silence and
random frames with persistent history. Its measured costs are:

| Isolated QMF layer | Maximum cycles | Time at 16 MHz | Frame budget |
| --- | ---: | ---: | ---: |
| 8→16 kHz | 1,452,772 | 90.798 ms | 20 ms |
| 16→32 kHz | 2,909,131 | 181.821 ms | 20 ms |

This is a memory-focused implementation and not a speed limit for all possible
implementations. It currently fails the real-time requirement even before
adding CELP decoding, packet transport, output and interrupts. UWB also needs
the inner WB synthesis layer. A larger buffer cannot compensate for a sustained
production rate below consumption. These full-filter implementations cannot be
enabled in the AVR player. The compact WB1 implementation makes a separate,
explicit filter approximation; UWB playback remains unsupported.

Reproduce after preparing real speech:

```sh
python Codecs/Speex/AVR/tools/build_rates.py --cc clang
python Codecs/Speex/AVR/tools/build_rates.py --cc clang --memory
python Codecs/Speex/AVR/tests/verify_rates.py
python Codecs/Speex/AVR/tools/build_qmf_bench.py --cc clang --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_qmf.mjs
python Codecs/Speex/AVR/tools/analyze_real_speech.py --rates
python Codecs/Speex/AVR/tools/package_comparison.py
```

The gallery and `build/real-speech/speex-listening.zip` include original,
decoded/PWM 8-kHz recordings and **PC-reference** native 16/32-kHz examples,
with source credits. See `reports/wideband-pcm.json`,
`reports/wideband-qmf-avr.json` and `reports/native-rates-quality.json`.

## Sources and provenance

`vendor/speex-1.2.1` contains unmodified release source/header files, their BSD
license, and `UPSTREAM.json` hashes. The official release tarball SHA-256 is
`4b44d4f2b38a370a2d98a78329fefc56a0cf93d1c1be70029217baae6628feea`.
Builds patch disposable copies; every build verifies vendor and handoff hashes.

`handoff/upstream` contains the previous agent's unmodified patch candidates
and tests. `reference/R4` retains the earlier custom decoder and input streams
byte for byte. It is a regression reference, distinct from this upstream port.
`handoff/import-manifest.json` records the supplied archive and imported files.
Historical notes describe their original state; the remaining historical stages
and generated files stay in the external ZIP.

The active adaptation uses exact symmetric 48-byte LSP polynomials, fused
innovation scaling, a bounded field reader and AVR assembly for pitch MACs and
whole-block direct LPC synthesis with coefficient ages. The earlier R4-based
transposed kernel remains in `src/lpc_update.S` for reference; it is no longer
linked into the player. The active block/vector kernels are in `lpc_dot.S`,
`innovation.S`, with the range controller in `short_pitch.h`. `pitch_add.S`
and its C fallback in `pitch24.h` remain historical/tested kernels; the current
nonzero excitation path uses fused products. Vendor and R4 sources remain intact.
