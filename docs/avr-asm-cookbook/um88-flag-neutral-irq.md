# UM88: preserve flags without saving them on the normal IRQ path

Original MicroMusic technique measured on ATtiny88 / AVR25, GNU AVR GCC
7.3.0, GNU ABI, `-Os -fno-jump-tables -ffunction-sections -fdata-sections
-Wl,--gc-sections`. It changes the hardware FIFO driver, independently of
musical arithmetic, dictionary compression or output-channel selection.
The portable C ISR remains explicitly selectable with `--backend c`.
Handwritten assembly requires both `__AVR_ATtiny88__` and the explicit
`UM_ENABLE_AVR_ASM=1` opt-in.

## Where the cycles go

The player's maximum ISR measurement starts when the interrupt is accepted
and ends after `RETI`. It includes four hardware-entry cycles, the actual
two-cycle vector `RJMP`, and four return cycles. It excludes waiting for the
interrupted instruction to finish or for interrupts to become enabled.

The previous fixed mono ISR (`8a0da608`) takes 44 cycles, including entry and
return; stereo takes 48. An earlier mono image (`41e456a9`) takes 52.
Those 52 divide into 10 cycles for hardware entry/vector/return, 18 for
register/SREG backup and restoration, and 24 for FIFO/PWM work. The earlier
image spends eight extra cycles forming a full FIFO pointer, reading/testing
the runtime channel count and converting the pointer back to a cursor.

| Normal path, 192-byte ring | Previous mono | Stack mono | GPIOR mono | GPIOR stereo |
| --- | ---: | ---: | ---: | ---: |
| Hardware entry and vector | 6 | 6 | 6 | 6 |
| Save working registers / flags | 9 | 6 | 3 | 3 |
| Read cursors and test empty | 6 | 7 | 7 | 7 |
| Read FIFO and write PWM | 5 | 5 | 5 | 9 |
| Wrap and publish cursor | 5 | 6 | 6 | 6 |
| Restore working registers / flags | 9 | 6 | 3 | 3 |
| `RETI` | 4 | 4 | 4 | 4 |
| **Total** | **44** | **40** | **34** | **38** |

At one IRQ per 256 CPU clocks, mono IRQ occupancy falls from 17.19% to
13.28% of CPU time. The ten saved cycles are 1.25 microseconds at 8 MHz or
0.625 microseconds at 16 MHz. Output frequency, sample values and event
schedule are unchanged. These are emulator measurements, not oscilloscope
measurements on physical hardware.

## Make the common path flag-neutral

`CPSE` compares the FIFO cursors without changing SREG. Wrap uses another
`CPSE` against an `LDI` capacity, rather than `CPI`/`BRCS`. Loads, stores,
`LDI`, `RJMP`, `PUSH`/`POP` and `IN`/`OUT` also preserve the flags. Consequently
the normal path need not save SREG. The diagnostic empty path still saves
and restores it around `INC um_underruns`, using the already-backed-up r27.
That path never needs the X pointer, so no extra stack round-trip is required.

For power-of-two byte capacities (8, 16, 32, 64 or 128), `SBRC` tests the
single wrap bit and conditionally executes `LDI XL,0`. Both outcomes take
two cycles, preserve SREG and save another two cycles. Other supported
capacities use the general comparison. This depends on a page-aligned ring,
valid byte cursors, a fixed one/two-byte frame stride and capacities divisible
by four. It does not extend to arbitrary pointer arithmetic or a 256-byte ring.

## Optional GPIOR backup

The default `--irq-scratch stack` preserves the three working registers on
the stack and reserves no I/O register. Explicit `--irq-scratch gpior`
instead backs up r16, XL and XH using single-cycle `OUT`/`IN` to GPIOR0/1/2.
Their definitions come from the pinned Microchip ATtiny_DFP header.
No CPU registers are reserved across foreground code.

This profile exclusively owns all three GPIOR registers. Foreground code,
other ISRs and libraries must not use them while this driver is active.
The ISR must remain non-nested: it never executes `SEI` and must not be
changed to `ISR_NOBLOCK`. It overwrites every backup before reading it,
so power-on or Micronucleus-inherited GPIOR contents require no initialization.
Neither path needs a software stack byte when GPIOR backup is selected.

`irq-scratch.h` defaults `UM_IRQ_GPIOR_SCRATCH` to zero. The builder passes
`UM_REQUESTED_IRQ_GPIOR_SCRATCH` and rejects a conflicting platform header
before publishing output. Reports record the requested/effective choice and
`reservedIORegisters`. The C fallback uses compiler-managed register backup,
does not use GPIOR, and produces identical code for either scratch request.

## References and validation

- [ATtiny48/88 datasheet 8008H](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf):
  section 4.8.1 (interrupt response), register summary and instruction timings.
- [Microchip AVR instruction set manual DS40002198C](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/ReferenceManuals/AVR-InstructionSet-Manual-DS40002198.pdf):
  `CPSE`, `SBRC`, `LDI`, `LD`, `STS`, `IN` and `OUT` flag semantics.
- [Driver](../../ATtiny88/Music/universal/irq-avr.S),
  [resource selection](../../ATtiny88/Music/universal/irq-scratch.h),
  [builder tests](../../tools/test-universal-irq-config.py).

The generic 192-byte path removes two bytes of code; the power-of-two 128-byte
path removes six bytes. Static SRAM and the FIFO location do not change.
GPIOR backup removes four stack bytes from the previous normal path.
Detailed test reports accompany the release; each measured claim applies
only to its recorded binaries and workloads.

Runtime source commit: `223f9cc3`. The [isolated driver matrix](../../ATtiny88/Music/universal/reports/irq-driver-verification.json)
executes 329,940 cases across 282 compiled configurations: all 47 byte
capacities, both channel counts and C/stack/GPIOR drivers. It covers every
8-bit register/counter value, all 128 interrupted flag combinations,
nonzero r1, inherited GPIOR contents, exact empty/wrap behavior and strict
mono OCR1A non-access. Stack use including the two-byte return PC is five
bytes for stack backup and two for GPIOR on either path. Empty paths take
37/31 cycles respectively. Tests use the actual production ISR and vendor
definitions; no checks are added to firmware.

[Release comparison](../../ATtiny88/Music/universal/reports/irq-optimization.json)
records all 18 full loops/restarts with active interrupts, current binary
hashes, unchanged compressed musical payload, four unchanged WAV previews
and independent C/ASM/reference arithmetic checks. The selected 128-byte
fast-dictionary and 192-byte compact-dictionary examples both meet their
deadlines; smaller buffers are not thereby qualified.
