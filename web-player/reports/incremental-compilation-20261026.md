# Incremental compilation and dynamic linking, 2026-10-26

Full ATtiny13A now offers `incrementalCompilation:true`: retain the original
compiled module/table/globals and dynamically link only affected fragments
after CPU self-programming. Reuse unchanged encoded instruction/block/region
templates. The ordinary monolithic path remains the default and explicit
fallback. Native device bytes, virtual timing and portable firmware artifacts
are unchanged. The caching checklist item is complete:23/30, seven open;
hardware fidelity, exclusive profiling and register-traffic work remain open.

## Mechanism and correctness

Initial startup compiles one monolithic seed, with private exports for function
references and its dispatch table. Unchanged groups continue using these
functions. A page change compiles affected fragments importing native memory
and native WASM bridges plus shared CPU globals. The same table is patched
after all replacement instances are prepared, and only after the in-flight
instruction retires. No per-instruction/edge JavaScript callbacks are added.

Pages use the official32-byte Microchip definition. Invalidation includes
two-word and skip dependencies across page/PC-wrap boundaries, changed remote
branch leaders, block flag masks and entire cross-page cyclic regions. Static
seed wrappers detach when a callee changes; later specialized wrapper modules
can be reused while their instances rebind updated imports. LPM reads live
Flash rather than a folded constant. Full CFG and portable-artifact serialization
still run. See [the complete contract](../native/INCREMENTAL_COMPILATION.md).

The earlier eager-page prototype compiled33 modules at startup. It passed
functional checks but roughly doubled construction cost and had no audio
benefit. That startup strategy is rejected; its measured source is retained.
The accepted seed strategy starts with one compiled module and32 logical page
groups referring to it. `reusedModules` in diagnostics counts reused code groups,
not distinct Module objects. For the real SPM fixture's final update, one new
fragment is compiled and32 groups are reused, including the original runner.

## Controlled measurements

AMD Ryzen5 5600X, Windows10.0.26300 x64, Node22.22.3/V8 12.4.254.21-node.56.
Baseline source:`9b1073f9`. Both source/native hashes are verified and retained.
The harness reconstructs baseline JS/native inputs from Git in an ignored
directory; it imports both variants in every fresh Worker. No full tests,
browser execution or profiler ran alongside either timing experiment.

Each case has four discarded warmups and eight balanced four-position Williams
trials, oldA/oldB/newA/newB:192 timed observations per experiment. Shared
whole-image caches are disabled; unchanged code within the candidate's live
chip is deliberately retained. Construction is timed separately. Host-patch
timers exclude the writes and hashing; real SPM timers include execution and
retranslation. CLKI pin draining and snapshot checks occur outside timers.
Audio cases capture4096 frames at48kHz, with interrupts active, but do not
measure browser playback or audio underruns.

|Case|Old median ms|Seed strategy median ms|Paired old/new|Paired range|
|---|---:|---:|---:|---:|
|16 host patches to rhythmic image|1564.24|815.18|1.914x|1.733–2.007|
|Real SPM, compatible clock|55.02|40.60|1.367x|1.148–1.644|
|Real SPM, physical1MHz|122.15|66.35|1.800x|1.501–2.064|
|Real SPM, CLKI1MHz /40000 transitions|146.80|80.79|1.889x|1.636–3.005|
|Physical rhythmic audio|144.71|152.26|0.955x|0.851–1.239|
|Physical Lumiere stereo audio|154.11|150.98|0.958x|0.886–1.241|

Ratios are medians of paired geometric trial ratios, not ratios of independently
selected medians. Same-version controls and all individual observations remain
in the raw data. The CLKI old-control range0.773–2.473x shows substantial host
variation; the result is workload-specific, not a guaranteed factor. Audio
has no established gain and a possible small loss. Seed construction still
costs extra: paired old/new ratios0.700–0.817x across cases. In the physical
SPM case, median cold construction81.34→109.00ms is separate from execution
122.15→66.35ms. Retain explicit opt-in and the unchanged player default.

The eager prototype's host-patch/SPM paired gains were2.105x/1.394x/1.996x/1.798x,
but construction ratios0.496–0.534x and audio0.931x/0.926x made its initial
module strategy unsuitable. Independent experiments have independent host
variation; no direct eager-versus-seed speed ratio is inferred.

## Evidence and validation

Final compiler identity:
`423f5bb9dd8aa5f53c176d1f24bf7aab2c85aaf9b6c954ce2d978ebd64cfa7cc`.
Native remains119010bytes, SHA-256
`bea029bf125c9f8f6ee3e63197e9a9e15556f35d59464ec3ccd5199c137e0715`.
No firmware, manufacturer originals or native C/WASM bytes change.

- [Accepted seed strategy](incremental-compilation-20261026/seeded-benchmark.json):192 observations,
  per-patch code hashes and diagnostics, full state/pin/PCM hashes, baseline and
  candidate source identities,36 byte-identical portable artifacts across the
  entire retained catalog's legacy/full/resumable/bounded-phase modes.
- [Eager prototype](incremental-compilation-20261026/eager-page-benchmark.json)
  and [its12-file source overlay](incremental-compilation-20261026/eager-page-source.zip)
  over baseline9b1073f9. `snapshot.json` pins normalized source hashes. This is
  historical source, not the accepted implementation; no MIDI is included.
- [Browser Workers](incremental-compilation-20261026/browser.json),
  [full test totals](incremental-compilation-20261026/test-summary.txt) and
  [source/evidence hashes](incremental-compilation-20261026/validation.json).

All1957 tests pass, no failures/skips. New coverage includes984 cases for all123
forms, four C/Z inputs and internal/unequal external clocks, with adjacent-ps
phase snapshots. Additional cases cover cross-page/wrapped operands, skip widths,
remote leaders, cyclic wrapper rebinding/removal, unchanged wrappers, current
Flash LPM, policy identity, RESET during RCALL, SPM under all three clocks,
erasing the executing SPM page, precompiled packages and persistent hits.

In real browser Workers,4096 stereo frames retain798IRQs and819199.5CPU cycles
with identical full native/CPU state and physical PCM. The CLKI erase/write/
execute case retains all40001 pin observations, two Flash generations,20ms,
20000CPU cycles and the new instruction's0x5A result. After its final write,
one fragment is compiled,31 page bindings are reused and16 table slots change;
the original runner stays loaded. These are software/model checks, not silicon
measurements. External virtual ISP/HVSP/programmer interfaces remain excluded.

```text
node --test web-player/tests/*.test.mjs tools/music-startup.test.mjs tools/avr-music-target-core.test.mjs
node web-player/scripts/benchmark-incremental-compilation.mjs --baseline 9b1073f9 --trials 8 --out build/benchmarks/incremental.json
node web-player/scripts/verify-incremental-benchmark.mjs web-player/reports/incremental-compilation-20261026/seeded-benchmark.json
```

Run tests before timing, serially. For browser checks, start
`node web-player/scripts/serve.mjs 8133`, open
`http://127.0.0.1:8133/web-player/tests/incremental-browser.html` in the in-app
browser and retain its visible report after PASS. Text evidence hashes normalize
CRLF to LF; ZIP/native hashes cover raw bytes. See official
[Microchip SPM](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
and [WASM module/import/table semantics](https://webassembly.github.io/spec/core/binary/modules.html).
