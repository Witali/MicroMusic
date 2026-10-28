# Reproduction interface

Read [the fixed protocol](../PROTOCOL.md) before preparing a run. No V2 study
outcomes are included here. Use the project's Python/numeric runtime and native
compiler bootstrap; pass the intended V2 checkout explicitly. The driver imports
its active tools from that root and rejects cached project imports from another
checkout. It reuses the small pinned V1 research utility module for atomic/private
storage, reset validation and native/model chain verification; it does not call
V1's core-epoch requirement or encoder.

Run the synthetic contract tests without corpus media:

```text
python reproduction/test_protocol.py
```

Prepare once after the parent freezes an explicit V2 core commit. All output
must be in a fresh ignored directory under that checkout's `build/` directory:

```text
python reproduction/run_corpus.py --prepare --source-root V2_CHECKOUT --output V2_CHECKOUT/build/adaptive-voice/corpus-v2 --core-commit FROZEN_COMMIT --v1-root PRIVATE_V1_STUDY --v1-audit PRIVATE_V1_AUDIT --nonspeech-manifest PRIVATE_NONSPEECH_MANIFEST
```

The private preparation receipt freezes the exact 98/14/6 phase inventory and
the maximum expensive-call count implied by the actual edited reset segments.
Preparation performs no seed fitting or refinement. It binds the passed V1
independent audit to the exact V1 private binding and retains the complete source
and stream provenance locally. Generic native common/v5-only libraries are built
once before concurrent workers start.

For each declared phase, run source-parity shard 0 and shard 1. Both profiles of
each source stay on the same shard. For example:

```text
python reproduction/run_corpus.py --source-root V2_CHECKOUT --output V2_CHECKOUT/build/adaptive-voice/corpus-v2 --phase speech-screen --shard 0
python reproduction/run_corpus.py --source-root V2_CHECKOUT --output V2_CHECKOUT/build/adaptive-voice/corpus-v2 --phase speech-screen --shard 1
```

The other fixed phase names are `speech-default` and `nonspeech-default`.
Workers use the prepared binding only; they accept no new selection/settings
arguments. Retain every worker/attempt receipt, including failures. A valid
completed cache is immutable and may be reopened without repeating refinement.

Each edited segment saves every distinct verified measured-pool stream in report
ID order. The driver independently recomputes the pool's metrics, voice/noise
descriptors, scores, admissibility, selected/raw IDs and byte/score frontier from
those actual bytes. Actual operator start/completion events must match reported
stages. A trapped new seed-fit call fails the record and is journaled.

Each record also saves original/declared-level reference fingerprints, exact
reset geometry and seed provenance, the separate legacy comparison, the three
complete choices, their full-chain domain floors and true 100/95/90 cap decisions.
The final completion marker is written after attempt completion and binds saved
pool streams and attempt journals. Progress output contains phase/counts only;
all detailed artifacts remain private.

This corpus uses the original frozen **PCM16** reference files. Recovery of
sub-PCM16 FLOAT/24-bit input before rounding is a separate input-format check,
not an outcome claimed for this PCM16 corpus. Active-policy quiet targets retain
their explicitly changed level and cannot be compared with original-level SSE
as if playback gain had stayed the same.

Independent saved-output audit and actual-player admission are required before
publishing claims. None of the data byte caps measures a complete player image.
