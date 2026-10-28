# V1 quiet/voice frontend: bounded first stage

The conservative V1 grid retains **all 98 original-level controls**. That is
successful rollback, **not proof that those streams preserve the source's
voice character**. In the separate amplified-target cohort, all eight profile
groups fit the original full-byte budget, four fit 95%, and none fit 90%.
Only one selected stream differs from its fresh control at the same amplified
target level. V1 is a measured first stage/control; it does not finish the
remaining rasp/timbre work being pursued in V2's unified search.

The user found the new targeted example much better than the older encoded
example, while still hearing roughness and a result worse than the original.
Both observations are retained. They concern one informal targeted comparison,
with a declared level change, rather than a blinded, volume-matched corpus
listening study. The earlier near-equal A/B observation concerns two older
encoded alternatives and is compatible with this later source comparison.

## Scope and controls

The [predeclared protocol](PROTOCOL.md), frozen frontend `5b4800f7`, fixed
pre grid 0/8192/13926 and fixed VoiceObjective were not changed during the run.
The original speech set contains **49 references / 98 profile groups / 118
actual reset segments**, covering 2,632,296 original samples, or 329.037 s.
Profile-group sample totals count each reference in profiles 4 and 6. Sources,
repeated profiles and the four-recording additional cohort are not asserted to
be statistically independent speakers.

All 98 preserve-mode groups retain original level and full length. Eight
additional auto groups cover the four whole sources below 256 PCM16-count AC
RMS; their declared gains are 16, 32, 16 and 64. These are currently single-reset
sources. Each auto control is freshly encoded at the **same declared amplified
target** as its alternatives. Original quiet controls remain separate context,
never relabeled as an amplified-target quality control. There is no fitted
output gain, resampling, trimming or independently amplified reset segment.

Both profiles of the user-targeted source are marked explicitly. That source
is not untouched held-out evidence for the new choices. Named tuning/evaluation/
additional splits remain in the data; the targeted flag must also be respected.

## Actual finite-pool outcomes

Each record has at most three whole chains: control, concatenated per-segment
selected output, and concatenated raw output. No combinatorial mixture or
cap-specific reoptimization was added. Complete target PCM/PWM metrics, both
voice-proxy domains, objective and exact byte totals decide whole-chain
admission. Local success alone never promotes a chain.

| View / cap | Groups | Automatic admissions | Byte fit but only tradeoff | No byte fit |
| --- | ---: | ---: | ---: | ---: |
| Preserve / 100% | 98 | 98 controls | 0 | 0 |
| Preserve / 95% | 98 | 0 | 22 | 76 |
| Preserve / 90% | 98 | 0 | 6 | 92 |
| Amplified target / 100% | 8 | 8 | 0 | 0 |
| Amplified target / 95% | 8 | 4 | 0 | 4 |
| Amplified target / 90% | 8 | 0 | 0 | 8 |
| Chosen active policy / 100% | 98 | 98 | 0 | 0 |
| Chosen active policy / 95% | 98 | 4 | 18 | 76 |
| Chosen active policy / 90% | 98 | 0 | 6 | 92 |

The active-policy view follows the user's choice to amplify quiet input: **90
existing preserve rows plus eight existing amplified-target rows**. It replaces
the eight quiet preserve rows rather than adding them. No extra fitting or new
independent signals are attributed to that view. Its row-carried 362 fits are
part of the actual 386-fit study, not a separate 362-fit execution.
At the frozen V1 epoch the CLI default was still preserve; the auto variant
was invoked explicitly. The chosen-policy view does not rewrite that historical
setting or represent a separately executed default switch.

At 100%, eight active-policy outputs differ from their original-level streams;
all eight have an intentional level change. Seven are their fresh matching-level
legacy controls. Only the targeted profile-4 result changes beyond that control:
1,698 -> 1,702 stored bytes. Against the original 1,800-byte budget basis it fits
100% and 95%; the 90% cap is unmet. This is not a same-level quality comparison
against the old quiet output.

The active-policy sum of streams is 366,289 B versus 367,028 B for the original
98 alternatives. These are benchmark alternatives, not one firmware image or
a measured full-Flash saving. Per-group metrics refer to their matching target;
**no SSE quality gain is aggregated across original and amplified levels**.
Missing selections remain null in the files. A finite-pool no-fit result is not
proof that an acceptable smaller stream cannot exist.

## Periodicity still has limits

Two preserve profile groups have no confidence-accepted source period. They
remain unassessed, not pitch successes. The independent audit counts six such
role-chain contexts because each group has three role entries. Existing
preserve controls also include two groups with source candidates but no paired
native-PCM candidates, and four such groups after PWM. Keeping those controls
does not cure their original distortion.

| Selected 100% view | Source candidate windows | Native PCM within 100 cents | Fixed PWM within 100 cents |
| --- | ---: | ---: | ---: |
| Original-level preserve | 8,950 | 6,381 | 5,670 |
| Declared amplified-target cohort | 1,342 | 1,108 | 1,076 |
| Chosen active-policy view | 8,950 | 6,970 | 6,631 |

These are overlapping, profile-group diagnostic windows, not independent
observations, validated true F0 or perceived-quality percentages. The views
contain different target-level policies. Full coverage, missing output periods,
collapsed frames and null paired errors remain explicit in
[summary.json](summary.json) and [groups.json](groups.json).

The targeted profile-4 output has 59 paired native-PCM candidates, **58/77 within
the 100-cent diagnostic tolerance**, and 57/77 within tolerance after PWM; the
median absolute paired PCM error is about 2.07 cents. Its profile-6 fresh target
control has 69/77 within tolerance in both domains, median about 1.58 cents.
These counts leave missing/wrong periods and remaining roughness visible.
The direct target-PWM diagnostic is retained to separate source/output
resolution limits from encoder loss.

## Validation and measured work

Preparation built generic common and v5-only native libraries once. The two
workers executed **354 preserve fits plus 32 auto fits = 386 fits**, with zero
reuse, prior incomplete attempts or hidden additional fits. Preserve work
included 1,888 explicit complete-chain native output-domain comparisons; auto
added 128. Original full PCM/PWM fingerprints, all real reset boundaries,
mandatory stored tails, byte caps and complete sample lengths were checked.

The [separate independent audit](../quiet-voice-v1-independent-audit-2026-10-28/README.md)
and its [corpus](../quiet-voice-v1-independent-audit-2026-10-28/audit.json) and
[context](../quiet-voice-v1-independent-audit-2026-10-28/context-audit.json)
receipts pass. It freshly checked 499 unique streams / 22,370,368 samples through
model/common/v5 native PCM/PWM, made 1,996 domain comparisons, rederived all
318 cap/priority decisions, and verified local trials, full metrics, voice
proxies, objective components, runtime, input bindings and attempt inventory.
It did not call the fitter's aggregation or selection helpers. Its 216.20 s
recheck is validation of existing signals, not more independent fitting data.

Worker wall times were 923.02 and 720.49 s after their initial startup guards;
they include encoding, validation, metrics and per-record guards. They overlap
and must not be added as elapsed time. Process CPU and a matched search-only
speed comparison were not measured. Candidate encoder timings remain descriptive.

Production MCU source and v5 syntax remain unchanged. This host study makes
no AVR timing, analog-board, full linked Flash/SRAM or universal voice-preservation
claim. Parent-owned complete-player admissions are a separate stage; playback
success never promotes a raw quality tradeoff.

## Saved evidence

[groups.json](groups.json) retains every anonymous control/selected/raw role,
whole cap, failed floor, null and local generation summary. The exact projection
tool is [reproduction/summarize_corpus.py](reproduction/summarize_corpus.py).
[source-runtime.json](source-runtime.json) pins code, packages, generic native
libraries and the projection. The raw local compiler version/wrapper line and
all original paths/identities, binding/recording/stream/PCM fingerprints, media
and detailed caches remain private. Generic decoder libraries contain no audio.

The [runner](reproduction/run_corpus.py) imports its configurable source root
without copying the core. [Contract tests](reproduction/test_protocol.py) cover
global caps, rollback/null behavior, real tails, paired source sharding,
successful capture order/ownership, stale cache/report rejection, numeric
binding and wrong-worktree import rejection. Adding this report changed none
of the guarded V1 core, runner, protocol or test files.
