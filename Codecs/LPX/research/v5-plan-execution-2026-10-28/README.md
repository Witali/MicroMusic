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
