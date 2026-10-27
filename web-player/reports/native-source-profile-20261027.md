# Native source-location profiling experiment

The diagnostic pipeline can now associate some raw V8 native leaf-PC samples
with candidate C source lines, including code inlined into a surviving native
function. It uses a generated source map whose executable WASM sections **and
absolute byte offsets exactly match production**. Production files are unchanged.
All 218 function metadata names, indices and body boundaries must also match the
verified named WASM; a JSON hash alone is insufficient evidence for its offsets.
No per-instruction, peripheral-event or clock-edge JavaScript callback was added.

This improves the evidence available for the open cost-attribution task; it
does not establish precise exclusive CPU/peripheral/pin durations. The complete
ATtiny13A plan remains **24/31**, with seven items open.

## Evidence

The [replay command](../scripts/audit-native-source-profile.mjs) and
[pure parser](../scripts/lib/avr-v8-native-profile.mjs) retain checks and hashes
in [the JSON report](native-source-profile-20261027.json). The
[cookbook](../../docs/avr-asm-cookbook/sampled-native-source-locations.md) documents
the offset conventions, official tool references, rejected DWARF-preserving
route, supported configuration and interpretation limits.

The fresh capture uses the existing physical direct instruction kernel with
10,000,000 requested instructions, D1 and a nominal 20 MHz source. It is a
diagnostic workload, with no active-IRQ audio or silicon measurement claim.
The existing capture tool verifies production parity for PCM and complete
architectural state, and proves its named native executable unchanged.

Host tools: Node 22.22.3/V8 12.4.254.21-node.56; prepared Emscripten 6.0.12,
Clang 24 and Binaryen 133. These were already registered project dependencies;
no new software was downloaded or installed.

| Whole-process raw tick budget | Observations |
| --- | ---: |
| Candidate project source lines | 37 |
| External/support source lines | 0 |
| Known native range, unresolved location | 46 |
| Other leaf PCs | 486 |
| Total | 569 |

The unresolved native budget contains **38 position gaps** and **8 absent
source-position tables**. The parser does not impute those observations. The
37 candidates cover 25 distinct lines, including `avr-device.inc`,
`clki_board.inc`, `io_registers.inc`, `analog.c`, `device_clock.h` and `device.c`.
These counts describe sampled locations; they are not an exclusive partition
of the hardware devices' elapsed execution time.

The audit checked 3722 logged code generations, 120 known native generations,
272 disassembly blocks and 15,664 source-map segments. There are 41 source-map
files, of which 22 normalize to project native files. Retained labels must be
registered native build inputs with valid line numbers. Raw host paths,
native addresses, SDK source text and full logs remain in ignored `build/`.

**50/50 focused checks pass:** 22 new parser cases plus 28 existing profile
attribution/function-name checks. Cases cover multiple source locations inside
one native function, byte-offset normalization, lifetimes/ties/ambiguous ranges,
unmapped spans, malformed metadata/VLQ/tables, external callbacks, path privacy
and conservation of every tick. No runtime/library source changed, so the
already passing 2586-check runtime integration suite was not repeated here.
The reviewer's actual stale-input reproduction (all offsets shifted by 16)
now rejects against the verified named WASM, alongside the synthetic negatives.

Native WASM remains 124,505 bytes, SHA-256
`ad3e472582cbca5f7d0d57b7b17776c58a03f9b5f7eb89b55fda89ea84389fc7`.
The generated AVR compiler identity remains
`f9db0099f03d50657ee08e1e98ea10d6b4aab44bca0d0d734a302938ed67d505`.

## Replay

```text
node --test web-player/tests/avr-v8-native-profile.test.mjs web-player/tests/avr-profile-attribution.test.mjs web-player/tests/avr-profile-functions.test.mjs
```

Create the capture directory first, then redirect the capture's stdout/stderr to
its `run.log` and retain the test output as `build/native-source-profile-tests.log`:

```text
node --prof --log-source-position --no-logfile-per-isolate --logfile=build/profiles/native-source-20261027/capture/v8.log --print-wasm-code web-player/scripts/profile-device.mjs --kernel --clock physical --operation direct --instructions 10000000 --frames 512 --repeats 1 --out-dir build/profiles/native-source-20261027/capture
node web-player/scripts/audit-native-source-profile.mjs --input build/profiles/native-source-20261027/capture --out-dir build/profiles/native-source-20261027/map --python <configured-python> --test-tap build/native-source-profile-tests.log --output web-player/reports/native-source-profile-20261027.json
```

The replay rejects another native version, incomplete captures, unsupported
address lifecycle events, changed executable code or changed absolute offsets.
The raw V8 log covers the entire process, including setup, reference execution
and warmup. Its 569 observations are separate from the inspector capture-window
samples; they cannot be added or compared as elapsed-time budgets. Further work
needs verified window markers and a measured ambiguity/overhead model.

Follow-up: the [native-window experiment](native-window-profile-20261027.md)
shows that this engine suppresses raw native ticks while the inspector CPU
profiler runs. This report's whole-process counts cannot establish a measured-
work source budget; setup/reference/warmup remain included. The separate native-
only mode supplies validated markers; the original data and limits above remain.
