# Optional resumable indirect SRAM blocks

`sramBlocks:true` batches only guarded LD/ST chains in the full ATtiny13A
resumable compiler. All effective addresses must be proven inside SRAM before
clocking. Register/I/O aliases, wrapping candidates, pointer destinations,
undefined update aliases and any intervening observation/event retain the
individual generated-instruction path. ALU and memory blocks stay separate.
See the [official semantics and whole-span proof](../../docs/avr-asm-cookbook/resumable-sram-blocks.md).

The option defaults to false and is forced off in verification. Both caches
partition it; a packaged policy survives actual SPM, including incremental
recompilation. It adds no native ABI, memory or import change. The distributed
124675-byte device runtime keeps SHA-256
`0e00866562e59ab8a40bb7295889386f7132b9a3d7e2c63ba02a804f387135a3`.
The legacy WASM artifact is also unchanged from baseline `3a73d96b`.

## Evidence

All **2706/2706** default tests and **93/93** focused integration tests pass,
without failures, skips or cancellations. The 33 new SRAM tests cover every
initial pointer byte, full SRAM bounds, all SREG values, option combinations,
ordered dependencies, original fault/alias paths, partial host edits, deadlines,
IRQ/reset and protected windows, held CLKI, retirement capacity, caches,
packages and real SPM. Native WASM probes require actual combined calls from
both `run` and `runUntilPs`, with no JavaScript phase callbacks.

The [retired-instruction census](sram-instruction-trace-20261101.json) retains
150000 instructions / 588 paired full-state and pin checkpoints. Native IRQ
arbitration happens before recording PC, and each step must retire once.
Rhythmic/Lumiere have 5291/5892 memory instructions and zero direct LDS/STS;
the HQ4 Tiny prefix has 292 direct SRAM accesses among 295 memory instructions.
This is an untimed census, not a subsystem cost profile.

The [historical and retained-pin audit](sram-blocks-verification-20261101.json)
checks both catalogs across legacy/full/resumable/combined compiler policies.
All 48 default module bytes match the historical compiler. Six additional audio
comparisons cover Rhythmic, Lumiere and HQ4 Tiny on internal and external clocks,
with active IRQs, complete state/memories/IRQ frames, exact PCM and all six
observed pins. CLKI traces drain every audio sample to retain every source
transition within the 1024-event ring. These comparisons retain 4,936,786 pin
events across 12,384 state/PCM/pin checkpoints. The bounded periodic source is an explicit
digital fixture, not a measured oscillator. Exact counts and hashes are in the
[evidence index](sram-blocks-20261101.json).

The [final thirteen-workload matrix](sram-blocks-validation-final-20261101.json)
also covers compatible/resumable music, direct kernels, CLKI divisors and active
ADC. Baseline CPU bytes match with the option off. Final candidate CPU hashes
match both timed series despite subsequent package/verification-policy wiring.
This links the timings to the retained generator rather than assuming source
edits left the result unchanged.

## Measurements and limits

Two quiet serial series use 12000 frames at 48 kHz, fresh chips, one unchanged
native Module, equal full-workload warmups and four-label Williams trials.
Identity pairs share CPU Modules via the production cache. Construction,
compilation, state/pin comparisons and hashing are outside capture timers.
All 192 timed runs and 96 warmups retain exact PCM, complete checkpoint state
and the default retained tail pins; the separate audit above retains the
complete pin history. Timings are Node 22.22.3 / V8 12.4 host observations.

| Firmware | Series A ratio | Series B ratio | Faster pairs | Module growth | Code growth |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rhythmic | 1.165x | 1.126x | 14/16 | 1680 B | 1347 B |
| Lumiere stereo | 1.134x | 1.229x | 16/16 | 2241 B | 1802 B |
| HQ4 Chego auto | 0.976x | 1.011x | 8/16 | 1591 B | 1257 B |

Ratios are baseline/candidate; above 1 favors the candidate. Individual and
identity ratios vary substantially: old-identity median ranges 0.947–1.050,
new-identity median 0.972–1.052, with larger individual outliers. Repeated music
medians support a scoped opt-in benefit; exact percentages, general HQ4 gains,
exclusive subsystem costs and browser real-time/underrun support are unproven.
No firmware image, analog timing profile or hardware accuracy criterion changes.
The plan stays **24/31**, with seven items open, including broader register and
helper traffic reduction. The official simulator remains unavailable locally.

Raw timings, warmups, control orders, hashes and host/tool versions:
[series A](sram-blocks-timing-a-20261101.json),
[series B](sram-blocks-timing-b-20261101.json).

## Reproduction

From this worktree, with the already registered local toolchain:

```powershell
node web-player/scripts/generate-avr-cache-identity.mjs --check
node --test web-player/tests/attiny13a-sram-blocks.test.mjs
node --test web-player/tests/*.test.mjs
node web-player/scripts/trace-sram-instructions.mjs
node web-player/scripts/verify-sram-blocks.mjs --baseline 3a73d96b
node web-player/scripts/benchmark-generated-wasm.mjs --transform sram-blocks --baseline-ref 3a73d96b --validate-only --frames 2048 --instructions 10000
node web-player/scripts/benchmark-generated-wasm.mjs --transform sram-blocks --baseline-ref 3a73d96b --frames 12000 --case rhythmic-physical --case lumiere-stereo-physical --case hq4-chego-auto-physical --out build/benchmarks/sram-repeat-a.json
node web-player/scripts/benchmark-generated-wasm.mjs --transform sram-blocks --baseline-ref 3a73d96b --frames 12000 --case rhythmic-physical --case lumiere-stereo-physical --case hq4-chego-auto-physical --out build/benchmarks/sram-repeat-b.json
```

Run timings serially, without tests, compilation or profiling in parallel.
Official PDFs, device definitions and tools are reused from the existing
download registry; this change adds no external download or system installation.
