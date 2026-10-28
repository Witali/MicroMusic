# Bounded non-speech trajectory robustness

`benchmark_nonspeech_trajectory.py` exercises the new encoder on complete frozen
non-speech references. This is a numerical robustness experiment. It computes
no STOI, makes no subjective music-quality or adoption claim, and performs no
AVR/hardware admission, including when full encoded chains exceed Flash.

Before candidate outcomes, freeze these per-group rules:

1. Independently decode every original ordered v5 reset segment with the model,
   native common and native compact-only paths, checking full PCM16 and PWM.
2. Rank original segments by exact PCM SSE divided by original sample count;
   choose the largest ratio with the earliest index on a tie. Also choose the
   final segment when different. This protects complete tail/reset coverage.
3. Search each chosen original segment with frame limit 2, window length 2,
   beam 2, two spectral finalists, one excitation finalist, horizon 80,
   64 complete evaluations, local screening 640, amplitude capacity policy,
   lambda 0, conservative numerical PCM/PWM floors and `speech=False`.
4. Cap each edited segment at its actual original serialized bytes. Retain
   selected and raw alternatives separately; check the true whole-chain cap.
   Every untouched segment remains byte-identical and independently verified.
5. Reconstruct every distinct final baseline/selected/raw chain afresh through
   the model and both native PCM/PWM interfaces. Recompute complete original-
   reference metrics and exact integer PCM/PWM energy floors independently.

The callback returns candidate-segment SSE minus frozen original-segment SSE.
Adding the frozen whole-reference SSE reconstructs the exact whole error. The
constant is removed before the refiner's float score, so a multi-million-sample
recording cannot lose a small improvement through a huge constant's rounding.
Segment deltas are exactly representable for the format's at-most-64k reset
segments. Full totals use bounded int64 dot-product chunks accumulated into a
Python integer. No long whole-recording arrays are rebuilt per search trial.

Full references stay at their original length and gain; there is no trimming,
resampling, delay alignment or normalization. Record RMS, peak, full-scale
sample fraction, nonzero fraction, absolute-amplitude >=256 fraction and fixed
PWM endpoint fraction descriptively. These are not VAD, perceptual scores or
proof that a full-scale source sample was clipped during recording.

## Freeze smoke, then run all groups

The smoke cases are chosen only by frozen geometry: shortest and longest
source cases, both profiles. The source/inventory, settings and manifest hash
are recorded before any search. A full run requires a completed smoke with
the identical protocol fingerprint. Settings remain fixed after smoke.

From the repository root with project Python dependencies available:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/benchmark_nonspeech_trajectory.py --manifest /private/manifest.json --output build/non-speech/smoke --phase smoke
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/benchmark_nonspeech_trajectory.py --manifest /private/manifest.json --output build/non-speech/full-0 --phase full --smoke-result build/non-speech/smoke/results-private.json --shard 0 --shards 3
```

Run the latter command with shard indices 1 and 2 and separate output folders.
Shards use original manifest ordinal modulo shard count, rather than ranking
outcomes. Each group saves changed segment streams and a private result,
including search bounds, evaluation/partial-window counts, numerical metrics,
original-level descriptors, exact full-chain counters and private artifact
fingerprints. Source and manifest identity are rechecked after every group.
Only anonymous whitelisted numeric evidence and public code hashes belong in
committed research; references, names, paths, streams and media-derived hashes
stay in ignored build storage.

The focused tests cover centered exact substitution, integer MSE comparisons,
chunked worst-amplitude SSE, no-STOI metrics, descriptive activity/clipping
proxies, geometry-only smoke selection, safe output aliases and complete
partial-tail reset-chain native/model/PWM reconstruction. The refiner's own
non-speech mode also retains the original speech policy unchanged.
