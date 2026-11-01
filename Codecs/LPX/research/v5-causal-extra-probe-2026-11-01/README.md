# Synthetic causal extra-pulse position probe

A legal profile 4 fixture demonstrates a missing candidate position in one
unchanged refit pass. Adding the actual mandatory-pulse positions reaches the
exact legal target at the same complete bytes. No qualifying profile 6 fixture
was found within the separately fixed 120-case bound. This is a constructive
synthetic mechanism result, not a corpus, bitrate, quality or audibility claim.

The [protocol](PROTOCOL.md) was committed before outcomes as 487f913f. The driver
and recipe were frozen as 793080ba before the single bounded execution. Source
epoch 654ada493202f565d24cb9dcf22f16137c825329 is checked against tools/tests/src.
The original adapt_excitation remains unchanged and callable. The prototype is
generated under ignored build storage from that exact function by adding only
a guarded insertion of the two actual mandatory positions. With the guard off,
both profiles' warm calls preserve original fields, bytes and trial counts.

## Reproducible counterexample

Use recipe case 30, profile 4:640 samples; spectral codes
[1,2,4,6,8,10,13,17,23,29] repeated twice; four parameter rows [8,40,0];
pre=bright=0. All 32 mandatory pulses have position 5 and alternating +8/-8
amplitudes, except positive pulse 10 has position 0. All 16 extras are inactive
except extra 5, initially at position 30 with amplitude -8. The legal target moves
only that extra to position 0. It cancels the positive mandatory pulse before q
saturation. See [recipe.py](recipe.py) for the exact deterministic fields/grid.

Refit samples 200..239 with horizon 160 and the real baseline state after samples
0..199. This avoids a parameter-row boundary. Target and baseline share the
entire prefix and filter/spectral/base fields. Their first output difference is
at group offset 0, but the largest output error is at offset 14. The old optional
position set is [14,29,30,31]; the prototype adds [0,25]. Gain/pre/bright are
zero and all compared outputs are unclipped, leaving LPC as the spreading stage.

| Result | Bytes / fixed cap | Payload bits | Active extras | Full PCM SSE | PWM bytes differing from target | Trial evaluations |
|---|---:|---:|---:|---:|---:|---:|
| Baseline |57 /57|275|1|3,787,164|not used for the success criterion|not a refit|
| Old complete refit |57 /57|275|1|2,682,956|170|43|
| Mandatory-position prototype |57 /57|275|1|0|0|57|

The old refit flips mandatory pulse 10 to -8, moves pulse 11 from 5 to 3 and changes
extra 5 to [30,4]. Its final file still has one extra; it does not gain an unfair
byte reduction by removing it. The prototype leaves all mandatory/parameter
fields unchanged and sets extra 5 to [0,-8], exactly the target. Both complete
serialized files and the target are 57 bytes, with no file truncation or cap
relaxation. The 14 extra trials are exactly two additional positions times seven
allowed extra amplitudes; this additional work is paid.

Every distinct serialized synthetic endpoint was checked against model, common
native and v5-only native PCM/PWM. Complete source/prefix/geometry/header/file
checks passed. Host native uses the separately pinned callback-enabled C recipe,
with assembly disabled; this is not a new AVR image, timer or hardware test.

## Bound, negative result and costs

Profile 4 stopped at its first counterexample after 31 cases; its first 30 cases
had clipped baseline and target outputs and were rejected. Profile 6 examined all
120 cases without a qualifying delayed missing-position case. Ninety had clipped
baseline/target outputs; in all 120 the error peak was not later than the causal
position. These rejection counts overlap. No measured profile 6 refit comparison
was run because the fixed eligibility condition never passed. This bounded
negative result says nothing about all possible profile 6 signals or refitters.
The grid was not retuned or extended.

The complete run used 151 cases, six separately paid baseline-reference warm
refits and two measured refits. All eight calls completed. It verified 228
distinct streams,145,920 model samples and 912 common/v5 native domain
comparisons. There were no corpus audio/stream reads, initial fits, native builds,
target jobs or default changes. Closed native source/build metadata and binary
fingerprints were reused, with no corpus signal opened. Five research contracts
passed, including actual native-source closure and clean import without codecs.

Total cost was 11.49285 wall /10.0 process CPU seconds: setup 2.18103/1.640625,
warmup 6.71293/6.625, measured search/verification 1.62305/1.53125. Individual old
and prototype refit walls were about 0.181 and 0.227 ms; both reported 0 CPU seconds
at the available sampling granularity. This does not mean zero CPU work and
does not establish a stable timing ratio or matched-CPU benefit. Trial counts
are the reliable measured work difference in this small fixture.

## Reproduction and limits

Use the project dependency/thread bootstrap and a fresh ignored output:

```text
python probe.py --source-root <654-source-worktree> --native-cases <closed-native-metadata> --output build/causal-extra/probe-v1
```

Set CAUSAL_NATIVE_CASES to enable the native metadata/source contract when running
`python -m unittest discover -s <probe-package> -p "test_*.py"`. The original
refitter, disabled prototype and mandatory-position prototype remain explicitly
separate. Full generated source, streams, exact fingerprints, native receipts,
every examined case and costs stay private in ignored build. Compact numeric
evidence is in [results.json](results.json). Session 11209 exited 0 and all source,
artifact, native and forbidden-fit/build guards passed. No retry occurred.

This demonstrates that output-error peaks can omit a causal excitation location
under LPC. It does not show how often that happens in recordings, whether the
extra trials help under the same CPU budget, or whether sound improves. Any
production/corpus experiment needs a separately frozen proposal and fair costs;
this probe changes no encoder default and makes no perceptual claim.
