# Exact v5 rate allocation on the host

`speech_rate_allocation.py` owns complete v5 bit accounting and optional-pulse
reclamation. MCU sources and v5 syntax are unchanged. The historical
`refine_speech_lpc.fit_capacity` and `spectrum_bits` imports remain available as
compatibility re-exports. Its amplitude/position ordering is retained as an
explicit experimental control; it is not the marginal algorithm.

`bit_accounting(spectra, profile, extras, force_extras=False)` counts the actual
gap/delta/repeat spectral choice, 15-bit half-frame parameters, profile-specific
base pulses, every optional-pulse marker, 10-bit active extra, 22-byte header and
final byte padding. A partially played final packet is still fully stored.
`extra_capacity` is shared by LPC, excitation and enhancement callers. Capacity
zero alone does not imply that the fixed fields fit.

```python
result = reclaim_extras(
    spectra, profile, extras, max_bytes,
    render=lambda candidate: render_full_pcm(candidate),
    objective=lambda pcm: whole_reference_loss(pcm),
    serialize=lambda candidate: pack_stream(candidate),
    start=0, max_evaluations=4096,
)
```

The callbacks close over each path's own spectra, parameters, base pulses,
filters and exact synthesis state. `render` returns the complete original-length
integer PCM, with full pitch/LPC/postfilter consequences. `objective` scores
that full output without changing its length or gain. `serialize` is optional;
when provided, every measured cost must equal the actual complete byte length.
The module imports neither a search implementation nor an objective policy.

Each round renders every eligible removal from the current candidate and
accepts the least distortion. Scores are discarded after accepting a removal:
interacting pulses cannot reuse their old additive ranking. Extras before the
40-sample-aligned `start` are frozen so a caller can retain its exact cached
prefix. Callbacks receive owned arrays, and results do not mutate the seed.

`AllocationResult` contains owned `extras`, complete `pcm`, optional `stream`,
`feasible`, `status`, `file_bytes`, `payload_bits`, `capacity`, `removed`,
`evaluations`, `score` and a numerical removal `trace`. An oversized input is
allowed. It can return `evaluation_limit` or `no_removable_pulses` with
`feasible=False`; neither outcome proves that a different v5 stream cannot fit.
Only complete evaluation rounds choose a pulse. The budget includes the initial
render, so the allocator never labels a partially evaluated round an exact
minimum. The evaluation limit is a computational bound, not a quality floor.

`distortion_rate(D, file_bytes, lambda)` exposes `D + lambda * R`, where `R` is
the complete serialized bit count, including header and byte padding. Its
lambda units follow the caller's objective. Optional removals in one round
have equal rate, so lambda does not alter their ordering; it is useful when
the search compares different spectral/excitation proposals. Exact gap/delta/
repeat costs must be refreshed when a spectrum or its predecessor changes.

The focused tests independently compare snapshot reconstruction with the full
integer model and both native decoder layouts, check serialized costs including
tails/marker disappearance, and force a coupled-removal ranking reversal.
No perceptual gain or target real-time admission follows from these unit tests.
