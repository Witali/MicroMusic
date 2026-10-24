# Equal-rate clock arithmetic experiment

The candidate is rejected. It bypasses multiply/divide for equal rates:
`floor((a*d+carry)/d)=a` when `carry<d`, and
`ceil((units*d-phase)/d)=units` for positive units and `phase<d`.
Zero units and invalid arguments retain the existing contract.
No device register, source-clock edge or peripheral event is removed.

The candidate passed all 1633 Node checks, including a new independent BigInt
oracle covering full-width counters, proper/improper carries and invalid
phases. Its WASM is 117923 bytes, 22 bytes larger than the baseline, with the
same 109 function exports, no imports and two fixed memory pages. The isolated
rebuild reproduces every byte; its SHA-256 is
`74b1dde3ef4ffb04110ef3e337a8b70aa19f93623ce1f19ed0b861bf62f8c430`.

## Performance decision

Baseline: `464add5`, runtime SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.
Four labels use shared Module objects within identical-binary pairs, equal
warmups, fresh instances and balanced trial positions/adjacent pairs.
Cross-version ratios above one favor the candidate.

| Case | Old identity | New identity | Cross ratio | Candidate faster |
|---|---:|---:|---:|---:|
| rhythmic-compatible | 1.002 | 0.998 | 0.996x | 6/16 |
| rhythmic-physical | 1.000 | 0.998 | 0.967x | 0/16 |
| lumiere-stereo-compatible | 1.001 | 0.998 | 0.996x | 3/16 |
| lumiere-stereo-physical | 0.992 | 0.993 | 0.960x | 1/16 |
| hq4-chego-auto-compatible | 0.995 | 1.007 | 1.002x | 9/16 |
| hq4-chego-auto-physical | 1.005 | 0.992 | 0.980x | 0/16 |

The HQ4 case name resolves through the catalog alias to `hq4-chego-tiny`;
its actual firmware hash is recorded. Across these six completed cases, 384
timed runs and 96 discarded warmups retain 5688 exact PCM/state/pin checkpoints.
All three physical audio cases regress; the ordinary cases establish no gain.
Sampling had identified a hot containing function, not a profitable condition
inside it. These measurements do not isolate the cause to an instruction or
prove exclusive subsystem costs.

The 13-case run was stopped after these six complete cases. Its raw
`complete:false` marker is retained; an unpersisted in-progress case is
discarded. Direct kernels, CLKI and active-ADC performance cases were not
completed. They are unnecessary to reject this candidate and are not claimed
as measured. This is an early rejection, not a complete acceptance matrix.

Production header, WASM and manifest were restored byte-for-byte to the
baseline. The new arithmetic boundary test remains useful independently;
it and the three control-design checks pass against the restored implementation
(six tests total). The 1633-test full run applies to the rejected candidate;
the restored core retains its prior 1632-test result, plus these focused checks.

## Evidence and reproduction

[Analysis](clock-identity-20261024/analysis.json) describes the stop decision.
The adjacent raw benchmark, exact harness, candidate header/patch, manifest,
binary and full test log preserve the experiment. To rebuild it in an ignored
directory without modifying production:

```powershell
node web-player/reports/clock-identity-20261024/verify-evidence.mjs
node web-player/reports/clock-identity-20261024/rebuild-candidate.mjs
node --test web-player/tests/device-clock.test.mjs web-player/tests/runtime-control-design.test.mjs
```

The recorded benchmark invocation is
`--baseline-ref 464add5 --change-set clock-identity --trials 16 --warmups 4`.
Its source-change assertion intentionally rejects the restored checkout;
repeating timings requires supplying the archived candidate first.

The next isolated hypothesis is to avoid the overflow-check division for
32-bit multiplicands. Their product fits 64 bits, so an unsigned addition
overflow check can qualify the short path even with a 64-bit carry. Larger
operands retain the existing wide path. This is unimplemented and unmeasured;
test product/addition boundaries independently and retain the full CLKI/ADC
controls before accepting it. The MCU plan remains 21/30 complete.
