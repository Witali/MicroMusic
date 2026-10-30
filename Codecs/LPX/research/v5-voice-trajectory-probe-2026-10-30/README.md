# Fixed-size trajectory search with the voice/noise objective

The existing multi-frame trajectory refiner adds no admissible improvement to
the current 1710-byte A endpoint under this declared 128-render probe. It finds
a slightly better 1701-byte alternative to the older 1702-byte V1 control, but
correct-period coverage does not improve. This evidence does not justify adding
another search operator to the default controller. No production branch or MCU
code was added. This is one tuning source, not a general verdict on trajectories.

| Seed | Outer-admissible result | PCM SER before / after, dB | Correct periods PCM / PWM before and after |
|---|---:|---:|---:|
| V1, 1702 B | 1701 B | 6.63609 / 6.65517 | 58 / 57, unchanged |
| Unified A, 1710 B | original 1710 B retained | 7.41740 / 7.41740 | 61 / 59, unchanged |

The source has 77 assessed period windows. Missing decoded periods remain
failures. The best raw A alternative lowers the joint proxy from 0.304473 to
0.304102, but increases PCM SSE by 35428 and PWM SSE by 131072 and slightly
lowers PCM STOI. Existing floors reject it; they were not relaxed to accept a
marginal score change. No new listening or audible-quality claim is made.

Both successful calls reached their 128 full-render limit and performed 129
objective evaluations including the baseline. Their measured helper regions
sum to 24.64 s wall / 23.09 s process CPU. These figures exclude endpoint
rechecking and the first failed postprocessing attempt, whose exact inner
counts and timing were not retained. They are not total campaign cost and are
not a matched-CPU comparison with the earlier four-call controller.

The campaign contains **three completed target helper calls**, two retained
helper reports and one failed postprocessing attempt. The original adapter
mistook the refiner's dictionary frontier export for an object and failed after
the first V1 call, before validating any endpoint. Its immutable failure was
retained. A source correction and two passing adapter contracts preceded one
explicitly documented recovery run with identical settings. Unrecovered work
is unknown, with at most 128 full renders in that first call; it is not silently
counted as zero or fabricated from the recovery's counters.

The [protocol](PROTOCOL.md) records this correction. The frozen V2 98/14/6 corpus
experiment is unaffected: no pool, gate, source file, byte ceiling or worker
was changed. There are zero initial seed fits and no cap/setting retuning here.
Eight anchors, two-frame windows and beam width 3 use the existing integer
decoder and full source-frozen PCM/PWM voice/noise objective at each seed's
exact complete-file ceiling. The finite render limit does not bound all local
screening work and is not a global optimality guarantee.

The [read-only projection](reproduction/project.py) independently reopens every
saved endpoint, source/input/artifact guards and the retained prior failure.
All endpoint metrics and outer selection reproduce; 16 common/v5-only output
domain checks / 512000 compared samples match the integer model. Detailed
anonymous values are in [results.json](results.json). No AVR images were built
for these marginal alternatives, so they have no new real-time or full-Flash
admission. Actual audio, streams, fingerprints and private receipts remain in
ignored build storage.
