# Frozen four-pulse Sparse80 mechanism

This is a separate experiment from the P3 coefficient-trace correction. It
changes existing v8/mode15 innovation bits only. No decoder, spectrum, metadata,
filter, target gain, sample count, packet geometry or output scaling changes.
The protocol and limits below are fixed before any speech result. Implementation
and deterministic synthetic validation are authorized first; speech comparison
requires the saved predecessor and target binding and a separate go decision.

## Search and controls

Select at most four complete, nonoverlapping existing 320-sample frames by
descending baseline PCM SSE, then ascending frame index. Never edit a partial
final frame, including its played symbols. Synthesis and scoring still extend
through every unchanged sample to the actual EOF. There is no zero padding in
the scored reference or decoder state.

For each of a frame's four existing 80-sample innovations, freeze at most three
distinct legal seven-bit symbols using its ORIGINAL baseline h[10], ring[256],
de-emphasis dd and previous clipped cc state. All 128 symbols are screened once:
64 legal positions `code + ((code + 2) >> 2)` and amplitudes -8/+7. Preserve the
incumbent, the immediate 80-sample PCM-SSE winner, and the next 400 real samples'
PCM-SSE winner with all future symbols unchanged. Short final horizons end at
the actual EOF. Ties prefer the incumbent, then the ascending seven-bit wire
symbol. Deduplicate these three winners; if fewer than three remain, fill from
alternating immediate/tail ranked lists, skipping already chosen values. The
pool order is incumbent, distinct winners, then these ranked fills. No earlier
trial or later leaf may alter a pool or baseline snapshot.

Enumerate every Cartesian assignment (at most 3^4 = 81 per region, 324 total).
Recompute the changed frame from its real original prefix state and keep the
unchanged suffix, with actual pitch ring, LPC, dd and cc propagation to EOF.
Evaluate complete PCM SSE. Independent model decoding and both native common
and v5-only reference receivers must agree on every leaf's PCM and PWM. The
native receivers use the existing v8-to-v5/P6 reference expansion; they are NOT
direct Sparse80 parsers. Duplicate baseline leaves can share native replay.

Compare prefix-greedy (width 1), width 2 and width 4 on the SAME frozen pools.
After each 80-sample innovation keep only the width best prefix PCM-SSE paths;
ties use pool-index lexicographic order. This also applies at depth 4. Compare
the surviving complete paths by whole-file PCM SSE with the unchanged suffix.
The exhaustive winner is a restricted-pool oracle, not a global optimum over
128^4 possibilities or a proof of audible quality.

Each edited region is independently anchored to the same protected baseline.
Do not chain frame patches, combine separate regions or change the 4/3/400
limits after inspecting outcomes. Report leaf counts, prefix/control extension
counts, symbol-screen samples, suffix samples, native/model checks and runtime
separately. Screens are bounded by 2048 symbol trials and 819,200 samples;
whole suffixes are bounded by 324 * 64,000 = 20,736,000 samples. Independent
model/native verification has additional work and must not be hidden.

## Whole-output shortlist and admission

Before speech outcomes, the fixed exhaustive quality shortlist is the first
12 DISTINCT changed full streams by complete PCM SSE, frame index and leaf
ordinal. Retain the best GENERATED changed raw proposal even if worse than the
baseline. If no frame is editable, the raw output is the unchanged baseline.
The incumbent is always the protected rollback. Each control is admitted
SEPARATELY using at most four complete frame winners; do not place its result
into the exhaustive pool or present ordinary extra search as a topology gain.

Each shortlisted candidate preserves the original complete byte length, all
non-pulse bits, unused final bits and every symbol in a partial final frame.
Patch original absolute seven-bit offsets instead of repacking: multiple legal
Rice spellings can encode the same spectrum. Strict unpacking precedes native
replay. No admission may spend spare bytes under the nominal 2 kbit/s cap.

Reuse the existing `refine_sparse80_pulses` whole-output policy: PCM/PWM SSE
and available STOI nonregression, both source-frozen voice floors, clipped
counts, fixed PWM high-band totals, burst maxima and EVERY partial tail-window
floor. Require changed actual PWM and strictly better old mean joint and PWM
joint objective to select. These numerical tests are not listening evidence.
Report old baseline/raw/final metrics and raw rejection reasons. The new
operator ranks trials using PCM SSE only; PWM feedback enters whole-output
admission, preserving the old research-policy distinction from host P3's typed
PCM/PWM target selection.

## Required synthetic validation and provenance

Before speech, record a deterministic real-recurrence case where exhaustive
finds a leaf discarded by at least one same-pool control, with all complete
native/model PCM/PWM outputs checked. Test nonminimal legal Rice spectra,
partial tails, nonzero brightness, pitch feedback, saturation, exact input
bytes and unchanged fields. Never call a synthetic case a speech gain.

Bind a real comparison to the saved FINAL November 2 round-3 best and its
declared integer source target where available, not a weaker fresh round-0
encode. Check immutable best pointers and source/target hashes locally; do not
publish private records. If that final predecessor has no public-source match,
state the gap explicitly and preserve the public fixture/retained seed and
existing follow-up controls. A playback manifest alone does not prove the
encoder's source normalization recipe. All generated streams/targets, detailed
journals and source hashes belong under ignored build/ unless already public
and intentionally selected for a source-only aggregate report.
