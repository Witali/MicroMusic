# AVR translation and device boundaries

The project currently registers ATtiny13A. The CPU translator, device-specific
hardware implementation and generated firmware are separate layers.
The virtual device runs a supplied image; external programming interfaces are
excluded by [`EMULATION_SCOPE.md`](EMULATION_SCOPE.md).

| Layer | Source or artifact | Responsibility |
|---|---|---|
| AVR decoder and WASM emitter | `lib/avr-transpiler.js` | Decode machine instructions, lower effects and flags, emit WASM functions and instruction blocks |
| CPU continuation lowering | `lib/avr-wasm-phases.js` | Split generation-time clock barriers into saved phases; emit native WASM control and local spills without an opcode interpreter |
| Phase temporary analysis | `lib/avr-phase-locals.js` | Optional generation-time local/branch annotations and backward liveness; strip annotations before serialization, retaining the full-context oracle |
| Target registry | `lib/devices/profiles.js` | Select a supported device explicitly and reject unregistered targets |
| ATtiny13A profile | `lib/devices/attiny13a-profile.js` | Flash/data geometry, PC wrapping, register placement and legacy hardware hooks |
| Manufacturer definitions | `vendor/microchip/ATtiny_DFP/3.4.278/` | Original register, bit, fuse, vector and memory definitions with versioned provenance |
| Generated register views | `lib/attiny13a-registers.*`, `native/attiny13a-registers.*` | C, JS, JSON and assembly views of the same official definitions |
| ATtiny13A hardware | `native/peripherals/`, `native/devices/attiny13a/`, `native/avr-device.inc` | Device bus, timers, GPIO, ADC/comparator, sleep/reset, power, NVM and physical time |
| ATtiny13A CLKI source | `native/devices/attiny13a/clki_{input,clock,periodic,validation}.*`, `clki_board.inc` | Bounded source edges, digital divider phase, finite periodic production and optional ideal timing qualification on the shared PB3 pad |
| Shared generated-CPU loader | `lib/avr-transpiled-runtime.js` | Link emitted CPU functions to their native ABI and maintain the translation cache |
| ATtiny13A host API | `lib/attiny13a-runtime.js` | Device configuration, queued external inputs, diagnostics and native pin capture |
| Native runtime WASM | `wasm/attiny13a.wasm` | Compiled peripheral implementation and ABI bridges, with no host imports |
| Translated firmware WASM | CLI output or package `assets.translated` | Generated CPU functions for the supplied Flash image |
| Portable package | `lib/attiny13a-package.js` format | Keep firmware, native runtime, initial memories, profile configuration and manifests as distinct assets |

All current files under `native/peripherals/` implement the ATtiny13A hardware
model. New device-owned modules, including the analog RESET receiver, live in
`native/devices/attiny13a/`; its build selects those sources explicitly.
A second microcontroller requires its own profile, bus/peripheral
implementation, native bridge and validation. Device-specific addresses and
memory sizes belong in that profile and its manufacturer definitions. The
shared emitter consumes the normalized geometry. Its current data/PC lowering
supports eight-bit data addressing and a two-byte program counter; extending
that geometry requires explicit CPU lowering work and tests.

The generated CPU module and native runtime share one WASM memory. Instruction
effects call native WASM bridges, which advance the selected device scheduler.
Pin transitions and audio integration stay in native memory. Host calls operate
on batches or queued inputs. Modified Flash regenerates the CPU module while
the hardware instance retains its state.

The optional `resumable:true` execution mode uses the native80-byte phase
context described in [`devices/attiny13a/cpu_phase.md`](devices/attiny13a/cpu_phase.md).
It preserves instruction/IRQ progress across physical observation deadlines.
It supports the internal physical clock with an explicit OSCCAL table and the
external CLKI profile without a dummy RC table. CLKI transitions enter the
device-owned native source queue, update PB3 and drive the divider, startup,
sleep gates and peripheral clock domains. Known high/low holds preserve phase;
an unknown input horizon returns `WAIT_INPUT`. Independent physical-time
domains continue during a stopped source.

Finite `highPs`/`lowPs`/transition-count descriptors lazily refill the same
512-edge queue in C. They avoid JS work per edge; the scheduler still services
each externally observable source edge rather than skipping the signal
analytically. The named initial/divider phase is a deterministic digital policy,
with optional ideal timing qualification and no measured silicon-phase claim.
Package v5 preserves the execution mode and initial CLKI profile and validates
the continuation ABI. Earlier package versions retain their original contracts;
they do not acquire a saved continuation or source queue.

Generated firmware bytes belong in compiler outputs or package assets. Keep
handwritten device logic in source modules and keep imported manufacturer files
unchanged. Build reports record the source/runtime identity, and the cache
includes the target profile identity. Adding a name to the registry alone does
not establish support for another microcontroller.
