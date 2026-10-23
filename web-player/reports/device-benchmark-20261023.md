# Full ATtiny13A device benchmark

`scripts/benchmark-device.mjs` measures the translated full-device path, with
separate library construction and JavaScript DSP timers. It validates every
measured configuration before writing a completed result. The default output is
under the ignored repository `build/` directory.

```powershell
# Representative music, stereo music and speech, default 250 ms per run
node web-player/scripts/benchmark-device.mjs

# All 13 retained firmwares, balanced four-trial order
node web-player/scripts/benchmark-device.mjs --firmware all --frames 12000 --rate 48000 --trials 4 --out build/benchmarks/device-all.json

# A longer interval or a particular firmware; --firmware also accepts comma lists
node web-player/scripts/benchmark-device.mjs --firmware rhythmic --frames 48000 --trials 8
```

Paths supplied to `--out` are relative to the repository root unless absolute.
The default representative IDs are `rhythmic`, `lumiere-stereo` and
`hq4-chego-auto`. The numeric limits are listed by validation errors; `--help`
prints the available options. The script refuses mismatched runtime/source hashes
or host imports in the peripheral WASM module.

## What is timed

- **Cold construction:** `new ATtiny13A(..., {cacheTranslation:false})`, including
  fresh runtime memory, reset, AVR lowering, generated WASM module compilation,
  instance binding and wrapper setup. The full-device runtime module has already
  been imported and compiled. V8 can internally cache identical compiled bytes;
  this is library-cache bypass, not a process-cold startup measurement.
- **Warm construction:** the same public constructor with a verified translation
  cache hit. The generated immutable module is reused; device memory is fresh and
  checked to differ from the cold instance's memory. Cache priming is outside both
  construction timers. Cold/warm order alternates between runs.
- **Capture:** only `capturePhysical` calls, starting from reset on a fresh
  warm-constructed device, in blocks of 1024 output frames. This includes
  translated CPU execution, C peripheral/event scheduling, physical pin
  integration, initial capture configuration and public-wrapper allocation/copy.
  CPU, peripheral and pin work are coupled. Their exclusive wall times remain
  unresolved without internal instrumentation.
- **DSP:** only the production JavaScript `Renderer.processRaw` calls on exactly
  those captured blocks, with a 35 Hz high-pass, 9 kHz low-pass, volume 0.65 and
  filtering enabled. Stereo uses two filter states. Its constructor, CPU setup,
  measurement bookkeeping, copies into the report's aggregate arrays, state
  snapshots, hashing, signal summaries and assertions are outside these timers.

The sum of capture and DSP is reported as their measured sum. It excludes
construction, benchmark validation and untimed intervals between calls. It is not
an end-to-end browser callback latency measurement.

## Equality and ordering

Every firmware is run with all four combinations of `fastIdle` and
`optimizeFlags`. Each variant receives an unmeasured warmup of up to 4096 frames.
Every trial then uses new device memory, the same Flash/EEPROM, sample rate,
frame interval, filter parameters and block boundaries. A four-order Williams
schedule puts each variant in each run position over four trials. The exact order
and start offsets are retained in JSON.

At every block boundary, direct assertions compare the public architecture and
IRQ diagnostics, complete 160-byte data space (registers, I/O and SRAM),
1024-byte Flash, 64-byte EEPROM and IRQ frames. The `idleCycles` performance
counter is excluded from equality. It remains in the report. Raw and filtered
Float32 PCM are compared byte for byte over the whole interval; the trial
baselines are also compared across trials. Hashes identify the compared samples
and state checkpoints; raw PCM files are not retained. Per-channel range, RMS and
sample-change count help identify a silent capture.

This demonstrates that the selected optimizations preserve those observations
for these inputs. It does not independently establish hardware fidelity or
compare every hidden peripheral latch.

## Retained run

The accompanying `device-benchmark-20261023.json` contains complete individual
trials, min/max/median/mean/sample standard deviation, exact parameters, Node/V8
versions and flags, CPU/OS metadata, Git state, firmware hashes, normalized-LF
source hashes, generated module hashes, runtime hash and build-manifest identity.
The runtime is source-matched by checking every manifest input before timing.

The retained run used Node 22.22.3 on Windows x64, AMD Ryzen 5 5600X, with four
trials of 12,000 frames at 48 kHz (250 ms per run). It completed all 13 firmwares,
208 measured device runs and 2,496 block checkpoints. All PCM/state assertions and
cross-trial determinism checks passed. Every captured channel had finite,
changing samples.

The source base was merge commit `0255388f1dc9fab1ca89c0784e8ef31d7b61314e`,
including runtime build `1e99df6`. The benchmark script was untracked at measurement
time, as recorded in Git status, and its exact content hash is retained. The
83,482-byte runtime SHA-256 was
`ff1f8203977328de99e20eb41a396b331ffb8c1ce886cf2d7e5be0caadc079d9`.

Times below are milliseconds for the baseline (`fastIdle:true`,
`optimizeFlags:true`), medians over four trials. The capture column also shows its
observed min–max range. Headroom is 250 ms divided by median capture-plus-DSP
time; a value below one means this measured path took longer than the represented
audio interval.

| Firmware | Cold | Warm | Capture median (min–max) | DSP | Headroom |
| --- | ---: | ---: | ---: | ---: | ---: |
| rhythmic | 39.89 | 1.44 | 434.96 (362.66–502.67) | 0.216 | 0.57× |
| alicia | 58.24 | 2.06 | 591.60 (520.99–684.09) | 0.232 | 0.42× |
| turkish-march | 42.42 | 1.90 | 262.25 (231.96–327.46) | 0.198 | 0.95× |
| children | 36.52 | 1.15 | 394.10 (324.45–432.89) | 0.191 | 0.63× |
| greensleeves | 27.52 | 1.02 | 284.91 (270.03–307.61) | 0.174 | 0.88× |
| lumiere-stereo | 34.63 | 1.27 | 301.18 (268.95–350.87) | 0.286 | 0.83× |
| hq4-chego-auto | 33.86 | 1.64 | 468.92 (408.86–549.16) | 0.183 | 0.53× |
| hq4-chego-spectrum | 37.96 | 1.90 | 476.46 (402.90–498.97) | 0.179 | 0.52× |
| hq4-chego-timbre | 40.34 | 1.57 | 499.67 (434.74–555.33) | 0.192 | 0.50× |
| hq4-chego | 37.23 | 1.39 | 524.55 (453.32–648.42) | 0.194 | 0.48× |
| hq4-otvechaesh | 32.51 | 1.16 | 481.06 (445.96–494.96) | 0.187 | 0.52× |
| hq4-vinni | 58.21 | 2.02 | 733.16 (680.87–754.31) | 0.216 | 0.34× |
| hq4-chego_stoi_max | 83.76 | 2.07 | 872.33 (642.72–1018.85) | 0.226 | 0.29× |

Warm construction was 20.0–40.4 times faster than library-cache-bypassed
construction by the ratio of medians. DSP was below 0.3 ms per interval. Capture
dominates the measured audio work, but these timers do not identify which portion
of capture is CPU, peripheral scheduling or physical pin integration.

The following ratios compare capture medians, disabling only the named option
against the baseline. Above one means the enabled option was faster in these
samples. They should be read alongside the raw trial spread, not as precise
optimization effects.

| Firmware | `fastIdle` off/on | `optimizeFlags` off/on |
| --- | ---: | ---: |
| rhythmic | 1.04× | 0.86× |
| alicia | 1.12× | 0.96× |
| turkish-march | 1.51× | 0.94× |
| children | 1.13× | 0.90× |
| greensleeves | 1.16× | 0.96× |
| lumiere-stereo | 1.41× | 1.27× |
| hq4-chego-auto | 0.97× | 0.97× |
| hq4-chego-spectrum | 0.90× | 0.86× |
| hq4-chego-timbre | 0.98× | 0.96× |
| hq4-chego | 1.04× | 0.90× |
| hq4-otvechaesh | 1.02× | 1.00× |
| hq4-vinni | 0.94× | 0.85× |
| hq4-chego_stoi_max | 1.00× | 0.83× |

The report also contains both ratios with the other optimization disabled. Every
speech firmware reported zero skipped `idleCycles` in all trials, so these runs
do not demonstrate a speech wait-loop acceleration. Substantial wall-time
variation remains, as shown by the capture ranges. Neither a universal
flag-optimization gain nor its converse is established by these four-trial wall
times.

## Limits

These are single-process Node measurements on the recorded host. No CPU affinity,
fixed-frequency control, forced garbage collection or host-load isolation is
applied. V8 tiering, compilation caching, GC, thermal/frequency changes and other
processes can affect trials. Four trials expose spread but do not establish a
statistically reliable small optimization advantage. Ratios are descriptive;
values near one, or smaller than the observed spread, need further measurement.

The default interval is the first 250 ms from reset, not an entire composition.
The device uses the current playback defaults, including fuse startup profile 0;
this run does not benchmark fuse-selected hardware startup delays. It does not
measure browser `AudioWorklet` overhead, host audio scheduling or exclusive
CPU/peripheral costs. Older duty-stream/interpreter benchmarks execute different
peripheral and audio pipelines and cannot be treated as controlled speedup
comparisons with this full physical-pin path.
