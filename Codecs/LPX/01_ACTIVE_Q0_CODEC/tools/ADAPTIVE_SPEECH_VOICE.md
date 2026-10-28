# Unified bounded voice search

The default `encode_speech_voice.py` CLI now runs one adaptive host controller.
It chooses the declared whole-input level before PCM16 quantization, fits the
existing three pre-emphasis seeds with consistent LPC analysis, and explores
header filters, joint LPC/excitation changes and optional excitation in the existing v5 format.
The original control remains in the measured pool. No MCU code or format changes.

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py input.wav build/voice --baseline old.l4hy --max-bytes 1800
```

The input gain defaults to the user-approved `auto-quiet` policy. Use
`--level-policy preserve` when playback level must stay unchanged. A raised
target is compared with a freshly encoded control at that same declared level;
an old original-level stream supplies only the default complete-byte ceiling.
The conservative grid winner becomes the refinement admission anchor, preserving
its PCM/PWM metric and period-coverage floors. If the grid has no feasible winner,
the legacy control remains the anchor even when it exceeds the requested cap.

The shared ranking averages VoiceObjective plus source harmonic/noise-balance
error across native PCM16 and the fixed PWM output. Missing source pitch stays
unknown. Existing complete PCM/PWM SSE and available STOI floors, nondecreasing
source-period coverage, no larger joint score, and no additional full-scale clipping are admission
conditions. Coarse spectral/collapsed-window descriptors remain visible rather
than requiring all correlated proxies to improve independently. This explicitly
differs from the stricter historical V1 grid gate. No listening quality is inferred
from a numerical score alone.
`--non-speech` disables STOI throughout both pool evaluation and internal
operator acceptance; waveform, spectral, noise and period descriptors remain.

Every contender is fully serialized, checked against actual native/model output,
and compared with this exact source target. Duplicate streams are evaluated
once. The report retains an admissible size/score Pareto frontier, rejected raw
alternatives, stage provenance and work counters. It selects the best measured
admissible score within the ceiling, breaking ties by smaller size and stable
discovery order. It does not claim global optimality or minimum required bitrate.

Each iteration prioritizes the best measured admissible feasible candidate;
remaining raw candidates stay available after its unattempted operators. It first
tries extra pulses when the complete marker layer and at least one value fit;
then header-filter changes and joint LPC/excitation refinement. It alternates
operators before repeating the producing operator on a changed descendant.
Existing extras are preserved and can be jointly refitted; they are never
silently removed by the legacy adapter.
Changed outputs join the same candidate pool. Previously attempted stream/operator
pairs are not repeated. A no-capacity extra search is skipped without spending a
refinement call. A profile is kept fixed for this invocation.

`--refinement-calls` defaults to 4 and limits expensive operator calls, including
calls that return an unchanged stream. Each LPC call uses the named `expanded`
preset (64 anchors, 4 spectral finalists, 1280-sample lookahead, 160-sample
excitation horizon, 2 passes). Each extra call uses a 320-sample horizon, 6
position finalists, batches of 16 and at most 128 full evaluations.
Header calls screen at most 256 legal filter pairs and measure full metrics on
at most 16 finalists; these finalists also enter the shared voice/noise ranking.
Internal local renders and complete metric evaluations are reported separately. These
are finite work bounds, not a wall-time guarantee. Zero calls retains the
measured seed pool. `--search-mode grid` retains the historical seed-only gate.

`adaptive_speech_voice.refine_candidates` accepts saved seed streams for
reproducible studies without repeating their fitting. It revalidates every seed
and never trusts cached quality claims. Its optional `firmware_cost(blob)`
callback must supply an actual complete image size to enforce `max_flash_bytes`;
a Flash ceiling without this callback is rejected. Ordinary CLI byte caps cover
the stream only. Selected outputs still need actual complete-player Flash/SRAM
and interrupt-active playback admission before a hardware-support claim.
An optional `candidate_sink(blob)` receives each distinct verified pool stream
in report ID order, enabling independent reproduction without retaining every
internal screening probe. Saved streams and their fingerprints remain private.

One invocation covers at most 64000 samples. Long chains need one whole-input
gain and a separate whole-chain admission; locally good segments do not establish
whole-record metric or size feasibility. Generated source audio, streams, player
images and detailed private receipts belong in ignored `build/`.
