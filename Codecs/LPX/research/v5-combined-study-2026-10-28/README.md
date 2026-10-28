# Combined v5 search: completed corpus result

The combined search adds no automatically accepted 95% or 90% point over the
completed expanded legacy search. At 100%, its extra PCM/PWM proxy gains and
measured Flash savings are small. Keep the joint/perceptual/swap combination
experimental; this study changes neither MCU code nor an encoder default.

Both ranking modes covered all 49 original references, 98 profile groups and
118 actual reset segments at the three original complete-chain caps. The split
remained 40 tuning, 40 evaluation and 18 additional groups. The independent
cohort is four recordings / eight profile groups, a subset of the additional
split; it is not a count of independent speakers. The two tuning smoke groups
per mode were reused only through identical source/settings/input cache keys.
There was no held-out retuning. [PROTOCOL.md](PROTOCOL.md) is the unchanged
predeclared protocol; [summary.json](summary.json) contains the source-bound
numbers, split/cohort results, explicit no-fit masks and work counts.

| Ranking | Extra PCM error reduction vs strong control, 100% | Extra PWM error reduction | Total serialized bytes vs control, 98 groups | Changed 100% selected chains |
| --- | ---: | ---: | ---: | ---: |
| SSE | 0.011511% | 0.011074% | 366,923 → 366,915 | 29 |
| Frozen perceptual | 0.009295% | 0.009082% | 366,923 → 366,917 | 19 |

The corresponding aggregate PCM/PWM error reductions against the **original**
incumbents are 7.229976% / 7.232644% and 7.227920% / 7.230797%. Most of that
benefit already belongs to the expanded control. The table isolates the new
combination's contribution. Error reduction is computed from summed squared
errors, rather than averaging percentages. Mean additional STOI deltas at 100%
are about 0.000019 / 0.000030 for SSE ranking and 0.000010 / 0.000016 for
perceptual ranking. These numbers do not establish an audible improvement.

At 95%, both modes retain the same sole accepted profile point, 1,701 bytes
under its 1,710-byte original cap. Its revised PCM error falls another 0.060365%
relative to that accepted control; PWM metrics are unchanged. Its full linked
Flash is unchanged. This study does not add another 99-byte stream / 100-byte
Flash saving to the earlier original-versus-expanded result.

At 95%, 78 groups have a byte-feasible tradeoff, but 77 of them still fail the
required automatic floors; 20 have no byte fit in the supplied finite pools.
At 90%, 30 groups have only tradeoffs and 68 have no byte fit. No 90% selection
is admitted. Missing selections remain null. A finite-pool or metric-shortlist
failure is not proof that a smaller acceptable stream cannot exist.

Every automatically selected chain passes the original PCM/PWM SSE/STOI floors
and the accepted same-budget expanded control's floors where one exists.
STOI comparison preserves the existing numerical tolerance of 1e-12. Local
beam branches and allocator candidates are not pruned by segment-local quality
floors. Failed-original-floor historical tradeoffs remain listening/control
alternatives and do not relax promotion. All old accepted rollbacks survive.

The independent audit freshly checked 610 old-control metric sets and 610 final
whole-reference metric/objective sets. Its 568 unique streams cover 24,464,708
samples, with 2,272 common/v5-only native PCM/PWM comparisons against exact
clipped integer synthesis. It independently rechecked caps and floor flags.
The exact executed auditor is retained in
[reproduction/audit_combined.py](reproduction/audit_combined.py); input, recording,
stream and output fingerprints remain private in ignored storage.

The perceptual filter uses one frozen seed per complete recording, reconstructs
the actual LPC resets, and preserves error-filter history across every segment.
Requested gamma2 is 0.6; the unchanged seed-wide contraction rule gives effective
gamma2 between 0.243131 and 0.6 in this corpus. No candidate changes those weights.
SSE mode allocates no weighting coefficient matrix. Scores use original-level
full-length PCM, with no gain fitting or trimming.

The modes used 354 segment fits each. SSE / perceptual ranking performed
45,284 / 45,281 bounded full synthesis evaluations, 28,142 / 28,220 local screens,
and 17,309 / 17,327 allocator renders within the shared full-synthesis limits.
Allocator candidate, confirmation, excitation, serialization and assembler
counts are separate in the receipt. The 128-evaluation bound was reached in
338 / 340 fits; interrupted windows are recorded, not described as complete
joint searches. Record CPU totals, including the reused smoke, were 3,015.359
and 3,103.453 seconds. Worker wall times, warmup and reused-record counts are
reported separately. They are not a matched pure-search speed comparison with
the earlier campaign and should not be summed as parallel elapsed time.

## Complete production-player admission

[player.json](player.json) covers every strictly smaller selected stream versus
its accepted same-budget control, plus the changed 95% point. After exact-chain
deduplication that is 20 chains and 40 complete linked images. These admissions
were selected for cost/timing verification after the frozen search, with no
further fitting or quality tuning.

The unchanged ATmega328P v5-only player uses queue 256, prefill 192, explicit AVR
assembly, GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, 16 MHz / 8 kHz,
and the external simavr observer. Both normal IRQ and an additional 100-cycle
IRQ load passed full durations of 8,000–64,000 samples: 1,370,340 exact sample
ticks across all images, exact PWM, clean EOF/stop, zero decoder/observer errors
and zero underruns. Static SRAM is 756 bytes; minimum observed stack margin is
1,231 bytes. The maximum IRQ cost is 168 cycles. These are simulator results;
there is no physical-board or analog-output claim.

The seven SSE smaller selections save 2 Flash bytes in four groups and no Flash
in three. The five perceptual smaller selections save 2 bytes in three groups
and none in two. Results overlap between modes; do not add them together.
Alignment can consume a one-byte serialized reduction. The 95% point saves no
additional Flash. Full Flash is linked `.text + .data`; program Flash subtracts
only the exact embedded stream arrays. Same-size quality-only candidates outside
this subset have full native/model/PWM validation, not a new AVR timing claim.

The parameterized public admission driver reproduced the identical subset
bindings and revalidated the same 40 source/toolchain/output-bound image caches.
Those rechecks do not constitute 80 independent simulator runs. The initial
execution and public reproduction driver hashes are distinguished in the receipt.

## Reproduction and scope

Use the project Python 3.12 environment and the exact source/package inventory
in the receipts, with numeric-library threads set to one. Run from the repository
root with the active codec tools on `PYTHONPATH`. The corpus and the original
baseline-v2 plus the three completed expanded run manifests must be supplied
locally; this folder redistributes no recordings or compressed audio.

Follow the frozen protocol to prepare the shared native libraries and execute
both objective modes, shards 0/1, into `build/combined-v1`. Then run:

```text
python reproduction/audit_combined.py --study build/combined-v1
python reproduction/summarize_combined.py --study build/combined-v1 --output build/combined-summary.json
python reproduction/admit_player.py --study build/combined-v1 --output build/combined-v1/player --prepare
python reproduction/admit_player.py --study build/combined-v1 --output build/combined-v1/player --shard 0 --avr-bin AVR_BIN --observer SIM_PLAYER --simavr-lib SIMAVR_LIB --wsl Ubuntu
python reproduction/admit_player.py --study build/combined-v1 --output build/combined-v1/player --shard 1 --avr-bin AVR_BIN --observer SIM_PLAYER --simavr-lib SIMAVR_LIB --wsl Ubuntu
python reproduction/summarize_player.py --study build/combined-v1 --output build/combined-player.json
```

Here `reproduction/` denotes this folder's reproduction subdirectory; retain
the repository as the working directory. Build the observer using the repository's
`build_release_observer.py`, the recorded source and local simavr dependencies.
Admission output must be a fresh owned folder under ignored `build/`. The public
drivers preserve source/input guards, exact full-waveform caps and rollback
policy. They do not approximate decoder arithmetic or change the earlier frozen
campaigns. The result is evidence for this fixed bounded experiment, not a proof
of global optimality, an audibility score or a default-setting recommendation.
