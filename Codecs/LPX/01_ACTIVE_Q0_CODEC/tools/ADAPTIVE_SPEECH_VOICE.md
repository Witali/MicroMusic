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
once. The report retains an admissible serialized-data-byte/score Pareto frontier, rejected raw
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
a Flash ceiling without this callback is rejected. This callback filters full
image feasibility; the reported frontier and size tie-break still use serialized
data bytes even when Flash is measured. They are not a complete-image Pareto
frontier. Ordinary CLI byte caps cover
the stream only. Selected outputs still need actual complete-player Flash/SRAM
and interrupt-active playback admission before a hardware-support claim.
An optional `candidate_sink(blob)` receives each distinct verified pool stream
in report ID order, enabling independent reproduction without retaining every
internal screening probe. Saved streams and their fingerprints remain private.

## Retained intermediate chains

The single-stream API still covers at most 64000 samples. The same CLI can now
refine an existing ordered reset chain, including longer recordings:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py input.wav build/chain --profile 6 --max-bytes 24000 --baseline-chain segment-000.l4hy segment-001.l4hy
```

`--baseline-chain` accepts 1..255 v5 files in playback order and preserves each
reset's sample count/profile. The files must cover the complete source after
resampling. It is mutually exclusive with `--baseline` and requires adaptive
mode. The default complete data cap is the sum of supplied file sizes. The input
receives one gain before segmentation; changed gain requires fresh legacy
controls at that target level. Segments are never independently amplified.

`adaptive_speech_chain.encode` performs those seed grids and calls
`refine_candidates`. The latter can reuse existing per-reset seed pools and
anchors without initial fitting. Each local controller runs once, under the
whole data cap (bounded by the 65535-byte per-stream limit), and captures its
verified pool. Whole candidates include the immutable baseline and selected/raw
snapshots after every common completed-call depth, including zero. Unsearched
resets stay byte-identical to baseline. A locally rejected raw snapshot can
still be tested against whole-record gates. There is no independent mixture of
different search depths or proportional division of the byte cap.

Every distinct ordered byte chain gets fresh full-record PCM16/PWM metrics,
period coverage, clipping and the shared voice/noise objective. The complete
quality gates compare against the immutable whole baseline. Exact reset bytes
can share native/model verification inside this call; different serializations
never share whole metric rows. Ties use score, actual total bytes and stable
discovery order. Missing feasible output remains absent. Earlier feasible
snapshots therefore survive deeper exploration with the same seeds, target and
settings. Earlier results from different runs can be passed explicitly as
`incumbents`; their whole output and quality are rechecked, not trusted.

`select_candidates` accepts saved local histories (`index`, actual `pool`
streams in ID order, and `report`) for reproducible replay. Their local scores
only define snapshot recipes; they do not establish whole quality. Sparse
histories are supported. Candidate provenance and actual work counters are in
the report. The optional complete-chain `firmware_cost(streams)` callback and
`max_flash_bytes` enforce measured image feasibility; a guessed program constant
is not accepted as a substitute. The reported frontier still uses data bytes.

Selected chain output uses `manifest.json`, `audio-NNN.l4hy`, and `decoded.wav`;
raw output uses `raw-manifest.json`, `raw-NNN.l4hy`, and `raw.wav`. A manifest is
written only when that whole choice exists. `report.json` and `target.wav` retain
the declared gain and complete target. Output names are protected against input
aliases and stale artifacts. Generated source audio, streams, player images and
detailed private receipts belong in ignored `build/`.
