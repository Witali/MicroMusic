# Browser validation of bounded AVR regions

Browser/model parity passes. The real-time audio gate fails for all three
physical firmware packages, both with and without bounded regions. Keep the
optional compiler setting and the default music engine unchanged. This is
evidence against enabling the full physical engine by default on this host,
not a silicon-fidelity result or an isolated compiler speed measurement.

## Fixture and evidence

The new [browser fixture](../tests/bounded-browser.html) loads the actual
rhythmic, lumiere-stereo and hq4-chego-tiny Flash/EEPROM images from the catalogs.
Each gets a physical OSCCAL table at its catalog frequency, resumable execution
and the declared NVM timing profile. It builds ordinary and bounded CPU packages
through the existing package API. It does not change source CPU frequency,
skip peripheral events, suppress IRQs or generate replacement audio.

In the in-app browser, the fixture compares four1024-frame blocks per firmware
at48kHz: exact raw/filtered PCM, full architectural/diagnostic state, Flash,
EEPROM, IRQ frames and picosecond pin events. All12 checkpoints pass with
active firmware IRQs. The embedded bounded-region manifests and CPU hashes are
checked. An independent Node replay of both package variants matches all
browser filtered-PCM/state/pin hashes:24 additional checkpoints. The native
runtime is unchanged, SHA-256
`111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`.

The audio screen then uses the production `worker.js`, package renderer,
`audio-worklet.js` and bounded AudioQueue. A real AudioContext runs at48kHz,
with4096-frame requests,8192-frame priming and the original queue/refill policy.
A zero-gain node after processing mutes the output. Thus no audible-quality or
physical audio-device latency claim follows. No mocks or OfflineAudioContext
replace the live queue. The AudioContext clock, position messages and worker
state messages are recorded throughout each10-second run, then all resources
are closed before the next run. No tests/profilers run concurrently.

Environment: Windows, Ryzen5 5600X, in-app Chromium user agent156.0.0.0; Node
v22.22.3 for the separate replay. Browser visibility stays visible and the
AudioContexts stay running. Each run lasts10001–10016ms wall time and advances
the audio context9971–10000ms; the final queue observation is13–44ms old.
Firmware IRQ counters reach95998–134398, with no device faults.

## Live queue outcome

Delivered percentage is `frames / clockFrames` after the production worklet
starts, excluding its initial prime. Missing/reprime frames remain in
`clockFrames`; the content position never hides them.

| Firmware | Bounded regions | Delivered / requested frames | Delivered | Underrun episodes |
| --- | --- | ---: | ---: | ---: |
| rhythmic | off | 143232 /446464 | 32.08% | 17 |
| rhythmic | on | 161280 /450560 | 35.80% | 19 |
| lumiere-stereo | off | 147456 /450560 | 32.73% | 18 |
| lumiere-stereo | on | 155648 /452608 | 34.39% | 19 |
| hq4-chego-tiny | off | 115712 /446464 | 25.92% | 14 |
| hq4-chego-tiny | on | 167424 /448512 | 37.33% | 20 |

All six fail the zero-underrun/full-frame acceptance criterion. Underrun
episodes count empty-queue incidents, not the number of missing frames; faster
repriming can increase this count while delivering more content. Use both frame
counts to assess the deficit. The rows are one serial screen, not balanced
identity-controlled trials, so differences between rows do not establish a
causal compiler speedup. The earlier [Node timing study](bounded-regions-20261025.md)
remains separate. Neither the synthetic11.3x result nor the measured Node HQ4
gain proves real-time browser playback.

The acceptance check also rejects stale/missing position reports, insufficient
audio-clock progress, suspended contexts, hidden tabs, missing IRQ activity or
device faults. `complete:true` means the diagnostic screen finished; it does
not mean `realtimeAccepted:true`. This screen establishes a failure promptly;
a future passing profile still needs longer runs and broader host coverage.

## Reproduce and next work

Retained [raw evidence](bounded-browser-20261025/browser.json),
[source snapshot](bounded-browser-20261025/sources.json),
[host/catalog identities](bounded-browser-20261025/environment.json) and
[Node replay result](bounded-browser-20261025/node-replay.json) preserve the
actual input/code identities, all queue positions and worker state messages.
The measured source snapshot matches `ee25c4c` after LF normalization; the
fixture was uncommitted over `c17f220` during capture and then retained unchanged.
The verifier checks archived source hashes, monotonic frame/underrun counters,
visible/running clocks and the failed gate; `--replay` additionally executes
the packages against every browser parity digest. Use this retained revision
when replaying against repository sources; later compiler/runtime changes may
correctly produce different CPU hashes.

```sh
node web-player/scripts/serve.mjs 8133
# Open http://127.0.0.1:8133/web-player/tests/bounded-browser.html in the in-app browser.
# Run exact parity, then live audio checks, then download the JSON evidence.
node web-player/reports/bounded-browser-20261025/verify-evidence.mjs
node web-player/reports/bounded-browser-20261025/verify-evidence.mjs --replay
```

No native/CPU production code changes in this checkpoint. The full-device
checklist stays21/30 with nine open items. Prioritize the measured native
scheduler/time-conversion work from the existing profiles; evaluate adaptive
region budgets separately afterward. The present browser screen does not
provide exclusive subsystem timing or prove which native function dominates.
Preserve original clocks, interrupts, event boundaries and pin/PCM parity in
each candidate, and repeat this gate before changing the default engine.

Primary API reference: W3C [Web Audio API1.1 working draft,22 September2026](https://www.w3.org/TR/2026/WD-webaudio-1.1-20260922/),
including the AudioContext time and AudioWorkletProcessor execution contracts.
AVR/WASM/device semantics and pinned Microchip definitions remain those in
[AVR_TO_WASM.md](../native/AVR_TO_WASM.md).
