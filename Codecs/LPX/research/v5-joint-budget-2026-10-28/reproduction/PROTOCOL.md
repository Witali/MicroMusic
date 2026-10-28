# Reproducing the v5 joint-search study

The supplied `benchmark.py` and `audit.py` are byte-for-byte copies of the scripts used for the corpus study. `source-manifest.json` preserves their SHA256 hashes, the benchmark's complete recorded decoder/tool inventory, exact package versions, search settings and original relative script locations. The three shard lists contain anonymous case aliases and sample totals only.

Private reference audio, original names, path-bearing manifests, incumbent streams, generated firmware and listening media are excluded. These public assets make the search and verification procedure inspectable. Reproducing the exact reported corpus numbers also requires the locally retained private corpus and strongest previous candidates; hashes cannot reconstruct those inputs. A lawful replacement corpus gives a new experiment, not a replication of the original numerical totals.

## Runtime and source preparation

Use CPython 3.12 with the recorded packages: NumPy 2.5.4, Numba 0.68.0, SciPy 1.18.1, pystoi 0.4.1 and SoundFile 0.14.0. Put a working native `g++` on `PATH`. The native decoder is built by the repository's `BatchSession`; the corpus search itself does not need the AVR toolchain. Run from a checkout containing the exact source inventory in `source-manifest.json`.

Replace `path/to/reproduction` below with this directory's location. The helper uses the current Python interpreter and standard library. Run it from the repository root or supply `--repo` explicitly:

```text
python path/to/reproduction/reproduce.py --repo . install
python path/to/reproduction/reproduce.py --repo . verify
```

Installation restores the exact scripts and shard lists to `build/v5-joint/corpus/`. It refuses to replace a different existing file. Restoring those paths matters: the original benchmark records its own path as `build/v5-joint/corpus/benchmark.py`, so executing a relocated copy directly would produce a different source-inventory key even if the bytes matched. Keep normal Python assertions enabled; these original research scripts use assertions for admission checks.

## Private input contract

Place the original local manifest at `build/v5-joint/corpus/strong-private.json`, and retain its referenced PCM16 WAVs and v5 streams. Its schema is `lpx-v5-joint-corpus-private-v1` with `cases`, `case_count` and `segment_count`. The recorded experiment has 49 speech cases, 59 reset segments, profiles 4 and 6, and budgets 0, 5 and 10 percent. No MIDI input belongs in this repository.

Each case needs an anonymous `id`, `kind`, `cohort`, `language`, `condition`, total `samples`, `reference` and `profiles`. `reference.path` identifies a mono 8 kHz PCM16 WAV, and `reference.pcm16_sha256` hashes its complete little-endian PCM16 samples. Each profile supplies `profile`, `original_bytes`, full `original_metrics`, `variants` and `budgets`. The original baseline is `variants[0]`. Every variant carries ordered `segments` with `index`, `start`, `samples`, local `path`, `stream_sha256` and `file_bytes`, plus complete joined `metrics`.

Each budget carries `growth_percent`, per-segment `segment_caps`, their sum `complete_stream_cap_bytes`, `incumbent_tag` and the complete `incumbent` variant. Caps use exact integer arithmetic:

```text
cap = (original_segment_bytes * (100 + growth_percent) + 99) // 100
```

For each budget, the strong incumbent is the feasible previous whole-clip candidate with minimum PCM SSE, then PWM SSE, then stream bytes, while preserving all four original baseline floors: PCM/PWM SSE and available PCM/PWM STOI. Previous header, excitation and raw alternatives remain available; this prevents evaluating the new search against an unnecessarily weak seed. Metrics use the full original recording at its original level and the actual reset geometry. Do not replace them with normalized snippets or independently scored segments. The optional `private_case_id` field is unnecessary for these public scripts and should be omitted from any shareable manifest.

## Search and ablation

The full branch searches legal adjacent quantized LSF coordinates and then refits local excitation. The ablation searches the same LSF coordinates without that local excitation refit. Both use the same strong incumbents, exact byte caps and bounded settings: 32 frames, two spectral finalists, 640-sample screening lookahead, 80-sample excitation horizon and one pass.

Run all three shards for each branch, then the independent audit:

```text
python path/to/reproduction/reproduce.py --repo . fit --branch full --shard 0
python path/to/reproduction/reproduce.py --repo . fit --branch full --shard 1
python path/to/reproduction/reproduce.py --repo . fit --branch full --shard 2
python path/to/reproduction/reproduce.py --repo . audit --branch full
python path/to/reproduction/reproduce.py --repo . fit --branch lsf-only --shard 0
python path/to/reproduction/reproduce.py --repo . fit --branch lsf-only --shard 1
python path/to/reproduction/reproduce.py --repo . fit --branch lsf-only --shard 2
python path/to/reproduction/reproduce.py --repo . audit --branch lsf-only
```

Outputs and resumable caches remain under ignored `build/v5-joint/corpus/{branch}/shard-{n}`. Cache identities bind the source inventory, settings, exact reference samples, incumbent stream and byte cap. Keep the recorded package versions; start with separate clean output directories for a changed runtime or a new experiment. The exact original scripts are retained without silently changing their historical cache protocol.

For every segment, the independent audit compares the portable model with native common and v5-only decoders, checks exact PCM/PWM output and serialized caps, and verifies both candidate and raw alternatives. It then recomputes joined original-reference quality, checks stored WAVs and output hashes, and verifies the selected variant's four floors. The two branches jointly produce 588 case/profile/budget rows.

## Full firmware and automatic budgets

The production tools `measure_speech_firmware.py` and `select_speech_budget.py` provide the separate full-Flash and budget stages. Run each tool with `--help` for its current CLI. Measure the complete ordered reset chain in one linked image with the same decoder/compiler/harness settings for all alternatives; shared code, lookup tables and segment switching count once. Full Flash is linked `.text + .data`; subtracting stream bytes is only a diagnostic program component, not the selection cost. Hash-bound evidence includes exact embedded stream ranges and source/build/image fingerprints.

Fresh budget evaluation decodes against the entire original reference, checks native/model/PWM equality, and validates that evidence. The default `review` policy chooses the best verified no-growth complete image preserving the baseline's four quality floors. Measured Pareto growth alternatives remain for listening; `metric-proxy` is an explicit optional policy for numerical recommendations. It does not establish audible improvement. Firmware size does not establish real-time admission: active-IRQ simulation or hardware measurements must separately verify exact output, completion, buffer underruns and stack margin.

Never publish path-bearing corpus manifests, source audio, generated private headers/binaries or listening media merely because these reproduction scripts are public.
