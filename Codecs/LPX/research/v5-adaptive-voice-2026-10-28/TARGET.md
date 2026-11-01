# Adaptive voice search: targeted endpoint evidence

The unified controller improves the measured reconstruction of the existing
four-second listening target within its declared byte ceilings. This is one
tuning source, not independent corpus evidence. The source target is the same
explicitly amplified recording (gain 64) used for every control and candidate;
no output gain is fitted and no samples are trimmed.

| Endpoint | Data bytes | Full Flash, normal / +100 IRQ | Correct-period windows, PCM / PWM | PCM SER, dB |
|---|---:|---:|---:|---:|
| Accepted V1 control | 1702 | 6276 / 6284 | 58 / 57 | 6.636 |
| A, ceiling 1800 | 1710 | 6284 / 6292 | 61 / 59 | 7.417 |
| Ceiling 1930 | 1930 | 6504 / 6512 | 64 / 62 | 8.264 |
| B, ceiling 2060 | 2060 | 6634 / 6642 | 67 / 65 | 8.418 |

The source has 77 reliably assessed period windows. The table counts decoded
windows within 100 cents of those source periods. Missing or wrong decoded
periods remain failures; this is not a claim that every window preserves pitch.
All endpoints have zero full-scale clipped samples. Their complete PCM/PWM
SSE and available STOI floors pass against the accepted V1 control. The shared
voice/noise score decreases, but it is a proxy, not a percentage of audible
quality. Detailed numerical results are in [target-endpoints.json](target-endpoints.json).

A grows by **8 bytes of complete Flash** versus the accepted 1702-byte stream;
it fits the original 1800-byte data ceiling. This is a fixed-ceiling comparison,
not identical payload size. The other two endpoints add 228 and 358 Flash bytes.
Program size stays 4574 / 4582 bytes and static SRAM stays 756 bytes. All six new
images and two exact control reuses pass physical PWM/EOF/tick/queue/stack and
interrupt-active playback checks with no underruns or errors. These are the
verified simulator profiles; no analog-board listening or portable-C real-time
claim follows. [Complete player evidence](../v5-adaptive-target-player-2026-10-30/README.md).

The user compared A and B at the same declared gain and answered **"hard to
say"**. That pair does not establish a perceptible benefit for B's extra bytes.
The larger stream is not adopted on listening evidence. Both earlier feedback
points remain valid: amplification made the new encoding much better than the
old result, while its reconstruction still sounded rougher than the original.

The frozen implementation is `5a6cd1ab`. Each ceiling used four refinement calls
and 38 distinct measured pool entries, with no new seed fits. Summed timed
refinement regions are 55.09 seconds; this excludes input loading and native
library preparation. It is not a global optimum or a same-time comparison with
an unbounded search. The complete target pool was not retained, so its selection
trace is not independently audited from all pool bytes. The retained endpoints
are independently rechecked against source-bound reports, both native layouts
and the integer model: 16 output-domain comparisons / 512000 compared samples.

The source-bound [endpoint projector](reproduction/summarize_target.py) performs
no fitting/refinement and publishes only anonymous numeric results and source
code provenance. Actual media, input/stream/image fingerprints, private bindings
and audio remain in ignored build storage. The separate predeclared corpus run
retains all candidate bytes and requires a complete independent pool audit;
these targeted results do not replace it.
