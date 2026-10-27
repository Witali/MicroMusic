# LPX 4/6 validation on the shared local corpus

Run commands from the repository root with the active codec requirements and
native C++ compiler available. All media, source provenance, encoded streams,
temporary headers, ELF/HEX files and caches belong under ignored `build/`.
The source collection is read-only. The scripts do not download or upload audio.

## Inputs and level policy

`shared_corpus.py` verifies the existing collection index and each applicable
manifest. It selects the 20 primary 8 kHz speech inputs, 27 mixed regression
references, four independent speech originals, five prepared phrases, three
complete music originals and 123 instrument captures before exact PCM dedup.
Prepared alternate-rate copies and encoded Speex/oracle streams are excluded.
The actual collection yields 181 unique cases and 306 independent segments.

Keep original level and DC. Conversion averages channels, resamples rationally
to 8 kHz when required, then rounds/clamps once to PCM16 and records any clipping.
Do not relabel 7.5 kHz samples as 8 kHz. Already prepared cartoon references have
their upstream processing recorded; this pipeline does not normalize them again.

Every sample of a long original is retained. Balanced segments contain at most
64,000 samples, avoiding a tiny final fragment. Encoder/decoder state resets at
each segment. Full-reference quality uses the concatenated complete output,
including boundary effects; it is not a claim of continuous decoding of an
arbitrarily long single LPX stream.

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/benchmark_shared_corpus.py prepare --collection tmp-audio-corpora --output build/lpx-shared/inputs
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/benchmark_shared_corpus.py encode --inputs build/lpx-shared/inputs --output build/lpx-shared/baseline
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/optimize_shared_corpus.py --inputs build/lpx-shared/inputs --baseline build/lpx-shared/baseline --output build/lpx-shared/selected --policy necessary
```

`encode` and selection accept `--shards 3 --shard 0` (then distinct shards 1/2).
Run at most one writer for a given shard. Selection counts missing baseline jobs
as pending, so it can be resumed after the baseline completes. A cache hit still
checks complete and segment references, contiguous slices, result signatures,
saved streams, model PCM and PWM. Changes to the recorded numerical source and
package-version fingerprints invalidate the cache.
Metadata saves retry brief Windows read locks without changing JSON bytes.

## Baseline and bounded optimization

The baseline uses the previously selected recipe: `speech_v4.encode`, two
refinement passes with a 320-sample horizon, then compact v5 extra innovations.
The cap for a segment of `n` samples is:

```text
20 + ceil(n / 320) * (20 for profile4, 30 for profile6)
```

This preserves the original v4 complete-file budget. Actual v5 headers are 22
bytes and are included in the cap. Report achieved payload/file rates by exact
input duration; short packet tails, headers and segment resets mean the profile
names are not exact achieved whole-file bitrates.

`optimize_speech_v5.optimize(reference, baseline_blob, decoder, cap)` can try
at most two generic host proposals: pre-emphasis 0.75 in an existing header field,
and three additional low/zero scale proposals outside the narrow scalar estimate.
Both reuse the same refinement strength and compact extra-pulse search. The
pre-emphasis proposal re-analyzes spectral coefficients; the lower-scale proposal
retains them. No gain field, trained codebook, MCU operation or decoder change is
introduced. Rejected candidates keep the exact original bytes.

The default `necessary` corpus policy chooses offline work for speech with
quiet/noisy labels, activity loss, SSE worse than silence, SER below 3 dB,
available STOI below 0.6, or absolute RMS gain error above 3 dB. These are work
triggers, not subjective quality thresholds or acceptance relaxations.
`--policy all-speech` explicitly searches every speech case. Exact digital
silence may use only the zero/lower-scale proposal regardless of cohort.
Other music/synthetic cases retain their original baseline in the default policy.

Every accepted segment stays within its cap and passes original-level PCM16 and
actual PWM SSE/STOI floors. The joined complete case must independently pass
those floors and must not introduce a new PCM/PWM activity failure. Otherwise
the entire case is restored and the rejected measurements remain available.
No budget increase or fitted gain/time shift is performed.

## Reading results correctly

`status=complete` means the stream and reference checks completed. The separate
`selected_quality_status` can still be `no_fit`: original-level waveform or
activity checks failed. This is a finite search result, not proof that the
format cannot represent that signal. Bit-cap failures and implementation errors
are accounted separately; they are never removed from group averages silently.

PCM16 and PWM quality differ. `pwm_pcm16(pcm)` applies the device transfer once;
do not pass already converted PWM duties into it. An 8-bit output may lose quiet
detail even when the internal PCM is accurate. STOI is unavailable when the
recording cannot provide enough active analysis frames, rather than assigned
pystoi's numeric `1e-5` sentinel. Perfect/zero-reference SER has an explicit status.
STOI and SSE are measurements, not listening scores or analog-board validation.

## Actual AVR checks

The validator compiles the unchanged core using the measured Flash recipe,
retains the full profiling ABI, proves the embedded audio subtraction, then
compares every useful PWM byte with the saved PCM/model oracle under active IRQ.

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/validate_shared_corpus_avr.py validate --inputs build/lpx-shared/inputs --selected build/lpx-shared/selected --output build/lpx-shared/avr --avr-bin AVR_BIN --runner SIM_RUNNER --lib SIM_LIB --wsl Ubuntu
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/validate_shared_corpus_avr.py stress --inputs build/lpx-shared/inputs --selected build/lpx-shared/selected --output build/lpx-shared/avr --avr-bin AVR_BIN --runner SIM_RUNNER --lib SIM_LIB --wsl Ubuntu
```

Replace the three toolchain/runtime placeholders. Omit `--wsl` for a native Linux
runtime. `validate` accepts the same shard arguments and optional `--common`;
the default is the explicitly enabled v5-only build. Check final accounting for
all expected images: an early snapshot with missing selected outputs is incomplete.

`stress` selects the heaviest measured source for each profile, tiles complete
stored packet fields to 64,000 samples, and computes a fresh continuous-state
model reference. Any previously unused partial-packet tail is disclosed. It runs
normal ASM, an extra 100 IRQ-cycle load, and explicit C fallback controls. The
fallback's exact values do not imply that it meets the AVR real-time deadline.

[Retained corpus measurements and limitations](../../research/shared-corpus-2026-10-27/README.md).
