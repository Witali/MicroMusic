# P4 existing-extra whole-pass pilot

The causal-position pass did not add a useful point to the prior V1 plus anchor
size/quality frontier. This conclusion covers every saved whole candidate, not
only the selected outputs. Keep controller/default behavior unchanged; this
pilot supplies no reason for target jobs or an audible-quality claim.

Both arms completed the six original P4 contexts and all ten reset helpers,
using the identical pre-pilot baselines/levels. Each visited all 681 eligible
active played groups under the common 33,369-trial ceiling without a CPU cutoff.
There were twelve arm records, twenty corpus helpers and exactly thirty-six
ordered 100/95/90 cap decisions. All speech selections retained their input.

## Complete saved frontier result

The saved-only audit reproduced all nine-role pools from exact callback bytes,
all full gates and decisions, durable intermediate admissions and exact
target/context/ordered-byte metric-cache origins. The 61 whole rows represent 54
distinct context/ordered-byte tuples: six inputs and 48 changed tuples. The old
comparison includes all 92 saved admissible V1/anchor rows, rechecked against
the fresh common input anchor, including nonselected and above-B points.

- Of the 48 changed tuples, 47 fail unchanged admission gates. The sole admitted
  changed tuple is dominated by the old frontier. No selected or nonselected
  point extends that frontier.
- At 100%, the prior union has a lower joint score in ten of twelve views; two
  are equal-size score rank ties within 1e-12. Rank ties do not imply PCM or
  stream identity.
- All 24 new reduced-cap views are actual no-fit at 95% and 90%. The old
  admissible union also has no choice at those caps. There is no preserved-quality
  data reduction from this pass.

The one changed admission is the legacy arm on NS ordinal 10, at the same 635
bytes. Against its input it lowers PCM SSE by 22,415,172 (1.2046%) and PWM SSE by
18,814,976 (0.9687%), raising SER by 0.05263/0.04228 dB. Joint score changes from
0.940666123 to 0.940580269. This is a small numerical own-control improvement;
the old union already has a better 635-byte point at 0.939319579, plus admissible
634/633-byte tradeoffs. The causal arm retains this context's input.

## Why lower local error did not suffice

Among the 48 distinct changed tuples, 33 lower full PCM SSE and 32 lower full
PWM SSE; 15/16 increase those respective errors. Only thirteen become smaller,
by one or two actual bytes; the other 35 keep their input size. All thirteen
smaller tuples are rejected. Full PCM SSE deltas range from -7,988,418,068 to
+41,387,160; PWM deltas range from -8,275,554,816 to +42,087,424. The individual
byte/SSE movements are retained in [rows.json](rows.json).

Rejection counts below overlap; their sum is not the number of rejected tuples.
The first row is the combined old quality gate, and subsequent SSE/STOI rows
describe its subfloors. All counts concern the same 48 distinct changed tuples.

| Failed floor | Tuples |
| --- | ---: |
| Combined PCM/PWM SSE/STOI | 39 |
| PCM SSE | 15 |
| PWM SSE | 16 |
| PCM STOI | 25 |
| PWM STOI | 23 |
| Joint voice/noise objective | 21 |
| PCM period coverage | 12 |
| PWM period coverage | 9 |
| Clipping | 0 |

These saved outcomes support a local-objective/whole-admission mismatch as a
follow-up hypothesis. They do not establish a perceptual failure mechanism or
justify relaxing any floor. The deterministic synthetic cancellation benefit
remains separate from this negative six-context corpus result.

## Work, costs and provenance

| Work | Legacy | Causal |
| --- | ---: | ---: |
| Eligible / visited groups | 681 / 681 | 681 / 681 |
| Actual trial evaluations | 18,964 | 27,290 |
| Changed active groups in working pass | 316 | 325 |
| Actual helper CPU seconds | 10.40625 | 10.109375 |
| Callback persistence CPU, included above | 0.296875 | 0.171875 |
| Catalogue SSE/native audit CPU seconds | 2.9375 | 2.875 |
| Whole admission/persistence CPU seconds | 30.5 | 32.515625 |
| Record workflow CPU seconds | 54.34375 | 55.328125 |
| Producer main CPU seconds | 58.515625 | 60.078125 |
| Required wrapper main CPU seconds | 60.234375 | 62.015625 |

This is full coverage with differing actual trial work, not a matched-CPU
comparison or evidence that the causal algorithm is faster. Helper CPU totals
20.515625 seconds; record workflows total 109.671875; producer mains total
118.59375; wrapper mains total 122.25. These are different accounting scopes.
Individual worker walls are recorded separately and are not summed into campaign
elapsed time. Callback persistence remains inside helper timing.

The producers made 61 fresh whole metric rows and twelve exact whole-cache hits,
with no reuse of old whole metrics as fresh results. Each arm independently
verified 49 unique reset streams in common/v5 PCM/PWM (196 domain comparisons).
The final postcheck made zero new synthesis, metrics, helpers, builds or targets.
Its measured cost was 9.3374 wall / 7.46875 CPU seconds.

Paid synthetic accounting is eighteen calls: six historical source-3f256c1d
preflight calls, six successful retention-source v2 preflight calls and six
worker warm calls. The historical successful v1 receipts remain intact; they
were superseded for pre-corpus I/O retention and strict admission, not retried
corpus work. Both metadata preparations, both preflights and the read-only
admission-review costs are separately recorded once in [summary.json](summary.json).
Root's separate long-prefix synthetic diagnostic is outside these counts.

Numerical production stayed at `de78a323`; the producer research source stayed
at `5930fa96`, required admission entry at `c4f624e8`, and this saved-only
projection at `a24dc681`. The original protocol/initial harness are
`0c041e48`/`3f256c1d`. Execution uses an exact de78 checkout; later source bytes
must not be accepted by weakening its guard. Eighteen producer/retention
contracts, seven admission contracts and five frontier contracts pass.

The admitted worker sessions 25082 (legacy) and 55966 (causal) both exited zero.
Saved-only projection session 70411 exited zero and its final binding/marker are
PASS/complete. There were no real-helper repeats, initial fits, native builds,
target jobs or gate changes. Prior saved measurements retain their explicit
unchanged DSP/metric/native/runtime bridge and remain labelled old evidence.

[prior-frontiers.json](prior-frontiers.json) retains the complete anonymous prior
frontiers, including distinct actual tuples at rank ties. The generated public
JSON files are exact projections of the closed private export. Media, private
identities/paths/fingerprints and spatial group/sample lists remain ignored.
