# Delayed innovation beam round

Registered before outcomes. Hold the saved incumbent's spectra, scale/lag/gain
metadata, filters, sample count, format and exact complete-file cap fixed.
Change only legal innovation positions/signs. This round requires brightness 0
and 320-aligned complete targets, as in the initial public/corpus workload.

There are exactly four new complete attempts: beam widths 2 and 4, each with
ordinary waveform SSE and the frozen clipping-aware loss. Starting from zero
decoder state, retain the best width paths after every 20-sample P4 innovation
or 80-sample sparse80 innovation. Each state owns its exact LPC history,
deemphasis history and 256-code pitch feedback ring. Try every legal position
and sign from every live state. Do not reset histories at metadata boundaries
or manufacture pitch from a candidate tracker. Ties retain parent/position/sign
order. Costs use signed64-bit integers; the frozen clipping penalty remains
within that range even for the supported 64000-sample upper bound.

The beam is a finite proposal search, not a global optimizer. In particular,
a path pruned by its prefix cannot be recovered later. Preserve the exact
original whole stream independently even if the beam prunes its pulse path.
Replay the final serialized stream through the shared independent model and
both native C receivers; the existing whole PCM/PWM quality/pitch/clipping
gates decide admission. A smaller proposal SSE does not override those gates.

Charge every actual trial, including identical serialized final outputs and
the initial single-state expansion. For G groups and width K, there are
`positions * 2 * (1 + (G-1)*K)` trials when G>=1; positions are 16 or 64.
Report actual counters and complete-output verification separately. Verify
width 1 against the original greedy fixed-parameter search on synthetic data,
and compare the beam's exact proposal cost against independently reconstructed
PCM/clipping counts before corpus execution.

The complete corpus, heldout split, protected best streams and prospective
three-round stopping counter are defined in
[ITERATION_PROTOCOL.md](ITERATION_PROTOCOL.md). No decoder instructions,
tables, RAM fields, sample rate or playback gain are introduced by this round.
