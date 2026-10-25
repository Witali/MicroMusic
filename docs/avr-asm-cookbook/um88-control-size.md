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
software multiply. Its two nine-bit symbols still require three Flash reads.
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
