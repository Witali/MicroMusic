# Current native sampling checkpoint, 2026-10-30

Fresh captures of commit `45d92168` identify `next_event_scan` and the CPU phase
bridge as current investigation priorities. They replace stale hotspot evidence
from before the wide-clock-ratio optimization. These are **sample counts, not
exclusive durations or a measured speedup**. No production code changed.

The native runtime is 124614 bytes, SHA-256
`b9a8fa14a971fd5f82f8175f978e9a0b1e03f31fc8612a6892d202d7f93635a1`.
The generated compiler identity is
`d67d0e37d909695ee35f8a90059d825f68008e42ec1ac231302c7f0bf51fa46b`.
The diagnostic native rebuild matches production byte-for-byte before names
are attached. Executable sections and their absolute offsets also match the
reconstructed source map. All 218 native function metadata entries are bound
to the named module. Production libraries, caches and both native artifacts
remain unchanged.

## Workloads and parity

- Kernel: three marked runs of 100,000,000 instructions, nominal internal
  20 MHz, CLKPR /1, resumable execution, flag optimization enabled, no bounded
  regions or phase-local optimization, fast idle disabled. Each reaches virtual
  time 6,249,999,950,000 ps, with no IRQs or device fault.
- Music: `lumiere-stereo`, three marked captures of 262144 stereo frames at
  48 kHz (5.461333... virtual seconds each), physical clock, bounded regions,
  phase-local and flag optimization, fast idle and the producer's benchmark
  controls enabled. Each records 204798 IRQs and no device fault.

These are explicit physical-model diagnostic policies, not the conservative
website `verification` execution preset. Clock/calibration data are nominal
software fixtures, not measured silicon. A preliminary 8192-frame music
capture had only 69 interior ticks and was replaced by the longer workload
for the retained hotspot assessment.

Every marked run matches its production reference's PCM and full recorded
architecture snapshot, including diagnostic slots, memory, Flash, EEPROM,
IRQ frames and retained tail-pin data. This is not a complete pin-waveform
capture or an audio-underrun/hardware admission test. Constructors, reference
execution, warmup, hashing and serialization are outside the marked work.
Raw captures run serially without simultaneous tests or benchmarks.

## Conserved sampling budgets

| Capture/view | All ticks | Project source candidates | Support | Source-unresolved native | Other |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kernel interior | 2146 | 939 | 6 | 837 | 364 |
| Kernel boundary | 0 | 0 | 0 | 0 | 0 |
| Kernel outside | 2150 | 400 | 2 | 331 | 1417 |
| Kernel whole process | 4296 | 1339 | 8 | 1168 | 1781 |
| Music interior | 3139 | 1386 | 10 | 1276 | 467 |
| Music boundary | 1 | 0 | 0 | 0 | 1 |
| Music outside | 3438 | 634 | 2 | 526 | 2276 |
| Music whole process | 6578 | 2020 | 12 | 1802 | 2744 |

All recognized native ticks have verified function containers; source gaps
remain unresolved. Individual interiors contain 715/718/713 kernel ticks and
868/1124/1147 music ticks. Median whole-process tick gaps are 15773 and 13327 us,
with maxima 33079 and 39277 us. Requested intervals do not establish actual
sampling resolution. Host marker excess and rounding allowances remain as
specified in the [sampling contract](../../docs/avr-asm-cookbook/sampled-native-source-locations.md).

| Verified native container | Kernel interior ticks | Music interior ticks |
| --- | ---: | ---: |
| `next_event_scan` (165) | 163 | 274 |
| `avr_device_phase_clock` (49) | 168 | 217 |
| `duration` (154) | 65 | 179 |
| `ratio` (155) | 117 | 149 |
| `advance_half_until_ps` (167) | 89 | 111 |
| `analog_advance` (133) | 82 | 93 |

These mixed function containers can include inlined work. Do not assign them
entirely to a peripheral or convert their counts into time percentages. The
older 10,000,000-instruction capture has a different native version and interval;
this table is not an old/new performance comparison.

## Next bounded investigation

Inspect `next_event_scan` call counts, its invalidation reasons and the actual
`at_half`/`duration` conversions before changing cache lifetime or adding guards.
Separate same-state lookups from scans required by elapsed time, I/O writes,
asynchronous input, reset, sleep, NVM, ADC/comparator and CLKI horizons.
Retain original fault and timestamp-capacity behavior. In particular, merging
`min(at_half(a),at_half(b))` into `at_half(min(a,b))` can suppress a conversion
fault from the later deadline unless representability is proven first.
No such transformation or previously rejected arithmetic guard is enabled.

The exclusive CPU/peripheral/pin timing item remains open. **68/68 focused
metadata/parser/attribution checks pass**. The prior 2659 runtime/shared checks
belong to the unchanged production checkpoint and were not rerun for report-only
work. The full-device plan remains **24/31 complete, seven open**. The 10 ns
verification requirement applies to virtual events, not these host samples.

## Reproduction

Create separate directories under `build/profiles/native-current-20261030/`.
Use Node `--prof --log-timer-events --log-source-position --no-logfile-per-isolate
--print-wasm-code`; set `--logfile=<capture-directory>/v8.log` and redirect
stdout/stderr to that directory's `run.log`/`run.err`. Run each capture serially:

```text
web-player/scripts/profile-device.mjs --kernel --clock physical --operation direct --instructions 100000000 --frames 512 --repeats 3 --native-log-windows --native-log-only --out-dir build/profiles/native-current-20261030/kernel
web-player/scripts/profile-device.mjs --firmware lumiere-stereo --clock physical --frames 262144 --repeats 3 --bounded-regions --phase-locals --benchmark-controls --native-log-windows --native-log-only --out-dir build/profiles/native-current-20261030/music-long
```

Replay each with `audit-native-source-profile.mjs --input <capture-directory>
--out-dir <separate-map-directory> --python <configured-python> --test-tap
build/profiles/native-current-20261030/tests.tap --output <report.json>`.
The TAP is from `node --test` on `avr-v8-native-profile.test.mjs`,
`avr-profile-attribution.test.mjs` and `avr-profile-functions.test.mjs` under
`web-player/tests/`. The retained [kernel](native-current-kernel-20261030.json)
and [music](native-current-music-20261030.json) audits pin raw input, native,
tool, map, source and TAP hashes plus all partitions and unresolved budgets.
Native addresses, host paths, raw source/disassembly and absolute timestamps
remain in ignored `build/`. No external file was downloaded.
