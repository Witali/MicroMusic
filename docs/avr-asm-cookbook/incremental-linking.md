# Keep the compiled AVR runner; replace changed WASM functions

Entry-point correctness: time can advance outside the main runner. An SPM
write completed by manual `clock()` must be rebound before the next single
step or instruction-counted/block run. Keep the active-instruction/IRQ guard,
and test the first call's effects and exact cycles, not just eventual output
after a timed runner happens to repair the translation.

Also exercise a Flash generation change during a suspended IRQ. Finishing its
four-cycle entry does not retire a CPU instruction. Retry the remaining count
after rebinding; for a single step, check the monotonic native retirement counter
before deciding whether another fetch is needed. Keep zero-count, RESET and
newly erased instruction faults covered, including pauses after stack writes.

Applies to full ATtiny13A AVR25 emission, the discovered native device ABI,
ordinary/resumable/CLKI execution and WebAssembly MVP modules. Original project
implementation; no adapted vendor assembly. Device page geometry comes from
the pinned Microchip DFP. The native C/WASM peripheral runtime and portable
complete artifact are unchanged. Explicit `incrementalCompilation:false` keeps
the ordinary whole-module fallback; this is the default.

Keep a monolithic seed with exported function references, mutable CPU globals
and its original dispatch table. After CPU SPM, reuse unchanged instruction,
block and cyclic-region templates, compile affected page fragments, and patch
the shared table only after the latched instruction retires. Import native
memory/bridges and original globals directly into new WASM modules. Hot paths
never call JavaScript. Original static wrappers must detach if a callee changes;
specialized wrappers can reuse compiled code but must rebind changed imports.

Invalidation follows semantics, not just written bytes: second words and skip
widths can affect a preceding page or wraparound PC; a remote branch can change
block leaders; an SCC depends on all its nodes. Block liveness/exit masks and
ABI/compiler policy belong in template identity. LPM reads current native Flash,
so retained code must not bake stale data. Full CFG and portable artifact
serialization still run: no O(changed-bytes) claim.

Measured on Ryzen5 5600X, Windows10.0.26300, Node22.22.3/V8 12.4.254.21:
eight balanced four-position trials, fresh serial Workers, unchanged native,
192 measured observations plus warmups. Sixteen host patches to a rhythmic
image improve by paired median1.91x; this isolates host compilation calls,
not execution. A real erase/write/execute fixture improves1.37x compatible,
1.80x physical and1.89x CLKI, including execution/retranslation. All snapshots,
code hashes, pins and PCM agree. All36 portable artifact cases match baseline.

Cold construction costs extra (paired old/new0.70–0.82x); ordinary IRQ-active
audio is noisy with medians0.955x/0.958x, so no audio gain or real-time admission
is established. Keep opt-in. The earlier eager32-page startup prototype roughly
doubled construction cost and is retained as a rejected startup strategy.

All1957 tests pass:984 instruction/flags/phase cases, cross-page dependencies,
wrapper rebinding/removal, RESET, three-clock SPM, self-erasing its current page,
packages and persistent hits. Browser Workers preserve4096 stereo frames with
798IRQs and40001 CLKI pin observations. Hardware behavior remains unmeasured.

[Implementation contract](../../web-player/native/INCREMENTAL_COMPILATION.md),
[source identities, measurements and reproduction](../../web-player/reports/incremental-compilation-20261026.md).
Primary references: [ATtiny13A SPM](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WASM modules/imports](https://webassembly.github.io/spec/core/syntax/modules.html),
[WASM tables/exports](https://webassembly.github.io/spec/core/binary/modules.html).
