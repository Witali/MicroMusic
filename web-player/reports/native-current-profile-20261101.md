# Current native sampling and lookup gaps, 2026-11-01

Fresh kernel and stereo captures on `882ba210` retain **17201 whole-process
ticks**, including **10657 certain-interior ticks**. Time conversion and CPU
phase scopes remain investigation candidates. These counts and the new
predecessor lookup gaps do not establish exclusive CPU/peripheral/pin durations.
Production runtime, generated AVR compiler, cache identity and defaults are
unchanged. The device plan remains **24/31 complete, seven open**.

The [checkpoint evidence](native-current-profile-20261101.json),
[kernel audit](native-current-kernel-20261101.json),
[music audit](native-current-music-20261101.json) and
[inline transport proof](inline-scopes-current-20261101.json) retain hashes and
conserved budgets. Raw logs, source maps, disassembly and host paths stay under
ignored `build/`. The four retained JSON files have LF checkout attributes so
their byte hashes remain stable on Windows.

## Identity and recorded parity

The current native module is 124590 bytes, SHA-256
`244b3d3da85ff6cd065e6b105b18d26d8ae07e6615802d77f23a123338209c98`.
The compiler/cache identity is
`6dff8aef30a8847d4abb3dad56d0d12d52889ac034c9cab42c13611121545a5d`.
The diagnostic native rebuild is byte-identical before names are attached.
Executable sections and absolute offsets match the reconstructed source map;
all 218 native body metadata entries match the named module. The inline proof
binds seven private artifacts, current producer sources and native inputs.
Scopes describe pre-Binaryen DWARF candidates, not a dynamic call stack after
optimization. The existing registered Emscripten 6.0.12 / Clang 24 / Binaryen 133
toolchain was reused; no new download was required.

- Kernel: three runs of 100000000 instructions, physical-model nominal internal
  20 MHz, CLKPR /1, direct resumable execution, flags optimized, no bounded regions,
  phase locals or fast idle. Each reaches 124999999 cycles and virtual time
  6249999950000 ps, with zero IRQs and no device fault.
- Music: three `lumiere-stereo` captures of 262144 stereo frames at 48 kHz,
  physical-model nominal 9.6 MHz, CLKPR /1, bounded regions, phase locals,
  optimized flags, fast idle and the producer's benchmark controls enabled.
  Each reaches virtual time 5461333333333 ps with 204798 IRQs and no device fault.

All six runs match their reference PCM and full recorded architecture snapshot,
including memory, Flash, EEPROM, diagnostic slots, IRQ frames and retained tail
pins. Music PCM SHA-256 is
`0f29ab6bf8fccb0f12f797fc557f00c86f2707f3eca42c864d2651d62177a974`.
This parity is not a complete pin-waveform comparison or audio-underrun test.
These explicit physical-model policies differ from the conservative verification
preset; nominal clock fixtures are not measured silicon data.

The capture producer is unchanged from the October 30 capture. The kernel
started from a clean checkout; the music checkout also had the three offline
analyzer/test edits. Both captures use the same production/native/compiler
inputs. Captures ran serially without simultaneous tests or benchmarks.
Reference execution, warmup and result serialization stay outside marked work.

## Conserved observations and lookup dependence

`--lookup-distances` adds an optional partition to every existing view. The
native gap is sampled PC minus the preceding V8 source-position offset. The
WASM gap is that position's module offset minus the preceding mapped segment.
They use different address spaces and measure reliance on predecessor lookup.
Zero gaps do not prove source ownership; nonzero gaps are not execution lengths,
time weights, confidence levels or error bounds. Unresolved samples supply no
gap. See the [method and official format references](../../docs/avr-asm-cookbook/sampled-native-source-locations.md).

| Certain-interior class | Kernel | Stereo music |
| --- | ---: | ---: |
| Both lookup positions exact | 130 | 50 |
| Native predecessor only | 2187 | 780 |
| WASM predecessor only | 78 | 41 |
| Both predecessors | 999 | 467 |
| Source-unresolved native | 3143 | 1169 |
| Other generated CPU/VM work | 1155 | 458 |
| Total interior | 7692 | 2965 |
| Largest resolved native gap, bytes | 767 | 758 |
| Largest resolved WASM gap, bytes | 20 | 54 |

The first four rows equal the existing project-plus-support budget. The inline
view independently retains 3367/1330 project candidates, 27/8 support and
3143/1169 unlabelled native observations. No ambiguous context was sampled;
ambiguity remains an explicitly tested outcome. `other` is not a CPU duration.

Kernel has 2 boundary and 3958 outside ticks; music has 2 boundary and 2582
outside. Thus 10657 interior + 4 boundary + 6540 outside = 17201 whole-process
ticks. Individual interiors are 2474/3828/1390 and 1030/1077/858. Whole-process
project/support/unresolved/other budgets are 3985/29/3741/3897 for kernel and
1804/12/1583/2150 for music. Nothing is assigned across an unknown source gap.

| Deepest unique project scope candidate | Kernel observations | Music observations |
| --- | ---: | ---: |
| `device_clock_ratio` | 372 | 143 |
| `at_half` | 370 | 111 |
| `avr_device_phase_clock` | 289 | 86 |
| `mirror` | 184 | 69 |
| `analog_next_event` | 136 | 54 |
| `clock_domains` | 121 | 54 |

These rows are selected investigation candidates, not a partition of subsystem
time or an exhaustive ranking. Inlined and optimized work can share locations;
unknown observations cannot be distributed using the labelled sample ratios.

## Validation and limits

All **85 focused Node checks** and **14 Python checks** pass. Five new tests
cover opt-in behavior, the four resolved gap classes, missing mappings, window
conservation with inline scopes and invalid option rejection. Real CLI replay
without the option exactly matches each new audit after removing only
`lookupDistances`. Plain source-map reconstruction also matches outside the
explicit inline views, map segment count and inline-method description.
Two real CLI controls reject an older native capture and a changed native hash
in the inline proof; neither creates a success report.

Current native/compiler sources, artifacts and identity are verified unchanged
from `882ba210`. Its prior **2862/2862** runtime checkpoint is retained separately;
that full suite was not rerun for this offline diagnostic change.

Host work windows vary from 21.39 to 75.96 seconds for kernel and 11.29 to 16.91
seconds for music under V8 logging. Whole-process median tick gaps are 15525 and
15557 microseconds; maximum gaps are 93673 and 31563 microseconds. The requested
1000-microsecond interval is not actual sampling resolution. These runs are not
a balanced before/after performance experiment, and differences from older
captures are not a regression or speedup measurement.

Inspect conversion operands, invalidation causes and emitted native instructions
at the surviving clock/phase sites before another runtime change. Preserve
faults, exact event order and timer/pin/IRQ/RESET service; require output parity
and balanced uninstrumented controls for an optimization. More samples do not
revive previously rejected arithmetic shortcuts. Exclusive subsystem timing
remains open. No official simulator session ran; the 10 ns requirement concerns
virtual verification events, not host sampling.

## Reproduction

Create separate kernel/music directories under
`build/profiles/native-current-20261101/`. Use Node 22.22.3 with
`--prof --log-timer-events --log-source-position --no-logfile-per-isolate
--print-wasm-code --logfile=<capture-directory>/v8.log`, redirecting stdout and
stderr to that directory's `run.log`. Run the two captures serially:

```text
web-player/scripts/profile-device.mjs --kernel --clock physical --operation direct --instructions 100000000 --frames 512 --repeats 3 --native-log-windows --native-log-only --out-dir build/profiles/native-current-20261101/kernel
web-player/scripts/profile-device.mjs --firmware lumiere-stereo --clock physical --frames 262144 --repeats 3 --bounded-regions --phase-locals --benchmark-controls --native-log-windows --native-log-only --out-dir build/profiles/native-current-20261101/music
```

Reconstruct the kernel map with `audit-native-source-profile.mjs --input
<kernel-directory> --out-dir <map-directory> --python <configured-python>
--output <plain-report.json>`. Run `map-native-inline-scopes.py --input
<map-directory>/runtime-debug-preopt.wasm --source-map <map-directory>/preopt.map
--emsdk <registered-sdk> --em-config <map-directory>/emscripten-config.py
--out-dir <inline-directory>`. Retain only its sanitized `report.json` proof.

Replay each capture with `audit-native-source-profile.mjs --input
<capture-directory> --out-dir <separate-replay-directory> --inline-scopes
<inline-directory> --inline-report <retained-proof.json> --lookup-distances
--test-tap build/native-lookup-focused-20261101.tap --output <audit.json>`.
Omit `--lookup-distances` for the compatibility control. The TAP comes from
`node --test` on `avr-v8-native-profile.test.mjs`,
`avr-profile-attribution.test.mjs`, `avr-profile-functions.test.mjs` and
`avr-inline-artifacts.test.mjs` under `web-player/tests/`. Python checks are
`dwarf-inline-scopes.test.py` and `source-map-labels.test.py` in the same directory.
