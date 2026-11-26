# Compact LPX quality study

At fixed file size, the strict2k operator admits three changes in 27 cases:
two of 20 speech targets and one of seven negative controls. The P3 study finds
three promising raw candidates in eight source/target cases, including one
preferred in local listening, while all eight strictly protected results remain
their original files. The P3 local-scoring correction is retained as a tested
correctness fix; its isolated corpus comparison produces no quality gain.

This study compares the current converter's P3 accuracy policy and the separate
research strict2k Sparse80 profile. They are different encoders and formats.
All comparisons use each finished baseline's actual complete byte count, B0.
The nominal policy allowance is reported separately and is not extra free space.
No decoder, wire format or declared source-gain policy is changed.
The two profiles use different corpora; their absolute STOI values are not a
controlled comparison of one profile against the other. All reported changes
are paired within the same profile, source, target and actual byte ceiling.

## P3: local scoring and reachable spectral neighbors

Four public complete clips (`chego`, `otvechaesh`, `vinni`, `bread`) at 8 kHz
were encoded separately for PCM and PWM. Both arms returned byte-identical
baseline files in all eight cases, before and after the extra experimental
protection. This is a negative quality result, despite exercised candidates.

| Target and active measurement | Baseline bytes, four files | Canonical scoring | Reachable neighbors | Mean active STOI, all three |
| --- | ---: | ---: | ---: | ---: |
| PCM | 2,829 | 2,829 | 2,829 | 0.6461613210 |
| PWM | 2,817 | 2,817 | 2,817 | 0.6383196017 |

The first arm fixes a real encoder defect: `localCoefficients` used a temporary
default-accuracy stream to rank P3 trials. P3 actually applies an even grid and
a history-dependent temporal hold. The fix canonicalizes the whole P3 trial
before cropping its coefficient context. Simply changing the cropped stream's
accuracy would lose the preceding history. Non-P3 behavior is unchanged.

Independent tests found 258 coefficient / 240 forward-audio mismatches in 294
old reset/nonzero P3 crops and 108 / 96 in 480 real-prefix continuation crops.
The fix reduced both sets to zero; 882 non-P3 controls remained exact. This is
a correctness fix, not a measured corpus quality improvement. See
[the regression tests](tests/README.md) and [registered protocol](PROTOCOL.md).

The second arm uses separate experimental source overrides with P3-only
`{-4,-2,2,4}` LSF proposals and matching composition eligibility. It leaves
ordinary profiles, search bounds and complete-file selection unchanged.
Independent native tests verify legal effective edits, canonical holds,
continuation, invalid-composition rejection and unchanged non-P3 proposals.
The wider grid produces more candidates but no final file change. See
[protocol](P3_NEIGHBORS_PROTOCOL.md), [tests](tests/P3_NEIGHBORS_TESTS.md),
[results](results-neighbors-matrix.json) and [validation](validation-neighbors.json).

The [bit accounting](size-diagnostics.json) explains one limitation. Spectra
occupy only 5.98–7.27% of these complete files. Spare nominal allowances are
17–55 bytes, whereas enabling the first extra correction requires 28–76 bytes,
depending on the file. Every case has insufficient headroom: the presence bits
for all real pulse groups must also be paid. Increasing coefficient precision
alone does not establish a better allocation of the dominant excitation bits.
P3 is an accuracy policy using ordinary P4 wire syntax, not a strict3k preset.

Frozen first-arm evidence: [paired results](results-matrix.json),
[artifact validation](validation.json) and [benchmark runner](compare.py).
Each arm's pilot is an infrastructure check, not an extra independent sample.
Each P3 arm validates 90 retained LPX/PCM/model artifact hashes including its
separately recorded two-case pilot. Generated media and binaries are ignored.

## P3: existing fine-grid encoder at B0

The third, separately registered arm reuses the existing `encodeThreeK` routine
once per original baseline. Two physically identical host copies select
accuracy4; their packed bytes and native output must first remain identical to
the P3 incumbent. The search uses actual B0, bandwidth argument .97, the same
target and existing bounded candidate generation, without added passes.

This is a fresh spectrum/excitation allocation with an incumbent floor. It may
change pre-emphasis, pitch/scale, pulse values and spectral update cadence;
it is not a local odd-LSF-only experiment. The separate checker preserves legal
odd rank residuals rather than silently re-quantizing them as P3. Search errors
or malformed candidates retain and explicitly label the original baseline.
Raw returned streams and independently protected outputs are kept separate.
See [the prospective protocol](P3_ENSEMBLE_PROTOCOL.md).

The complete eight-case matrix produced three changed raw outputs, with no
errors or fallbacks. All protected outputs remained exactly the original
baseline. The raw results are promising tradeoffs, not admitted improvements.

| Target | Baseline bytes | Raw bytes | Protected bytes | Mean active STOI, baseline / raw / protected |
| --- | ---: | ---: | ---: | --- |
| PCM, four clips | 2,829 | 2,828 | 2,829 | 0.646161 / 0.662549 / 0.646161 |
| PWM, four clips | 2,817 | 2,813 | 2,817 | 0.638320 / 0.674346 / 0.638320 |

Chego PCM/PWM changes from 461 to 460 bytes; Vinni PWM changes from 1,083 to
1,080 bytes. Chego PCM SSE falls 60.33%, STOI rises 0.586210 to 0.651761 and
clipped samples fall 6 to 0. Nevertheless, lower retained band energy and newly
observed per-window octave labels trigger existing guards, as does the existing
complete selector. Vinni PWM is accepted by that selector but fails the extra
FullBand retention guard.

The separately labeled [posthoc diagnostic](ensemble-diagnostics.json) finds
no supported-band magnitude-error regression in any of the three candidates.
Every FullBand failure is caused by capped retention: the old output has at
least the source RMS in those bands, so its proxy saturates at 1; the new output
has less band energy even while its magnitude error is closer to the source.
For Vinni PWM the two affected bands carry only 0.710% and 0.735% of source
power; retention falls to 0.9649 and 0.7538, while band magnitude errors improve
70.3% and 63.5%. No new octave label occurs there. Chego adds one octave label
at 0.76–0.84 s relative to a baseline window with no finite detected period.
These are heuristic guard failures, not established audible regressions.
The frozen criteria and selection outcomes were not changed after seeing them;
listening is needed to assess the tradeoff.

See [results](results-ensemble-matrix.json),
[validation](validation-ensemble.json), and
[independent synthetic gate](tests/ENSEMBLE_TESTS.md). All 90 pilot/matrix
artifact hashes pass, and every protected LPX/PCM/model artifact is exactly its
own original baseline. The separate [listening exporter](make_listening.py)
wraps verified public reference/baseline/raw PCM in WAV without fitted gain,
delay or resampling. For PWM-target clips it uses the fixed duty-average
transfer, not a physical board recording. It writes nine WAVs and a manifest
to ignored `build/compact-quality/listening-ensemble/`:

```powershell
python Codecs/LPX/experimental/compact-quality/make_listening.py
```

These listening files are deliberately labeled rejected raw candidates;
the protected versions would duplicate the baselines exactly.

In one local, unblinded listening comparison on 2026-11-26, the experimental
Chego PCM candidate was preferred to the current P3 output. The original source
was also provided. This supports further investigation of that candidate policy
and distinguishes it from a purely numerical result; it is one listener on one
already measured clip, with no blinded or heldout listening evidence. It does
not retroactively change the registered admission criteria or protected files.

## Strict2k: four-innovation exhaustive search

This separate v8/mode15 experiment binds the exact final round 3 winners of the
saved 27-case November 2 campaign, rather than using weaker fresh encodes.
All 162 original best pointers and immutable round receipts are checked.
The original 20 speech / 7 negative-control membership and the ten heldout
speech cases are fixed. Each case has 32,000 samples at 8 kHz and keeps its
actual baseline byte count, which may already be below the 1,000-byte cap.

The saved prepared integer targets are verified and used unchanged. Original
raw-source paths are stale, so their preprocessing was not independently rerun.
Private audio, identities, paths, target/stream fingerprints and complete
search journals remain in ignored local storage. Retained reports contain only
anonymous ordinals, original groups, numerical evidence and software hashes.

At most four complete 320-sample frames are edited independently. For each of
their four existing 80-sample innovations, a frozen three-symbol pool includes
the incumbent and immediate/tail candidates from the original decoder state.
All 81 combinations per frame are evaluated with the unchanged suffix to EOF.
Only the existing seven-bit pulse fields are patched, preserving every other
original bit, including legal nonminimal Rice spelling and padding.
Every unique leaf is independently checked against both unchanged native
receivers via the explicit existing v8-to-v5/P6 expansion bridge. The native
servers do not directly parse Sparse80.

The whole-output quality shortlist is bounded at 12 changed exhaustive leaves.
Greedy/beam2/beam4 controls use the same pools, but prune on prefix PCM SSE
before their surviving leaves receive full-suffix scoring. This compares the
combined exhaustive/full-suffix operator with those controls; it does not
isolate pruning width from lookahead/objective choice. Each control is admitted
and reported independently, without pooling its wins into the exhaustive arm.

The dated synthetic witness demonstrates an actual recurrence difference,
not a speech-quality gain. See [mechanism protocol](sparse2/MECHANISM_PROTOCOL.md),
[mechanism validation](sparse2/MECHANISM_RESULTS.md),
[speech protocol](sparse2/SPEECH_PROTOCOL.md), and
[native bridge](sparse2/README.md).

All 27 searches completed with 3 admitted exhaustive changes: 2/20 speech,
both in the original ten-case heldout subset, and 1/7 negative controls.
Every output keeps its own exact baseline byte count; the total is 24,637 bytes.
Tuning speech and the fixed quiet/noisy variants remain unchanged. The gains
are very small numerical changes, with no strict2k listening validation.

| Subset | Cases | Bytes, before = after | Admitted changes | Mean PCM STOI, before / after | Mean PWM STOI, before / after |
| --- | ---: | ---: | ---: | --- | --- |
| Tuning speech | 10 | 9,495 | 0 | 0.671257 / 0.671257 | 0.644367 / 0.644367 |
| Heldout speech | 10 | 9,492 | 2 | 0.742212 / 0.742377 | 0.709840 / 0.710015 |
| Negative controls | 7 | 5,650 | 1 | Not assessed | Not assessed |

Heldout summed-energy SER changes from 3.996904 to 3.998953 dB on PCM and
3.974690 to 3.976809 dB on PWM. Do not interpret these approximately 0.002 dB
increases, or the 0.000175 PWM STOI increase, as an established audible gain.
Negative-control changes are numerical admissions, not music-quality evidence.
Greedy admits no changes; beam2 and beam4 each admit one negative-control change
and no speech change. These controls' outcomes are kept separate from exhaustive.

The workload includes 8,748 leaves, 55,296 symbol screens, 8,667 native oracle
calls (both receivers and both domains per call) and 447 complete metric
evaluations. Sum of per-case wall times is 815.05 s, of which 656.74 s is search
including mandatory model/native checks and 145.20 s is admission. Preparation,
compilation and final independent audits are separate. Reported 755.45 CPU
seconds cover the Python process, excluding the persistent WSL native processes.
These are host research costs, not AVR decoder timing.

See the anonymous [complete matrix](sparse2/results-matrix.json) and
[read-only artifact validation](sparse2/validation-matrix.json). The original pilot is
included exactly once. Exhaustive/full-suffix scoring beats beam4's restricted
survivor score in 29/108 regions; the different prefix pruning and suffix
objectives prevent attributing that difference to pruning width alone.
The final validator passes all 8,748 original bitmask/length checks, 85 unique
native/model raw/final replays, 216 variant checks and 108 topology-specific
final-floor checks. It regenerates the public rows and aggregates from the
immutable journals; it does not rerun search or full speech analysis. The
read-only validation took 89.91 s, outside the encoding-work totals above.

The complete corpus is not bundled. Reproduction requires the original local
saved campaign and its exact prepared targets; a fresh encode or unrelated WAV
is not equivalent evidence. With those inputs and the existing Python codec
dependencies, [run_campaign.py](sparse2/run_campaign.py) exposes `prepare`,
`pilot`, `all` and `export` commands. Use a dedicated ignored `--output` folder
and provide `--campaign` only for preparation. Preparation freezes software,
target/predecessor bindings and baseline metrics before search. A verified pilot
is reused once by `all`; it is not searched again. The separate read-only
[validator](sparse2/validate_results.py) checks original bit masks, immutable
artifacts, native/model raw/final output, each topology's own admission floors
and every anonymous aggregate after the complete pass.

Public synthetic mechanism tests do not require the private corpus:

```powershell
python Codecs/LPX/experimental/compact-quality/sparse2/test_mechanism.py --packages C:/Work/MicroMusic/build/codec-python
```

Build the two native reference servers first as described in the bridge README.

## Admission and scope

The P3 research wrapper is stricter than the production combined selector:
it also requires the active path's SSE, STOI, old-noise and FullBand floors,
pitch/level/clipping/stability checks and actual B0. Inactive PWM measurements
do not select PCM-target outputs. Raw candidates and protected outputs must be
read separately. The unchanged production selector is not claimed to enforce
every extra research floor itself.

Strict2k reuses its existing complete PCM/PWM SSE and available STOI floors,
source-frozen voice checks, clipping, fixed PWM band totals, burst maxima and
every real tail-window floor. Changed PWM and strict improvement of both old
joint objectives are required. No case, unchanged output or failed score is
dropped from a denominator to improve an aggregate. Speech SER uses summed
energies; music controls do not receive a speech-intelligibility claim.

Native/model equality and unchanged decoder source do not establish equal AVR
cycles for changed data. Spectral update cadence, packet types, gain and
saturation can affect work. No new ATtiny88/ATmega328P interrupt, underrun,
Flash/stack or physical-board support is claimed by these host experiments.
Single-run host times describe these runs and are not controlled speed ratios.
STOI, error and objective changes are proxies, not a percentage improvement in
perceived quality. A broad audible-quality claim requires listening and unseen
sources. Nothing here is pushed, merged into production or deployed.
