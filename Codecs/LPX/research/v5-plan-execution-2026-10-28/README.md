# v5 plan execution: exact decoder and application reductions

The corrected decoder baseline is `b8f473a6` (complete-packet EOF guard).
The campaign is in progress. Local screens do not establish final corpus or
real-time support; the final combination must pass the complete plan matrix.
Private streams, recording identities/fingerprints, generated firmware and
full binding receipts stay in ignored build storage.

## Byte LSF storage and direct cosine nodes

Only the explicit v5-only layout stores two ten-element vectors as bytes.
A stored value Q is the existing quantized index plus one; zero still means
untouched state. This preserves the distinction between zero initialization
and the nonzero center of the first grid bin. The common decoder keeps its
centered signed16 representation and existing formats.

The storage-only experiment reconstructs exactly the old centered values.
For segments1/2, reachable conversion anchors have u=t/8 in {0,1,2}. Their
index into the existing even-node table is
`(P*(2-u)+C*u-1) * (profile4 ? 2 : 1)` for stored P,C. This factors the same
integer normalization, with no added quantization or table approximation.
The byte is enough: all initialized inputs are1..32 or1..64, and resulting
indices are2..126 or1..127. The four-segment path reconstructs centered
values and retains full normalization for its quarter anchors. Conversion
is reached only after a complete valid initial spectrum; failed parses stop
before conversion. Reset and partial-error traces normalize private storage
back to semantic centered values; their frozen digests remain unchanged.

Eight fixed linked AVR images cover profiles4/6, four single-reset and four
multiple-reset chains, short/long inputs, expensive conversion windows and
low data density. All use ATmega328P, AVR-GCC7.3.0,16MHz/8kHz,
`-Os -flto -mcall-prologues -mrelax`, LPC segments2, unroll1/tuning0,
explicit ASM, the retained diagnostic player and identical ordered streams.
Count `.text + .data`, including startup, player, tables and reset dispatcher.
The source patches apply independently to the baseline src folder.

[Anonymous screen data](lsf-screen.json) records the independent stages:

| Representation/conversion | Full Flash delta | Static SRAM delta |
| --- | ---: | ---: |
| Q=q+1, reconstruct old normalization | -18..-14 B | -20 B |
| q with255 sentinel, reconstruct | 0..+4 B | -20 B |
| Q=q+1, directly compute normalized grid coordinate | -56..-54 B | -20 B |
| q with255 sentinel, direct grid coordinate | -38..-34 B | -20 B |
| Q=q+1, directly compute even-table index (selected) | -100 B each | -20 B |

The cleaned selected implementation reproduces the -100 B result in all8
images. Each screen variant passes36 native PCM/PWM comparisons on both
profiles, extras and short packet boundaries. The selected source passes56
existing regression tests, including the frozen legal-grid LPC digests for
both layouts and segments1/2/4,1,838,989 parser cases per layout/reader mode,
reference reader/counter/history paths, snapshots and bandwidth expansion.
This is exact output preservation; no sound-quality gain is claimed.
Full181-case,204-chain and IRQ admission remains the final campaign stage.

## Narrow only the private v5 remaining count

The valid v5 count is at most64000. The public sampleCount remains uint32:
failed begin may retain an invalid raw count, including65536 or UINT32_MAX.
Only compact remaining becomes uint16. produced performs explicit modulo16
subtraction before widening (and adds subPos in batched mode). Valid progress
is at most64000; after a failed/repeated begin both counts have identical low
words and progress remains zero. Common/legacy counters retain their width.

[Counter screen](counter-screen.json) saves74..78 B standalone and2 B static
SRAM. With selected byte LSF, the measured combined delta is -174..-176 B
Flash and -22 B SRAM, rather than an assumed sum of independent LTO savings.
The frozen public lifecycle probe was first compiled against b8f473a6 and
matches after narrowing in both layouts, batched/per-sample counters and
ROM-pointer/base-cursor readers. It covers full64000-sample outputs in both
profiles; header lengths0..22; invalid/null/short/valid transitions; count
edges through UINT32_MAX; parser errors; copy/assignment after errors and
mid-stream. Getter arithmetic independently exhausts every legal total count
and every position in its final subframe. It does not claim a fresh complete
DSP decode for every one of the64000 possible lengths. The existing parser
frozen trace also matches all1,838,989 cases per layout/reader build.

## Pack the packet phase without changing commit points

Compact subIndex stores the subframe in low3 bits and the old post-readFrame
half in bit3. readFrame toggles the same half bit at its original point;
subframe advance preserves it and wraps only the low3 bits. Tests of frame
boundaries use low3 bits, pulse parity is unchanged, and interpolation receives
only the original0..7 index. The corrected full-packet predicate is now simply
zero packed phase: exactly the conjunction of the old zero half and zero
subframe, after the same advance. There are no special sample-length cases.
Common layouts retain their separate fields and behavior.

[Phase screen](phase-screen.json) saves4..10 B Flash and1 B static SRAM
standalone. The actual byte-LSF/counter/phase combination saves184..190 B
Flash and23 B SRAM in the8 full images,10..14 B better than the counter/LSF
combination. Frozen malformed parser and lifecycle/count digests remain exact.
The native half-spectrum matrix covers segments1/2/4, bandwidth expansion,
static/changed spectra, copies and corrected partial tails. The bit encoding
proves the EOF predicate equivalent for every length; every320-sample residue
in the first two packets is also exercised through the real native decoder.
A full64000-sample lifecycle run exercises repeated phase wraps. This is not
an assertion that every complete DSP stream length was individually decoded.

## Remove derived brightness history

At each successful sample boundary, prevBright was assigned exactly
clipQ14(prevDeemph). Reset sets both histories to zero. Derive that clipped
old deemphasis value before overwriting prevDeemph, keeping the original
attenuation, rounding and saturation order. This removes a redundant state
word across layouts, without changing the filter or stream format.

[Brightness screen](brightness-screen.json) saves2 B Flash and2 B SRAM
standalone. The measured LSF/counter/phase/brightness combination saves
188..192 B Flash and25 B SRAM versus corrected baseline, an additional2..4 B
relative to the preceding combination. Header edge tests compare exact native
PCM/PWM with the independent model for pre=0/1/8192/16384 and
brightness=0/1/8192/11469, both profiles, alternating low/high spectral clusters,
maximum scale and pitch gain. All128 output comparisons pass; the existing
compact suite (8 tests including reference/copies/EOF) also passes. Final
whole-corpus and active-IRQ admission remains separate.

## Rejected workspace and static-endpoint experiments

The [full-image screen](workspace-endpoint-screen.json) retains reproducible
source patches. These are rejected experiments, with no production wiring:

- A typed overlay uses a union of a20-byte coefficient struct and48-byte
  polynomial-P struct. Explicit single-object placement activation precedes
  every workspace phase and restores synthesis lifetime after conversion;
  no raw reinterpret_cast, array-new cookie, heap or96-byte stack relocation
  is used. A distinct placement tag avoids replacing a platform allocator.
  The union provides alignment; trivial representation copying follows
  [C++11 draft copy rules](https://timsong-cpp.github.io/cppwp/n3337/class.copy#16),
  with explicit active-member transitions following
  [its union guidance](https://timsong-cpp.github.io/cppwp/n3337/class.union#4).
  The host prototype passes36 output comparisons and saves20 B static SRAM,
  but every full AVR image grows4 B Flash. It is rejected under the Flash
  priority before expensive final copy/sanitizer/IRQ admission. No claim of
  a supported overlaid decoder is made.
- Reading static coefficients directly from the cached endpoint removes its
  frame-start copy but adds coefficient selection to every sample. The local
  pointer is derived from owned arrays/offsets, and bandwidth expansion keeps
  its original a[] fallback.36 output comparisons pass; full Flash changes
  -2 B for single-reset images and +10 B for multiple-reset chains. Static
  RAM is unchanged. Reject as a universal default; no final timing claim.

The actual linked synthesis epilogue was also inspected under the baseline
AVR recipe. It already flows directly from the Q4 accumulator into clipping,
then four contiguous mirrored-history byte stores. Its one movw transfers the
low result to the upper-register pair required by the current CPI-based clip;
there are no intermediate SRAM spills or repeated history-pointer reloads in
that boundary. The conditional plan item therefore supplies no demonstrated
redundant transfer to remove. No new fused handwritten ASM was introduced.
Every existing C/ASM arithmetic selector and fallback remains available.

## Rescreen existing linear history in the changed context

The original fixed-baseline screen of LPX4_LPC_RING=0 saves0..10 B Flash
and20 B static SRAM. After byte LSF, narrowed/packed state, derived brightness
and shared attenuation, repeat the same bounded8-image screen rather than
assuming that result remains valid. The measured ring combination saves
214..216 B Flash versus b8f473a6; linear saves218..222 B, an additional2..8 B,
and brings total static SRAM reduction to45 B. The history algorithm and its
C/ASM implementations already existed; no assembly kernel was added.

The [new-context cost screen](history-screen.json) and
[bounded IRQ gate](history-irq-screen.json) preserve exact sources and actual
AVR macro selection. The latter chooses the worst prior160-sample conversion
window among complete64000-sample controls in each profile, then compares
ring/linear at normal/+100-cycle IRQ loads. All8 complete outputs match the
model, with zero underruns/errors. Linear costs2.85..3.03% more decode wall
cycles; max160 grows2.38..3.11%, reaching162695 cycles in the worst control.
The reported producer-side queue minimum remains386 and observed stack margin
improves920 to940 B. These are bounded gate results, not universal admission.

Only the explicit compact size layout changes its default to linear. Common
layouts retain mirrored history by default; either layout can still explicitly
select0/1. The isolated prototype patch forces0 for its screen, while the
production-default patch preserves that common-layout policy. Final source
uses the header hash in the cost receipt. All58 core regressions pass, including
both layouts, frozen coefficients/parser/lifecycle traces, reader/counter/history
fallbacks, segments1/2/4, bandwidth expansion, tails and snapshots. Full181/204
corpus and final diagnostic/production IRQ matrices are the remaining gate.
