# V5 host perceptual objective

`SpeechObjective.from_v5(reference, seed_blob, mode='perceptual')` binds an
original-level PCM16 reference and a frozen, exactly interpolated seed LPC
trace. `objective(pcm16)` and `objective.score(pcm16)` rank complete clipped
integer reconstructions. `mode='sse'` retains the waveform-SSE control.
Candidate spectra never change the weighting criterion.

The existing `perceptual_rate.weight_error` numerical kernel is reused without
modification: W(z) = A(z/gamma1) / A(z/gamma2), default gamma1=0.9 and requested
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
