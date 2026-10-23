# AVR machine code to WebAssembly

The experimental translator accepts ATtiny13A Flash bytes, including decoded
Intel HEX. It emits a real WebAssembly binary directly, without AVR sources,
Clang, Emscripten, WAT assembly or runtime opcode interpretation. The browser
can translate a firmware image when it is loaded; the CLI can do it in advance.

The translator now lowers all 123 ATtiny13A instruction-summary forms.
Forms include aliases and addressing variants, not 123 distinct opcodes.
119 forms execute their CPU semantics directly; SLEEP, WDR, BREAK and SPM
also connect to the device-control protocol described below. The production
C/JS interpreters still support their previous 105 forms. Invalid words fail
only when executed; embedded
Flash data remains available unchanged to LPM. This is a prototype
for the retained firmware, not a complete ATtiny/ATmega implementation.

## Official references

- [Microchip AVR Instruction Set Manual, DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf): instruction encodings, per-bit SREG equations, AVRe timings and device applicability. Section numbers below refer to this PDF, not the differently numbered online edition.
- [Microchip ATtiny13A Data Sheet, DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf): sections 4–5 (CPU/memory/interrupts), 11–12 (Timer0/prescaler), 21 (instruction summary).
- [WebAssembly Core: binary instructions](https://webassembly.github.io/spec/core/binary/instructions.html), [integer/value encodings](https://webassembly.github.io/spec/core/binary/values.html), [module sections](https://webassembly.github.io/spec/core/binary/modules.html), [instruction semantics](https://webassembly.github.io/spec/core/exec/instructions.html).

The existing reviewed `reports/attiny13a-instructions.json` retains source
hashes, all 123 forms, opcode patterns, cycle counts and flag-write masks.
Tests compare the new independent decoder against all 65,536 possible first
words and that official-document fixture, rather than the interpreter decoder.

## Instruction correspondence

The primary operation is shown, not the entire expansion. Registers reside in
the shared AVR data image and are loaded into WASM locals within a block.
`i32.store8` truncates register writes to eight bits; intermediate results are
masked to 255 when flags need the wrapped result. WASM has no AVR SREG or
8-bit arithmetic type. Only live flag bits are calculated in optimized blocks.

| AVR forms | Closest emitted WASM operations (opcode hex) | Additional AVR behavior |
| --- | --- | --- |
| `NOP` | no data operation | Advance PC and one CPU cycle. |
| `LDI`, `SER` | `i32.const` (`41`), `i32.store8` (`3a`) | `SER` is `LDI Rd,255`; SREG unchanged. |
| `MOV` | `i32.load8_u` (`2d`), `i32.store8` (`3a`) | SREG unchanged. |
| `MOVW` | two byte loads and stores | Copy the even register pair; SREG unchanged. |
| `ADD`, `LSL` | `i32.add` (`6a`) | Wrapped result and live `H,S,V,N,Z,C`; `LSL` is `ADD Rd,Rd`. |
| `ADC`, `ROL` | two `i32.add` (`6a`) | Read C; `ROL` is `ADC Rd,Rd`. ADC Z depends only on the new result. |
| `SUB`, `SUBI`, `NEG` | `i32.sub` (`6b`) | `NEG` subtracts from zero; live arithmetic flags. |
| `CP`, `CPI` | `i32.sub` (`6b`) | Compute live flags without writing Rd. |
| `AND`, `ANDI`, `CBR`, `TST` | `i32.and` (`71`) | Live Z/N/S, clear live V; preserve C/H/T/I. `TST` is `AND Rd,Rd`. |
| `OR`, `ORI`, `SBR` | `i32.or` (`72`) | Same flag behavior as AND. |
| `EOR`, `CLR` | `i32.xor` (`73`) | `CLR` is `EOR Rd,Rd`; same flag behavior as AND. |
| `COM` | `i32.xor 255` (`73`) | Complement eight bits; C=1, V=0; live Z/N/S. |
| `INC`, `DEC` | `i32.add 1` / `i32.sub 1` | Preserve C/H/T/I; V at 0x80 / 0x7f respectively. |
| `LSR` | `i32.shr_u` (`76`) | Old bit 0 becomes C; update live Z/N/V/S. |
| `ASR` | `i32.load8_s` (`2c`), `i32.shr_s` (`75`) | Sign extend first; mask the result to eight bits. |
| `ROR` | `i32.shr_u`, `i32.shl` (`74`), `i32.or` | Insert old C at bit 7; old bit 0 becomes C. A 32-bit `rotr` would be incorrect. |
| `SWAP` | `i32.and`, `i32.shl`, `i32.shr_u`, `i32.or` | Exchange the two nibbles; SREG unchanged. |
| `BSET`, `BCLR`, `SEC/CLC`, `SEN/CLN`, `SEZ/CLZ`, `SES/CLS`, `SEV/CLV`, `SET/CLT`, `SEH/CLH` | `i32.or` / `i32.and` | Change exactly one SREG bit. SET also preserves the player's work-loss diagnostic. |
| `SEI`, `CLI` | `i32.or` / `i32.and` | SEI has the documented interrupt acceptance delay. |
| `BRBS`, `BRBC`, `BREQ/BRNE`, `BRCS/BRCC`, `BRSH/BRLO`, `BRMI/BRPL`, `BRGE/BRLT`, `BRHS/BRHC`, `BRTS/BRTC`, `BRVS/BRVC`, `BRIE/BRID` | bit test, `if` (`04`), constant PC | Read the selected SREG bit; one or two AVR cycles. |
| `RJMP` | constant PC, generated function-table dispatch | Two AVR cycles. WASM `br` addresses structured labels, not arbitrary Flash addresses. |
| `RCALL`, `RET` | byte stack loads/stores, PC, function-table dispatch | Preserve the observable two-byte AVR return address in SRAM; three/four cycles. Native WASM `call/return` alone would be incorrect. |
| `RETI` | RET expansion plus I-bit/IRQ state | Four cycles, interrupt delay and nested-ISR accounting. |
| `SBRC`, `SBRS` | bit test, `if`, constant PC | Skip one or two words; one/two/three cycles. |
| all `LD`/`LDD` X/Y/Z forms | `i32.load8_u` (`2d`) | Plain, pre-decrement, post-increment and Y/Z displacement; two cycles. |
| all `ST`/`STD` X/Y/Z forms | `i32.store8` (`3a`), or peripheral write helper | Same pointer modes; I/O side effects occur at the completing cycle. |
| `LDS`, `STS` | byte load/store, constant address | Two-word instruction, two cycles; I/O addresses use the peripheral model. |
| `LPM Rd,Z`, `LPM Rd,Z+` | Flash `i32.load8_u`, optional pointer increment | Three cycles; byte address differs from word-addressed PC. |
| `IN`, `OUT` | byte load / peripheral write helper | Clock the one AVR cycle before observing/changing I/O. |
| `SBI` | load, `i32.or`, peripheral write helper | Two cycles and the same I/O behavior as OUT/ST. |
| `PUSH`, `POP` | byte store/load and SPL adjustment | Two cycles, shared SRAM stack and explicit bounds diagnostics. |

For this <=256-byte data space, LD/ST use and update only the low pointer
byte. XH/YH/ZH remain usable as general registers (manual 5.66–68 and
5.114–116). LPM uses the program-memory Z pointer instead.

The additional CPU forms are implemented and tested against the individual
instruction descriptions, independently of the older interpreter subset:

| Additional AVR forms | Implemented lowering |
| --- | --- |
| `ADIW`, `SBIW` | `i32.add/sub`, 16-bit result and word-operation flags. |
| `SBC`, `SBCI`, `CPC` | `i32.sub` with carry/borrow and chained Z. |
| `IJMP`, `ICALL` | Z-derived PC and generated function-table dispatch; ICALL pushes AVR PC. |
| `CPSE`, `SBIC`, `SBIS` | comparison/bit test and length-aware skip; I/O timing for SBIC/SBIS. |
| `CBI` | I/O read/AND/write at the correct cycle. |
| `BST`, `BLD` | bit extraction/insertion involving SREG T. |
| operandless `LPM` | Flash byte load into r0; separate encoding from `LPM Rd,Z`. |
| `SPM` | Export a Flash-controller request; its actual latency comes from the device model. |
| `SLEEP`, `WDR`, `BREAK` | Observe sleep enable / watchdog / debugger state and use the device boundary protocol. |

ATmega instructions and peripherals, including devices with 16-bit data
pointers, larger PC/Flash, additional timers and extended I/O, need a separate
device profile. `MUL`, long `JMP/CALL`, `ELPM` and extensions of other AVR cores
are not part of the ATtiny13A target.

## Flags and cycle synchronization

A backward pass computes `needed = written & live`, then
`live = (live & ~written) | read`. For example, ADD followed by ADC needs
ADD's C, while its other flags can be omitted if overwritten before use.
The emitter generates equations only for needed bits. The CLI switch
`--no-flag-dce` disables elimination for differential checks.

The pass currently operates within straight-line basic blocks, with all SREG
bits live at block exits. This deliberately preserves exact debugger, SREG
read, branch and interrupt-handler observations. It is not whole-program
flag elimination or a lazy-flags scheme. A future global pass must model
interrupt entry as a possible reader of SREG.

CPU time is a count of original AVR cycles, stored as f64 exact integers
beyond 2^32 (up to 2^53). Each optimized block consists of fixed-cycle
instructions with no I/O, stack or interrupt-control operations. Guarded
LD/ST accesses are restricted to SRAM and LPM to valid Flash addresses. A
guard exits before register/I/O aliases, undefined pointer combinations or
invalid addresses; it flushes exact flags, PC and elapsed cycles, then the
generated single-instruction path performs the access or reports its fault. It
runs only when its end is strictly before the next Timer0 event and at or
before the caller's deadline. Pending interrupts or SEI/RETI delay disable
blocks. TCNT0 and prescaler phase advance by exactly the block's AVR cycles.
An event-boundary fallback still executes **generated WASM**, one AVR
instruction at a time, then advances timers and checks interrupt acceptance.
It never falls back to the C opcode interpreter.

I/O is clocked at the completing AVR cycle; EEPROM-read stalls add four
cycles. Hardware IRQ entry adds its four cycles, and vector instructions
are then executed normally. No browser wall-clock time drives MCU timers.
This provides cycle-consistent behavior for the existing peripheral model;
it does not add physical PWM edges, ADC, pin transitions or unsupported
timer modes. See the existing ATtiny13A audit for those limitations.

## Files and use

- `lib/avr-transpiler.js`: independent decoder, liveness analysis and binary emitter.
- `lib/avr-transpiled.js`: generated CPU plus the existing WASM peripheral runtime.
- `scripts/transpile-avr.mjs`: HEX/BIN to WASM and a JSON report with PC mapping,
  flag masks, optimization counts, runtime ABI and SHA-256 provenance.
- `tests/avr-transpiler.test.mjs`: official opcode coverage, exhaustive byte ALU
  cases, exact SREG observations, event boundaries, stack/I/O, music and speech.

From the repository root:

```powershell
node web-player/scripts/transpile-avr.mjs ATtiny13A/Music/variants/lumiere-stereo/synth.hex build/avr-transpiler/lumiere.wasm
node --test web-player/tests/avr-transpiler.test.mjs
```

The emitted module imports `avr.memory`, `avr.clock`, `avr.interrupt`,
`avr.writeIO` and `avr.idle`; those functions are WASM exports from `wasm/avr.wasm`, not JS
instruction callbacks. The module exports `step()`,
`block(f64 deadline, i32 instructionLimit) -> i32`,
`run(i32 instructionLimit) -> i32` and `nextDuty() -> i32`.
`capturePWM(i32 frames, i32 channels) -> i32` writes up to 4096 duty frames
per call to the dedicated PWM scratch region named by `abi.pwm`.
Bind the exact runtime ABI recorded in its custom section/JSON and initialize
that runtime with the same Flash/EEPROM. The module does not initialize the
runtime or contain a separate copy of Flash constants. Its function table
dispatches by AVR address to already generated code, not by opcode.

In JavaScript, use `new AVRCore(flashBytes, eepromBytes)` from
`lib/avr-transpiled.js` for automatic generation and binding. `step()` retains
all flags; `run()` and `nextDuty()` can use optimized blocks. Flash is immutable
for the lifetime of a translated CPU: construct a new instance to load a
different firmware. Do not mutate the debugger's underlying Flash view.

The prototype keeps registers in shared memory and compiles every Flash word
as a possible entry, including data. Module size and load-time compilation
are costs to measure, not evidence of a speedup. Benchmarks must distinguish
construction/compilation from warmed execution and compare both flags-on
and flags-eliminated runs with equal AVR timing and output.
Static optimization counts cover all potential code entries, including
decodable data words; they are not weighted by actual execution frequency.

For the existing player's Timer0-only interrupt profile, `nextDuty` and PWM
capture also reuse the C/WASM wait-loop accelerator. It recognizes self-jumps,
T-bit wait branches and the player's five-instruction arithmetic wait loop,
advancing by whole loop iterations to the Timer0 boundary with the same
registers, flags and elapsed AVR cycles. It does not execute an opcode
interpreter or call JavaScript. `fastIdle:false` disables it; instruction-counted
`run` and `step` always execute the requested instructions. The accelerator's
deadline/IRQ assumptions must be replaced by the full peripheral scheduler
before enabling additional interrupt sources in this playback path.

## MCU instruction/device boundary

No generated instruction calls JavaScript. The four MCU-control instructions
have these semantics with the current peripheral model:

- SLEEP with MCUCR.SE=0 completes in one cycle. With SE=1 it completes the
  instruction, publishes `controlRequest=1` and stops execution before the
  next instruction. Sleep-mode clocks and wake sources require the later
  peripheral model.
- SPM publishes request 2 and stops before charging programming time. A Flash
  controller must supply the real latency; the compiler does not invent a
  fixed cycle count. Flash mutation also requires retranslation before the
  CPU resumes, which belongs to the deferred Flash-controller work.
- WDR completes in one cycle and records `watchdogResetCycle`. With an active
  watchdog it publishes request 3 for a device model to handle. A disabled
  watchdog needs no callback.
- BREAK with the debugger disabled acts as the documented one-cycle NOP.
  When `debugEnabled` is set, it publishes request 4 and stops after the
  instruction. Firmware SREG is preserved.

`step`, `run` and `nextDuty` stop at a pending device request. The JS wrapper
reports the missing device service explicitly. A debugger/device scheduler
can inspect the request and use `acknowledgeControl(extraCycles)` to resume;
SPM requires a positive actual latency. This handshake establishes CPU-side
instruction coverage. It is **not** an implementation of active sleep/wake,
watchdog expiry, debugWIRE or Flash programming; peripheral emulation remains
a separate agreed next stage.

`attiny13a-transpiled-isa.test.mjs` covers every word operand and immediate for
ADIW/SBIW, all byte pairs and C/Z combinations for SBC/SBCI/CPC, T transfers,
indirect calls, skip lengths/timing, and these device-control boundaries.

## Buffered PWM output

The translated renderer captures an entire batch inside WASM, writing mono
duty bytes or interleaved left/right duty bytes into reserved WASM memory.
It performs no JavaScript callback for any AVR instruction or output value.
The JS consumer copies a batch (up to 4096 PWM frames per boundary crossing)
and resamples/filters it. The renderer forecasts exactly the number of PWM
frames consumed by the requested audio block using the same floating-point
phase updates as its resampler; CPU state does not run ahead at block exit.

`AVRCore.capturePWM(count, channels)` returns Uint8Array mono values or
Uint16Array packed stereo values. Large requests are split into bounded
WASM captures. Device state, memory and output after each capture are
checked against single-step execution, including sizes above 4096 and
arbitrary audio boundaries at 8/22.05/44.1/48/96 kHz.

This buffer currently holds the existing player's stream of OCR duty
updates, not reconstructed physical PB0/PB1 edges. Actual compare-pin
waveforms and double-buffered timer semantics belong to the new Timer0
peripheral module. Resampling/filters still execute in JavaScript, outside
WASM; this is not a callback from the CPU into JS.
