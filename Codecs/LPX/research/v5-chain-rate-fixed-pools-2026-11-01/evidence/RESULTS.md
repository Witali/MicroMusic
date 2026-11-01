# Exact fixed-pool allocation: no new context-wide frontier

Exact allocation recovers five same-byte joint-score gains against individual
arms' original recipes. **None extends the size/joint-quality frontier of the
union of all five V1 arms' originals.** This is a useful finite-pool allocation
tool, not evidence of new overall codec quality, compression or an audible gain.
No default change, larger corpus run or target job follows from this result.

All 60 declared arm records completed exactly at their original B, covering 12
contexts and 100 saved reset pools. Each pool contains only its retained V1
frontier (at most 16) plus protected baseline/selected/raw options: 381 verified
integer-SSE rows reused. Each arm made one DP call; 100/95/90% endpoints came from
the same frontier. No helper, coefficient search, encoding, new native build,
pool widening, resource-limit recovery or retry occurred. All 50 single-reset
records pass identity against direct per-cap selection from their supplied pool.

The five primary gains are repeated views of speech source 42, not five
independent recordings. Every gain uses exactly its old complete byte count:

| Profile / arm | Bytes | Old joint score | New joint score |
| --- | ---: | ---: | ---: |
| P4 / G-full-0 | 16141 | 0.195037041474 | 0.195034981907 |
| P6 / T-local-0 | 23259 | 0.136129593222 | 0.136114712615 |
| P6 / T-full-0 | 23259 | 0.136129593222 | 0.136114712615 |
| P6 / G-full-0 | 23259 | 0.136129593222 | 0.136114712615 |
| P6 / G-full-.1 | 23259 | 0.136129593222 | 0.136120274805 |

The original five recipes plus DP add ten arm-local unique whole tuples in total;
this does not mean ten globally distinct recordings. Among 17 cap-qualified
added-tuple views, one is already known in another V1 arm, five are dominated or
equivalent to an admissible context original, and eleven fail whole admission.
No added point extends the context-wide frontier, including points not selected
by the minimum-joint-score policy. [Per-arm gains](primary-wins.json) and
[complete known/dominated/rejected classifications](classifications.json) retain
the details; [secondary.json](secondary.json) records both comparison roles.

| Cap | Original admitted /60 | New admitted /60 | New no-fit | New raw-only |
| --- | ---: | ---: | ---: | ---: |
| 100% | 60 | 60 | 0 | 0 |
| 95% | 0 | 0 | 42 | 18 |
| 90% | 0 | 0 | 54 | 6 |

These are arm views with overlapping sources. No-fit describes the measured
whole union; the exact finite-pool SSE frontier is reported separately. Whole
PCM/PWM SSE/STOI, clipping, period coverage and joint voice/noise gates remain
unchanged. Integer SSE/rate optimality is not optimality under those gates.

The campaign freshly checked 192 whole rows, with 88 fresh metric keys and 164
exact new-study reuse events including the 60 before-DP baseline requests.
117 distinct reset streams / 5,401,462 model samples passed 468 common/v5 native
PCM/PWM comparisons. Fresh integer whole-SSE checks agree with the reused local
sums. No actual media, paths or stream/PCM/image fingerprints are exported.

DP visited 3195 transitions; the largest working layer contained 202 states,
below the unchanged 250000-state / 10000000-transition limits. The sum of measured
DP clocks is 0.015625 CPU seconds / 0.0163794 wall seconds; this is a tiny supplied-
pool workload and includes timer quantization, not a universal speed claim.

Windows process times measure 103.171875 CPU seconds / 105.9086359 wall seconds
for the real Python worker through exit, including imports, CLI and final writes.
Its execute-body snapshot is 102.75 CPU seconds. Process CPU excludes git/source-
binding subprocess CPU and the external launcher; wall time includes their wait.
Metadata preparation used 28.828125 body CPU seconds, synthetic native preflight
12.328125 worker CPU seconds, and the independent saved-only audit 14.078125 body
CPU seconds. These overlapping clock categories must not be added. The earlier
V1 raw-model audit's 222.734375 CPU seconds remain prior paid work. See
[cost scopes](costs.json) and [producer counters](summary.json).

Actual execution used the chain-study worktree with production inventory
`654ada493202f565d24cb9dcf22f16137c825329` and producing research commit
`700147a571aacaf56b9587053e7f96385d403bc6`. The V1/model/native bridge remains
explicit: old V1 epoch `b21cb028`, unchanged DSP/metric/C/header/table closure,
and pinned reused common/v5 libraries; only host trajectory ordering differs.
This is host native output evidence, with no AVR image, full-Flash, IRQ,
physical-board or listening admission.

The [independent saved-only audit](audit-summary.json) reopens committed source
bytes and all input/artifact pins, checks every stored integer tuple, all 180
decisions, full saved gates, cache creators and coverage counters. It performs
zero DP/model/metric/native reruns and relies on the producer's fresh native
checks. [Source hashes](sources.json) bind the producer and separate postcheck.
The producing recipe and original experiment are unchanged. Further quality
work needs a different independently bounded mechanism; repeating this allocator
on unchanged larger pools is not justified as a quality breakthrough.
