# V5 host perceptual objective

`SpeechObjective.from_v5(reference, seed_blob, mode='perceptual')` binds an
original-level PCM16 reference and a frozen, exactly interpolated seed LPC
trace. `objective(pcm16)` and `objective.score(pcm16)` rank complete clipped
integer reconstructions. `mode='sse'` retains the waveform-SSE control.
Candidate spectra never change the weighting criterion.

The existing `perceptual_rate.weight_error` kernel remains unchanged and is an
independent whole-trace control for the stateful implementation of the same
recurrence: W(z) = A(z/gamma1) / A(z/gamma2), default gamma1=0.9 and requested
gamma2=0.6. Legal v5 spectra can produce clipped LPC coefficients that do not
define a stable floating-point denominator. One seed-wide gamma2 is therefore
chosen so every coefficient row satisfies
`sum(abs(a[k]) * gamma2**(k+1)) <= 0.95`, with a[k] in real Q12 units. This
sufficient contraction bound also applies to time-varying rows. The numerator
is finite FIR; the denominator's output is bounded by its numerator peak
divided by 1-0.95. The bound can be conservative; it is not tuned per candidate.
`describe()` reports requested/effective gamma2 and the exact scoring scope.

For an original recording stored as independently reset streams, use
`SpeechObjective.from_chain(reference, ordered_seed_blobs)`. Each segment gets
its actual decoder LPC reset, while the weighted-error filter remains
continuous over the joined original waveform. `weight_error_chunk` exposes
copyable input/output histories for explicit continuations and branches. Use
one gamma2 computed over the complete trace; do not recompute damping or reset
weighting at frame boundaries.

Full original recordings may contain up to 4,294,967,295 samples. V5 coefficient
rows repeat exactly over each 20-sample subframe; the factory stores one
lossless int16 row per subframe and generates them in 6,400-sample chunks with
the preceding 160-sample LPC frame as interpolation context. A reset segment's
final partial subframe is kept, then the next segment starts its own LPC trace.
Each chunk's contraction solution uses the same settings; their minimum is the
same frozen seed-wide bound. Weighting histories continue across all chunks.
The dense constructor also remains available for arbitrary coefficient traces,
stored as int16 chunks without assuming repeated rows.

The reference is frozen as PCM16. SSE mode validates the seed stream geometry
but constructs no coefficient matrix or weighting state. Each chunk's integer
SSE dot fits int64; Python integers accumulate the total before the scalar
float return. The uint32-length worst case is 18,446,181,123,756,261,375, which
would overflow one int64 whole-recording dot. Perceptual energies use a
compensated sum of chunk energies. Floating-point reduction may differ from a
monolithic dot by rounding; independent comparisons use explicit numerical
tolerances, while integer synthesis and frozen damping remain unchanged.

The actual 3,786,111- and 3,138,052-sample corpus recordings are verified in
[full-length robustness evidence](../../research/v5-perceptual-objective-2026-10-28/LONG_RECORDINGS.md).
The uint32 bound is an arithmetic/count contract, not a claim of measured
runtime or available memory at the theoretical maximum.

`refine_speech_perceptual.py` is an explicit trajectory-search wrapper. It
requests conservative selection and independently rechecks returned complete
PCM16/PWM against the integer model and the existing `no_regression` gate.
Raw objective alternatives remain separate for blind listening. Oversized
seeds may be searched; a feasible tradeoff without a conservative fit returns
no selected audio. Unplayed padded-tail fields can sometimes be removed
losslessly. The CLI requires fresh output paths to avoid stale selected audio
after a later no-fit result.

From the active codec directory:

```text
python tools/refine_speech_perceptual.py reference.wav seed.l4hy output-directory --max-bytes COMPLETE_FILE_CAP --objective perceptual
```

Use the same search bounds and byte cap with `--objective sse` for a matched
control. Weighting only ranks host-side proposals: it changes no decoder
arithmetic or bitstream format and provides no listening or real-time claim.
Report full original-length PCM/PWM metrics, serialized sizes, encoder CPU and
wall time, and the finite search budget. Changed parameters still need target
IRQ admission; unchanged MCU sources alone do not establish timing support.

Independent tests cover SciPy constant and variable-coefficient filters,
physical history reconstruction at coefficient changes, chunk/branch/reset
ownership, whole-recording reset geometry, a legal unstable v5 fixture,
bounded extreme traces, original integer PCM, exact receiver/model/PWM tails,
and independent conservative-wrapper gates.
