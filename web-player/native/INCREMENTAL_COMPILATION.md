# Incremental AVR compilation and dynamic linking

The full ATtiny13A runtime offers `incrementalCompilation:true`. It is a host
compilation/linking policy, separate from the emulated device, phase behavior,
flag optimization and bounded execution regions. The default remains false.

```js
import {ATtiny13A} from '../lib/attiny13a.js';
const chip = new ATtiny13A(flash, eeprom, {
  ...deviceOptions, incrementalCompilation: true,
});
// The complete original generated module runs initially. CPU SPM later
// updates affected functions while retaining the original dispatcher.
```

`incrementalCompilation:false` explicitly retains ordinary whole-module
retranslation. Both compatible and resumable physical/CLKI execution are
supported, including phase-local and bounded-region policies. Other AVR device
profiles do not yet support incremental linking; their ordinary paths remain
available. No native peripheral implementation, register addresses or virtual
timing changes.

## Compiled code stays live

The initial monolithic module gains private exports for its functions and
dispatch table. Its original runners and mutable CPU globals stay loaded.
The linker replaces entries in the same fixed WASM table after Flash changes.
Unchanged functions continue running from the original compiled instance.
It does not initially compile32 additional page modules.

Changed code is grouped by32-byte Flash pages, taken from the pinned Microchip
`FLASH_PAGE_BYTES` definition. A basic block belongs to its start page; a
cyclic region belongs to the page containing its lowest PC. Instructions,
blocks and regions have stable logical names. A fragment imports the same
native WASM memory and bridges, the original CPU globals, and any generated
functions it calls. These are direct WASM function references, not JavaScript
instruction callbacks. JS handles only compilation/linking at a Flash change.

Before replacement, the emitter re-evaluates whole-image control flow and
dependencies. Encoded standalone instructions are reused only with matching
word/next-word and ABI/compiler policy. Block keys include their sequence,
boundaries and flag masks. Cyclic-region keys cover their full nodes and skip
widths. This handles two-word operands and skips across page/PC-wrap boundaries,
remote branch leaders and regions spanning multiple pages. LPM continues to
read the live native Flash bus; it is not folded to an outdated constant.

An original region wrapper has static calls inside the seed module. If a callee
changes, that wrapper must detach into a new fragment importing the replacement.
Unchanged specialized wrapper bytecode can then reuse its module while creating
a new instance with updated function bindings. Removed blocks/regions disappear
from the dispatch map. All fragments are compiled and instantiated before the
live table changes. An active instruction retains its latched code until
retirement; the existing generation guard defers replacement across a hold.

## Cache and artifact contracts

Manual `clock()` may complete SPM outside the timed/audio runner. Every public
instruction entry (`step`, `run`, compatible `runBlock`) refreshes changed code
before fetching and checks again on return. This applies to ordinary and
incremental compilation, including precompiled packages. It preserves the
active-phase guard; raw time advancement alone does not fetch an instruction.

The runtime identity, exact padded image, ABI and compiler policy separate
whole-image cache entries, including the incremental option. At most eight
entries/16MiB of encoded artifacts/templates are retained per native module;
JS/VM metadata overhead and live instances are additional. Each chip owns its
memory, table, globals and instances; compiled modules can be shared safely.
`cacheTranslation:false` disables the shared whole-image cache. With incremental
linking explicitly enabled, unchanged code within that same live chip is still
retained across SPM.

`core.incrementalCompilation` reports emitted instructions/blocks/regions,
compiled/reused groups, instantiated fragments, seeded groups and changed table
slots. The portable `transpiledBytes` and manifest remain the ordinary complete
artifact, byte-identical to the baseline emitter. Full manifest/portable-artifact
serialization still runs; this is not an O(changed-bytes) implementation.
The diagnostic `reusedModules` counts reused code groups; several groups can
refer to the same original compiled module.

`ATtiny13A.fromPackage(pkg,{incrementalCompilation:true})` preserves the supplied
initial precompiled module. After SPM it builds a linkable seed and subsequent
updates can be selective. The persistent IndexedDB cache partitions the option
and retains portable bytes, not live fragments or function references. A hit
follows the same precompiled-start contract. Packages with their own native
runtime remain self-contained; standalone JS deployment must also include
`lib/avr-incremental-compiler.js`.

## Evidence and scope

All123 instruction forms with four C/Z inputs retain exact half-phase/adjacent-ps
state under internal and unequal external CLKI clocks. Tests cover dependency
boundaries, live LPM, changing policies, cyclic wrapper rebinding/removal,
RESET during RCALL, real SPM under three clocks, self-erasing the executing SPM
page, precompiled packages, persistent hits and IRQ-active physical audio.

The browser Worker verifies4096 stereo frames with798 interrupts and a complete
CLKI self-programming trace with40001 pin observations. After the test page
write, one fragment is compiled and32 code groups are reused; the original
runner and untouched page functions keep their identities. These are software
checks, not silicon or real-time audio admission. External ISP/HVSP/programmer
interfaces remain excluded.

See [controlled timings and exact sources](../reports/incremental-compilation-20261026.md).
The first eager-page prototype is retained as a rejected startup strategy.
The current seed strategy retains explicit opt-in because construction has
extra costs and ordinary firmware does not necessarily benefit from SPM caching.

Primary references: [Microchip ATtiny13A data sheet, sections16.1–16.9](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
[WebAssembly modules and shared imports](https://webassembly.github.io/spec/core/syntax/modules.html),
[binary function/element/export sections](https://webassembly.github.io/spec/core/binary/modules.html).
