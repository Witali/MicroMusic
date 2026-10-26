# Attribute generated AVR/WASM functions before profiling

Applicable to MicroMusic's ATtiny13A physical CPU emitter and the common music
emitter (including ATtiny88). This is diagnostic tooling, not a CPU speedup.
The current runtime uses Clang 24 / Binaryen 133, Node 22 / V8 12.4; other
optimizers may inline or reorder functions differently.

`web-player/scripts/profile-device.mjs --clock physical --bounded-regions`
profiles the optional bounded region policy. `--phase-locals` separately opts
into phase-local liveness; both require a resumable physical/CLKI configuration.
Keep these independent when attributing an experiment to one change.

Before attaching a custom name section, rebuild the native runtime with the
recorded compiler/options and require byte equality with the production WASM.
Its optimized function map supplies the final native indices. For unoptimized
generated CPU modules, derive function order from the embedded manifest:

```
imported functions
one instruction body per Flash word
ordinary basic blocks
region bodies
region entry wrappers
region wrappers with an ordinary-block fallback
one empty block
public execution/capture drivers
```

Never assume 512 Flash words or label every nonexported extra function
`emptyBlock`. Check body count, consecutive indices, name uniqueness and the
actual public export indices. Unit tests additionally inspect the binary's
element table to verify that dispatch targets identify entry/fallback wrappers,
rather than region bodies. Unknown layout fails before profiling.

The [WASM module format](https://webassembly.github.io/spec/core/binary/modules.html)
defines the index spaces and executable sections. The
[custom name section](https://webassembly.github.io/spec/core/appendix/custom.html)
attaches diagnostic names; stripping all custom sections must give identical
executable bytes. Compare named/profiled execution against its uninstrumented
production reference, including PCM, architectural state, Flash/EEPROM, IRQ
frames and retained pin events. Construction, comparison and serialization
belong outside the profiling window.

Self samples describe observed leaf frames; inclusive samples overlap. Inlined
work is attributed to the surviving containing body. Neither observation proves
exclusive peripheral time or a causal speed improvement. Keep raw samples,
function maps, source identities and a replay of derived counts. Performance
acceptance still requires separate balanced, uninstrumented timing controls;
real-time audio additionally requires active interrupts and underrun checks.

This changes no native ABI, production CPU bytes, memory geometry, or engine
default. The C/WASM and JS engines remain selectable. No handwritten AVR
assembly is introduced.

Verified example: [adaptive-region study, 2026-10-26](../../web-player/reports/bounded-profile-20261026.md),
15 profiles / 14,031 work samples with all five production execution replays.
It identifies remaining clock/scheduler work; it is not a speed measurement or
a supported real-time audio claim.

## Validate attribution and irregular sample intervals

`scripts/lib/avr-profile-attribution.mjs` checks every tree node, parent and
sample ID, including unsampled cycles, and validates the timestamp/delta stream.
It partitions all observations into work ancestry and observations without that
ancestry. Each partition retains both leaf counts and right-end delta weights.
The weights are estimates: a sample cannot establish who owned its preceding
interval, and the initial delay can contain profiler startup work.

Keep native board/bridge/CLKI bodies in an explicit mixed bucket. O3 can inline
peripheral and pin work there, so a containing native function is insufficient
evidence of a separate hardware-subsystem duration. Support/unknown WASM leaves
also keep a nearest-known-caller table, labelled as context rather than added
cost. GC samples without a work ancestor remain visible outside that partition;
do not silently charge them zero work overhead.

The existing profiler now records this analysis beside its original count
tables. Replay a retained capture without running the emulator:

```text
node web-player/scripts/audit-device-profile.mjs --input build/profiles/bounded-current-music
```

The replay requires the original profile hash, production-parity marker and
exact agreement with all earlier leaf-count tables. It records source/metadata
hashes while exporting no frame URLs or compiler object directories. New link
maps and function catalogs retain object basenames. See the
[nine-profile replay and limits](../../web-player/reports/profile-attribution-20261026.md).
