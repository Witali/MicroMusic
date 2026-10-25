# UM88: smaller command decoding and voice addresses

Original MicroMusic C techniques, measured on ATtiny88 / AVR25 with GNU AVR
GCC 7.3.0, GNU ABI, `-Os -fno-jump-tables -ffunction-sections
-fdata-sections -Wl,--gc-sections`. Baseline: `41e456a9`. No instruction-set
extension, compiler LTO policy, musical command, or voice slot is removed.

## Share address work

An eight-entry Flash table stores `index * sizeof(UMVoice)`. A shared
`voice_at()` adds that byte offset to the voice array. This replaces repeated
software multiplication by the 23-byte AVR record size in CONTEXT, PITCH,
LEVEL and PHASE_COPY. The table uses `UM_CONST`/`UM_VALUE`, preserving the
storage adapter. Its offsets derive from `sizeof`, not a hard-coded AVR ABI;
ordinary pointer indexing remains the fallback if an offset exceeds 255.

The initialization refresh loop and C mixer traverse voices with a pointer.
Together with exact shift/add offsets for dictionary pairs and envelope rows,
this removes the last linked `__mulhi3` caller from the production engine.
Sharing the header-pointer binding in one non-inlined helper also saves code.
The state layout, public rendering ABI and zero/callee-saved register rules
are unchanged. The helper can increase call-stack depth, so the complete IRQ
audit must still measure the actual stack above the FIFO.

## Commit decoder cursors once

Keep a local pending-stack pointer while expanding a grammar rule and commit
its depth once on return. Keep stream address and bit position local during
one symbol read. This removes repeated state loads/stores while retaining
left-before-right rule expansion and exact advancement across byte boundaries.
The bounded depth is still twelve; pending slot twelve remains reserved.

For compact rule index `i`, the pair begins at byte `2*i + (i >> 2)` with bit
shift `(i & 3)*2`. This equals the old `floor(9*i/4)` address without a
software multiply. The first-pass implementation loaded three Flash bytes once
for the two nine-bit symbols. The shared `read9` implementation described below
uses four physical byte reads, including a repeated middle byte.
Envelope row `r` starts at `2*r + r`; no serialized data changes.

LOOP preserves its original reset order and contexts. PHASE_COPY observes the
source phase at its exact command position. Envelope changes happen before
new commands. Neither command merging nor event reordering is used.

## Measurements and reproduction

The isolated control/stream patch is 2830/2882 bytes at 8/16 MHz with compact
packing, against 2930/2982 bytes. Its fast128 core is 2930 against 3036 bytes.
These figures exclude the subsequent init, gain, C-mixer and IRQ changes.
On the dense-eight compact workload its control peak falls from 26120 to
19170 active cycles and minimum FIFO rises from 58 to 92 frames. The isolated
fast128 dense peak falls from 19574 to 16215 cycles (FIFO 26 to 42).

The final combined runtime sizes and retained-image measurements are in
[core-size-comparison.json](../../ATtiny88/Music/universal/reports/core-size-comparison.json).
They must not be inferred by adding isolated savings: linking and the
32-byte song boundary can change the final result.

`tools/test-universal-packed-decoder.mjs` executes real C/ASM routines with
both compact9 and fast0 snapshots at each clock. It checks every code through
511, all 256 terminals, rule index 510, depth twelve, guard bytes, machine
stack and stream position. The adjacent control-order fixture checks eight
voices, nonzero phase copies, resets, envelope ordering, percussion, WAIT and
LOOP. `tools/audit-universal-music.mjs` separately checks complete scores and
PWM with active interrupts; decoder conformance alone proves no throughput
claim. C remains explicitly selectable, including on this AVR.

## Second pass: share reset tails and reuse validated context state

Isolated against `565e8958`, before the later read9, ASM-loop, and tight-placement
changes. [Measurements](measurements/um88-control-second-pass.json) and the
[reproduction patch](examples/um88-control-second-pass.patch) preserve this experiment.
Compiler, CPU, GNU ABI, and explicit C/ASM selection are unchanged from above.

- Share the stream, decoder-position, control-time, and percussion reset tail
  between cold initialization and LOOP. LOOP still clears phase/step/level
  first and preserves contexts. Cold initialization still clears `UMState`;
  it does not reuse the warm voice-reset loop.
- Select the LEVEL voice index before its single `voice_at` call. WAIT and
  LOOP need no unused voice lookup. PHASE_COPY and event order are unchanged.
- Share dirty-mask updates through one ordinary C helper. No state-layout or
  hardware-access change is introduced.
- Reuse the cached mix class for level-only waveform refresh. Validated contexts
  require raw gain bit 32 exactly when `mix==0` or mix bit 32 is set. Thus the
  original `!(gain & 32)` predicate equals `(v->mix & 0xA0) == 0x80` for every
  legal mix, including all pans and group attenuation. Context changes still
  force refresh before this classification can matter. This removes a redundant
  context Flash read; it does not skip a required envelope or waveform update.

| Profile | C baseline → candidate | ASM baseline → candidate |
|---|---:|---:|
| 8 MHz, compact192 | 2624 → 2566 B | 2540 → 2482 B |
| 16 MHz, compact192 | 2676 → 2618 B | 2594 → 2534 B |
| 8 MHz, fast128 | 2724 → 2666 B | 2642 → 2584 B |
| 16 MHz, fast128 | 2776 → 2718 B | 2694 → 2636 B |

The combined saving is 58 bytes per tested core. Individual changes are not
additive: full voice-reset sharing saved only 18 bytes, stream-tail sharing 20,
cached classification 26, and dirty-mask sharing 6; dispatch alone grew 6 bytes
but improved the combined result. These are core bytes, not predicted aligned
song-image savings.

Both clock-specific compiled suites passed 44 decoder cases each, including
the adjacent eight-voice control-order fixtures for C/ASM and formats 0/9.
The retained fixture now has `normal`, `raw-terminal`, and `raw-interior` modes:
24 compiled control variants across both clocks, including sixteen raw variants.
Raw terminal voices form eight closed single-voice groups; raw interior voices
form two closed four-voice groups. Distinct waveform banks and alternating
context changes make a missed context refresh observable. Alternate event blocks
keep contexts stable while levels change. Counting actual `um_scale_wave` entries
checks both seven context/LOOP refresh steps and nine LEVEL-only cache-reuse steps
per raw variant. Nonzero phases, envelope-before-event order, percussion, WAIT,
and LOOP remain covered. All cached waveform bytes and state match the independent
uncompressed reference. Reports preserve each mode and the fixture source hash.

Dense-eight playback with active IRQs passes on both boards. Fast128 minimum
FIFO is 42 → 41 frames; compact192 remains 91. Control peaks rise about 132
cycles (16604 → 16736 fast, 19558/19559 → 19690 compact), while stack margins
improve by four bytes. There are no underruns, lost IRQs, or PWM differences.
This is a measured size tradeoff, not an unconditional speedup or a silicon
measurement. Final combined release figures belong to their separate report.

## Second pass: share the packed word reader

This decoder-only experiment is isolated against `565e8958`, before combining
the reset/cache changes above, later ASM-loop changes, or tighter song placement.
The [measurements](measurements/um88-decoder-second-pass.json) and
[reproduction patch](examples/um88-decoder-second-pass.patch) retain that scope.
CPU, toolchain, GNU ABI, compiler options, and explicit C/ASM selection are the
same as the first pass. All decoder changes are ordinary portable C; the storage
adapter, public interface, state layout, and callable `command` boundary remain.

Share the Flash word load and nine-bit extraction in one non-inlined helper:

```c
static UM_NOINLINE uint16_t read9(uint16_t at, uint8_t shift) {
    return (um_word(at) >> shift) & 511;
}

/* Pair byte address and shift retain their existing formulas. */
*pending++ = read9(at + 1, shift + 1);
code = read9(at, shift);
```

Valid shifts are always 0..7: stream positions cycle through all eight values;
pair-left shifts are 0, 2, 4, 6 and pair-right shifts are 1, 3, 5, 7. `um_word`
still reads through `UM_READ`, so the helper adds no processor-specific memory
or register access. `UM_NOINLINE` is guarded for GNU-compatible compilers; other
C compilers retain the same arithmetic without requiring that attribute.

Each compact9 pair now performs **four physical Flash byte reads**: `at+1`, `at+2`,
then `at`, `at+1`. The middle byte is re-read from immutable score data.
Logical expansion still pushes the right symbol and follows the left symbol,
so command order is unchanged. Sharing the loads and shifts reduces live
temporaries and generated code despite the extra read. The helper occupies
22 bytes instead of the former 60-byte fallthrough `shift9`. Commit the pending
depth once before choosing the fast0 literal or compact9 alphabet return path;
this removes another two bytes from the measured fast cores. Fast128 cores
retain both decoders. Their fast0 pair layout and four distinct byte reads
are unchanged; the repeated middle-byte read applies to compact9 only.

| Profile | C baseline → candidate | ASM baseline → candidate |
|---|---:|---:|
| 8 MHz, compact192 | 2624 → 2540 B | 2540 → 2458 B |
| 16 MHz, compact192 | 2676 → 2594 B | 2594 → 2510 B |
| 8 MHz, fast128 | 2724 → 2656 B | 2642 → 2574 B |
| 16 MHz, fast128 | 2776 → 2708 B | 2694 → 2626 B |

The isolated saving is 68–84 core bytes. These builds retained the old minimum
song address 2560 and 32-byte placement boundary. Crossing that address changes
`bind_pointer` constant folding by two bytes in some profiles. These figures
must not be added mechanically to the other isolated savings or treated as
the later tightly placed release sizes.

The measured compact dense-eight peak rises from 19558 to 21159 active cycles:
**1601 extra cycles**, with minimum FIFO falling from 91 to 84 frames. Compact
polyphony-study reaches 20118 cycles with minimum FIFO 89. Fast128 dense reaches
16433 cycles with minimum FIFO 42 at 8 MHz and 43 at 16 MHz; fast polyphony-study
reaches 15452 cycles with minimum FIFO 47. This is a Flash-for-control-time
tradeoff, not an unconditional speed improvement.

At the time of the isolated measurement, both clock-specific compiled suites
passed 44 decoder cases and four normal control-order fixtures each: 88 decoder
cases and eight control fixtures in total, covering C/ASM and formats 0/9,
every code through 511, rule index 510, depth twelve, pending guards, cursors,
phase copies, resets, envelope ordering, percussion, WAIT and LOOP. The later
raw-cache fixture expansion is recorded in the preceding section. Eight full
ASM dense/polyphony cycle-and-restart audits passed with interrupts active at
both clocks and both dictionary profiles. C held-four with compact192 and C
held-one with fast128 also passed. Every checked state and PWM byte remained
exact, with no underruns, lost interrupts, or clipping. These instruction-model
results do not establish physical hardware behavior or admission of other scores.

### Compiler-policy screen

A separate screen used the same four compact C/ASM profiles at 8/16 MHz.
`-mstrict-X`, `-fno-split-wide-types`, `-fno-inline-small-functions`,
`-fno-caller-saves`, `-fno-tree-ter`, and bounded LTO with the required callable
functions preserved saved zero bytes. `-fno-tree-scev-cprop` grew C by 34 bytes.
`-mcall-prologues` grew ASM by 68 and C by 56 bytes and introduced `IJMP`, which
the common executors do not support. No compiler-flag change was selected.
The measurements JSON retains the profile sizes and instruction observations;
these negative results apply to this workload and toolchain.
