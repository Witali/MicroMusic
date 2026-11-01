# Bounded cross-rate optional-pulse endpoints

`speech_rate_allocation.allocation_frontier` generates alternatives inside the
existing v5 format. Spectra, parameters, base pulses and decoder arithmetic stay
fixed within one call. The caller supplies a full-output renderer, a frozen
distortion objective and the actual serializer for those fixed fields.

```python
result = allocation_frontier(
    spectra, profile, extras, max_bytes,
    render=render, objective=objective, serialize=serialize,
    start=0, stop=actual_samples, rate_lambda=0.0,
    max_evaluations=64, candidate_batch=16, removal_steps=4, max_points=3,
    checkpoint=None, on_candidate=None,
)
```

Every measured point owns `extras`, full original-length `pcm`, actual `stream`,
exact `cost`, scalar `score`, stable `id` and descriptive `labels`.
`point.file_bytes` is the actual complete-file cost; `point.copy()` owns its
arrays and cost dictionary. Cost includes the 22-byte header, every complete
stored packet, spectrum coding, optional-pulse markers, values and byte padding.
Serialization is checked against that cost, requested spectra/extras, profile
and actual sample count; parameters, base pulses and filters must also stay
identical between endpoints. The renderer/objective remain the caller's responsibility;
these checks do not replace independent native/model validation.

The return object keeps three measured anchors separately from its bounded
`points` list:

- `unchanged`: the input optional-pulse allocation.
- `control`: the preserved amplitude-based fitting allocation.
- `suffix_all_off`: all optional pulses at or after the cached prefix removed.
  If earlier pulses remain, their global marker overhead remains too.

The allocator first measures a differing, feasible amplitude control; otherwise
unchanged is first. It then measures the other anchor and suffix-all-off. These
requests deduplicate by canonical optional-pulse fields, so an unchanged control
costs no extra evaluation. A bound of one can leave an anchor unmeasured: that
field is `None`, `anchors_complete` is false and status is `evaluation_limit`.
No unmeasured point receives fabricated metrics. A returned control may itself
be oversized when the fixed fields cannot fit.

Starting from the measured unchanged allocation (or the control if unchanged
was not measured), up to `removal_steps` fresh single-removal neighbourhoods are
examined. Each tests at most `candidate_batch` choices, ordered by unplayed stored
tail first, then absolute amplitude and chunk index. Every tested candidate uses
full-output reconstruction with the current state; scores are not added from an
old marginal table. The best tested neighbour becomes the next removal state,
even if distortion or priced distortion worsens: later removals can reach the
last-extra marker cliff. Earlier completed points remain available.

`points` contains distinct feasible endpoints for minimum `D + lambda * R`,
minimum `D`, and minimum actual rate. Here `R = 8 * len(stream)` and lambda is per
complete serialized bit. With fewer than three slots, those roles have that
priority. Ties use rate and stable evaluation order; duplicate streams occupy one
slot. Anchors are independently owned and are not evicted by this endpoint cap.
No local PCM/PWM, pitch or perceptual acceptance gate is imposed.

`start` is aligned to 40 samples and cannot exceed `stop`; all optional fields
before it remain byte-for-byte unchanged. `stop` is the actual output length,
including a partial final stored packet. Suffix removal may clear unplayed tail
fields, but never removes a stored packet, reset or requested output sample.

`checkpoint()` runs before each atomic serialization/render/scoring evaluation.
Exceptions propagate to the caller. After each distinct completed evaluation,
`on_candidate(owned_point)` runs before any next checkpoint, including for
oversized points. It can retain completed work when a later deadline expires;
mutating its point cannot affect internal state or return values. No filesystem
work is required by this helper.

The evaluation bound is in 1..4096. `evaluations`, `serialization_calls` and
`objective_evaluations` count completed
new measurements. `removal_evaluations` counts the new measurements requested by
removal neighbourhoods; `cache_hits` counts deduplicated requests. Each
`removal_rounds` entry reports its full neighbourhood size, tested candidates,
new evaluations, selected point/chunk, `exhaustive` and a partial reason.
`exhaustive_rounds` and `partial_rounds` summarize those entries. A partially
tested batch never claims an exact neighbourhood minimum. `bounded_complete`
means only that this declared finite exploration finished; `evaluation_limit`
means an additional requested measurement could not start. Neither status proves
a global optimum or impossibility of fitting another stream.

Callers must independently verify native/common/v5 PCM and PWM, retain prior
incumbents, and apply fresh complete-chain byte/Flash and quality admission.
Pitch/period coverage, clipping, voice/noise and PCM/PWM floors belong to that
outer admission. A lower priced score alone authorizes no promotion. The existing
amplitude, marginal-removal and swap APIs are unchanged; this opt-in helper adds
no MCU mode and establishes no timing, full-Flash or listening improvement.
