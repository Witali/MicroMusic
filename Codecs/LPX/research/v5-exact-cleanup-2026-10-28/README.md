# Paused exact-cleanup checkpoint

The completed component checks found **no byte changes and zero serialized-byte
savings** in 1,049 unique reset streams. They cover 48,960,174 samples and pass
the integer-model, common-native and v5-only-native PCM/PWM checks, non-growth,
field/tail preservation and private-transform fixed-point checks. V5 remains
lossy relative to an original WAV; the equality promise concerns decoded output
relative to the input codec stream.

[checkpoint.json](checkpoint.json) records the anonymous checkpoint. The input
scope was all 181 original references: 98 original speech profile groups, 264
non-speech groups and 98 accepted expanded100 speech groups, totaling 460 source
groups. Another 610 finalized combined-study selected/raw chain requests were
included. These 1,070 requests deduplicate to 752 ordered chains and 1,049 reset
streams. The completed component stage made 4,196 native output-domain
comparisons: two layouts times PCM/PWM for each byte-unchanged stream.

The **independent 752-chain audit has not run**. No new production-player
admission, linked AVR Flash/SRAM measurement or IRQ experiment has run for this
cleanup study. There is no Flash-saving or new timing claim. Saving this
checkpoint does not resume those stages or change an encoder default.

The component and its seven previously passed independent test groups are in
commit `5172ce23`; the unchanged decoder source is `5c7e0592`. The proof and
predeclared study scope remain in [PROTOCOL.md](PROTOCOL.md). The completed
worker receipts and per-stream caches remain in ignored build storage. Their
source inventories and recorded runner match the saved files; all recorded
input/output fingerprints are equal. No recordings, compressed streams, waveform
or firmware fingerprints, private input paths, or generated firmware are
redistributed here.

## Saved research tooling

[reproduction/run_corpus.py](reproduction/run_corpus.py) is the exact runner used
for the completed per-reset checks. It reads frozen locally prepared bindings,
checks source/native-library/input epochs, uses separate shard receipts and
retains per-stream cache records. Its output must be an owned directory under
ignored `build/`; input streams stay outside that directory's stream-output
subdirectory. All 1,049 actual stream outputs in this run refer back to their
unchanged input files.

[reproduction/audit_chains.py](reproduction/audit_chains.py) is a saved,
**unexecuted draft** for the independent follow-up. It is intended to re-decode
complete old/new ordered chains through both native layouts, concatenate across
the explicit reset geometry and compare original chains with their frozen
PCM/PWM fingerprints. Its existence and syntax validation are not evidence that
the full-chain stage passed.

The scripts require the project Python environment, active codec tools on
`PYTHONPATH`, locally prepared private bindings and matching common/v5 native
libraries. They do not create or redistribute the private corpus manifests.
Bindings must be trusted, locally prepared data; assertions are integrity checks,
not a security boundary for arbitrary manifests. Recorded runtime versions must
remain unchanged for cache resumption. The cache key is not a complete runtime
attestation; use a new binding/output epoch if that environment changes.

Only syntax compilation, CLI help parsing and read-only receipt/source-inventory
checks were performed while saving this checkpoint. The optimization, corpus,
whole-chain and firmware stages remain paused pending explicit resumption.
