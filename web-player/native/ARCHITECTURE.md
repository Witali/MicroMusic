# AVR translation and device boundaries

The project currently registers ATtiny13A. The CPU translator, device-specific
hardware implementation and generated firmware are separate layers.
The virtual device runs a supplied image; external programming interfaces are
excluded by [`EMULATION_SCOPE.md`](EMULATION_SCOPE.md).

| Layer | Source or artifact | Responsibility |
|---|---|---|
| AVR decoder and WASM emitter | `lib/avr-transpiler.js` | Decode machine instructions, lower effects and flags, emit WASM functions and instruction blocks |
| Target registry | `lib/devices/profiles.js` | Select a supported device explicitly and reject unregistered targets |
| ATtiny13A profile | `lib/devices/attiny13a-profile.js` | Flash/data geometry, PC wrapping, register placement and legacy hardware hooks |
| Manufacturer definitions | `vendor/microchip/ATtiny_DFP/3.4.278/` | Original register, bit, fuse, vector and memory definitions with versioned provenance |
| Generated register views | `lib/attiny13a-registers.*`, `native/attiny13a-registers.*` | C, JS, JSON and assembly views of the same official definitions |
| ATtiny13A hardware | `native/peripherals/`, `native/devices/attiny13a/`, `native/avr-device.inc` | Device bus, timers, GPIO, ADC/comparator, sleep/reset, power, NVM and physical time |
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

Generated firmware bytes belong in compiler outputs or package assets. Keep
handwritten device logic in source modules and keep imported manufacturer files
unchanged. Build reports record the source/runtime identity, and the cache
includes the target profile identity. Adding a name to the registry alone does
not establish support for another microcontroller.
