# Guarded CPU blocks and idle NVM, 2026-10-24

The checkpoint adds an actually exercised register-only block path for resumable CPU execution and avoids recurring service of idle EEPROM/Flash. It retains cycle/phase scheduling, the generated instruction fallback and native pin/audio buffering. The results below separate native changes from compiler changes; synthetic loop throughput is separate from firmware audio throughput.

The three measured physical-time firmware excerpts improve by median paired 1.365–1.640x overall, with every one of 18 pairs positive. Compiler-only medians are 1.328–1.596x. The short/long arithmetic loops improve 2.610x/22.123x overall; the latter is a synthetic region of 30 INC instructions. CLKI /1,/256 gains are 1.087x/1.065x overall while preserving every source phase. These measurements still leave real firmware below real-time throughput on this host, so the default-engine gate remains open.

## Implementation and boundary fixes

`f0d3f94` gates NVM using its existing command/window/busy state. Register/control accesses catch up its private timestamps before mutation. EERIE-ready remains a live IRQ level. Active programming, protected windows, sleep/reset/supply ordering and held CLKI keep their existing timing. See the [NVM contract](../native/devices/attiny13a/nvm-activity.md).

`cfcc379`, `0cefb04` and `8c59884` add guarded register-only spans, remove duplicate native checks and activate the internal runner with the correct f64.lt opcode. The guards retain active continuations, IRQ delay, enabled IRQs, count limits, physical observation/event boundaries and exact u64 retirement capacity. An unbounded span also proves finite physical timestamp capacity. Register values still reside in shared memory; WASM register locals and cross-block flag liveness remain planned. CLKI and memory/I/O retain their detailed phase paths. See the [CPU contract](../native/devices/attiny13a/cpu_phase.md).

`b850ad0` fixes fractional-period event ties for both ordinary and resumable full-device blocks. At9MHz the second instruction and RESET can share222223ps. Rounding the event budget up admitted the block and either cancelled an already completed instruction or committed too many effects. The conservative floor with a strict block-end comparison preserves the successful prefix. Tests cover both adjacent picoseconds. The separate observation-deadline conversion retains its rounded-up half-cycle contract.

Hardware meaning follows [Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf), sections4.3.1/4.7 and5.3/5.5.3/16.6/16.9.1. Byte encodings follow the official [WebAssembly instruction index](https://webassembly.github.io/spec/core/appendix/index-instructions.html). Existing documented digital phase choices remain profiles pending silicon validation. External ISP/HVSP/programming remains excluded.

## Reproducible measurement

Measured source: `b850ad07f1008e9fb1ec4a56f98153d0b866fc3c`. Baseline: `0a61ae7`, 112522-byte native WASM, `ccbef473d1c5947c218215272b0a4312352a9e71c9ebc1851dec640c25f5f4f3`. Final native WASM: 112668bytes, `9a3461976f84d456ca6f2a1c8b2a24f0b1dadbc85ced2c45d20f1eeffbbc2bde`. Both runtimes have103 function exports plus exported memory (104 total exports), no imports and fixed two-page memory. The build log/older reports counted functions when saying “103 exports.”

The harness verifies original Git/native/source hashes, compiler flags and export sets. Native-only binds the original compiler to the new native runtime. Candidate binds the new compiler to that same runtime. Old compiler source changes only its two import URLs; both dependencies must match Git. All13 retained firmwares produce byte-identical ordinary translations for each of the legacy and full ABIs.

Six trials use all six permutations of the three variants, serially, with discarded warmups and fresh mutable instances. The 234 timed runs use public execution calls; compilation/construction/input submission, snapshot assertions, hashing and retained-output concatenation are outside timers. Public API copying and engine tiering inside calls remain included. Final tests and diagnostic tracing finished before measurement; they did not overlap timing. Host scheduling/frequency/GC remain uncontrolled. AMD Ryzen 5 5600X, Node 22.22.3, V8 12.4.254.21-node.56, Windows 10.0.26300.

[Final raw results](planned-optimizations-20261024/benchmark.json) retain individual trials, order, variance, byte sizes and single startup generation/compilation observations. The latter are diagnostics rather than stable cold-start performance estimates. The [initial run](planned-optimizations-20261024/initial-benchmark.json) and [preactivation run](planned-optimizations-20261024/preactivation-benchmark.json) are retained with their exact [initial](planned-optimizations-20261024/initial-benchmark-source.txt)/[preactivation](planned-optimizations-20261024/preactivation-benchmark-source.txt) harness sources. They exposed missing amortization/activation and are not final-implementation speed claims. Source archive hashes match their original reports; restore an archive to scripts/benchmark-planned-optimizations.mjs at its recorded compiler revision to reproduce that checkpoint.

Reproduce the final timing with `node web-player/scripts/benchmark-planned-optimizations.mjs --trials 6 --frames 12000 --instructions 1000000 --out build/benchmarks/planned-optimizations-rounded-final.json`.

## Results

Firmware intervals are250ms at48kHz. Direct loops retire one million instructions; the long loop has30 INC instructions per branch. Clock cases capture25ms at20MHz. Ratios are medians of individual paired ratios, not ratios of independently selected time medians. Native=baseline/native-only; compiler=native-only/candidate; total=baseline/candidate.

|Case|Baseline median ms|Final median ms|Native paired|Compiler paired|Total paired|Total paired min–max|
|---|---:|---:|---:|---:|---:|---:|
|rhythmic-compatible|270.94|272.30|0.997x|0.996x|0.992x|0.971–1.021|
|rhythmic-physical|680.12|414.68|1.032x|1.596x|1.640x|1.619–1.663|
|lumiere-stereo-compatible|266.26|270.57|1.017x|0.978x|0.986x|0.816–1.015|
|lumiere-stereo-physical|531.64|391.00|1.032x|1.328x|1.365x|1.347–1.394|
|hq4-chego-auto-compatible|383.53|371.23|1.031x|1.001x|1.036x|1.025–1.054|
|hq4-chego-auto-physical|619.68|446.41|1.021x|1.365x|1.408x|1.355–1.464|
|kernel-compatible-direct|141.69|131.70|1.073x|1.002x|1.078x|1.063–1.092|
|kernel-physical-direct|254.11|97.08|1.014x|2.581x|2.610x|2.556–2.907|
|kernel-register-span-compatible-direct|15.75|14.44|1.091x|0.999x|1.090x|1.070–1.121|
|kernel-register-span-physical-direct|288.76|13.10|0.993x|22.018x|22.123x|21.336–23.087|
|kernel-internal-20m-div1|117.10|41.74|0.995x|2.812x|2.798x|2.688–2.832|
|kernel-clki-20m-div1|318.19|291.36|1.092x|0.996x|1.087x|1.044–1.181|
|kernel-clki-20m-div256|193.04|180.76|1.078x|0.989x|1.065x|1.039–1.997|

These are coupled execution/peripheral/audio-capture measurements. The identical ordinary compiler paths provide a host-variation control; small differences on those paths cannot be attributed to new CPU instructions. No firmware-wide, browser-latency or real-time guarantee follows from a synthetic loop or a noisy paired median.

## Equality and activation evidence

All 1476 retained pairwise checkpoints match registers/SREG/PC/cycles, interrupts, SRAM/Flash/EEPROM, raw Float32 PCM and remaining pin events. Against the old runtime only the private overflowAt event hint may differ, validated as exactly0 or1 cycle earlier; 432 such differences are retained. Raw hint values and hashes with/without that hint are stored. Candidate versus native-only and baseline cross-trial checks require complete diagnostic equality too. No chip flag, retirement count or physical output is normalized. An untimed unequal-CLKI/ADC3/PWM comparison matches all 2001 pin events across2000 source transitions.

The native WASM phase-probe tests require real run/runUntil clock(14) calls for a12-instruction block. They first failed with individual clock(1) calls, then passed after correcting f64.gt to f64.lt. Final-state parity alone had not proved activation. Other new checks include accepted low32 carry/u64 boundaries, physical u64 overflow preserving four completed instructions, half-cycle starts, aliases, IRQ/reset and clock-control boundaries. The9MHz tied-RESET tests first failed in both CPU modes, then passed after the shared event-budget fix.

The historical pre-cache oracle separately validates the expected earlier hint and, in its OSCCAL/CLKPR wait-loop fixture, fewer optimized idle cycles. Total emulated cycles and every chip observation still match. These are scheduler work diagnostics, not relaxed hardware checks.

## Native source-entry reductions

The [counted runtime and chronological prefixes](planned-optimizations-20261024/call-counts-and-prefix.json) match the final production runtime. These are source entries, including functions later inlined, rather than WASM-call counts or timing. Baseline counts come from the retained analog-propagation checkpoint whose native hash equals0a61ae7. Timed runs are uninstrumented.

|Case|nvm_advance old → final|NVM cycle query old → final|NVM wall query old → final|
|---|---:|---:|---:|
|rhythmic|1448858 → 39120|1467609 → 0|1467609 → 0|
|lumiere-stereo|1361634 → 39120|1389765 → 0|1389765 → 0|
|hq4-chego-auto|1983101 → 132|2013105 → 0|2013105 → 0|
|kernel-clki-20m-div1|2601604 → 0|1300803 → 0|1300803 → 0|
|kernel-clki-20m-div256|2003948 → 0|1001975 → 0|1001975 → 0|

Nonzero firmware NVM advances include real EEPROM/register accesses and remain required. Their exact timestamps and protected windows are covered by24 differential NVM checks. Eliminated entries prove removed work; speed comes from the independent timing table.

## Integration status

The [full regression summary](planned-optimizations-20261024/test-summary.txt) records1187/1187 passing tests at the final source commit. This includes24 new block tests,24 NVM activity tests and the existing all123 instruction, package, SPM, RESET, input, CLKI and audio tests. No physical chip measurement has been supplied.

This is partial stage5 progress in [ATTINY13A_PLAN.md](../native/ATTINY13A_PLAN.md):21/30 main checklist items remain complete and nine remain open. Register locals, broader active-peripheral scheduling, persistent/region caches, Timer0 TOP=0/debugWIRE decisions, silicon measurements and the default-engine performance gate are not closed by these results.
