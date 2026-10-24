# Another 24 bytes from the ordinary floor Q3 core

A controlled assembly-only probe reduces the qualified Vinni core from
**392 to 368 bytes**, preserving every output sample and the complete speech
stream. The same phrase now occupies **990 Flash + 64 EEPROM bytes**, compared
with 1014 + 64. This is a storage/runtime improvement; STOI and spectrum are
unchanged. Public firmware and the production builder remain unchanged.

## Separate measured steps

Each row includes the preceding transformations. Every stage is assembled and
run independently against the frozen integer decoder in all three engines.

| Stage | Code bytes | Full phrase Flash | Minimum slack, cycles |
| --- | ---: | ---: | ---: |
| Frozen ordinary floor baseline | 392 | 1014 | 332 |
| Dedicated IRQ registers | 380 | 1002 | 358 |
| Preserve the zero high byte of Y | 378 | 1000 | 361 |
| Use vacant reset-vector words | 374 | 996 | 361 |
| Scale EEPROM taps and exchange multiply operands | 368 | 990 | 352 |

The final stream remains 620 bytes; EOF and alignment account for two more.
The baseline binary matches the previously qualified image SHA256
`b9cf233d73fe4b8f50e08505160fa9638863336a96d93e3951e1ff51ff1e7177`.
All five stages have phrase PCM SHA256
`4155925af8a10464f0b3b7c26973ee2963adc514bb670ed6f93d9533ae7c4e12`.

1. **Reserve registers for IRQ work: 12 bytes.** Move frame-mode bits from
   r22 to the otherwise unused r14. Use high register r22 for the IRQ countdown
   and reserve r12 for saved SREG. The handler no longer needs to preserve r16
   with PUSH/POP; the direct high-register LDI also removes two copies during
   initialization/reload. After startup, the main loop must leave them alone.
   Nested interrupts are not enabled. Maximum measured ISR length falls from
   28 to 19 cycles, and stack high-water use from 6 to 4 bytes.
2. **Keep YH zero: 2 bytes.** r29 is initialized once and no other instruction
   changes it. Remove its duplicate CLR in the coefficient reader. This relies
   on the audited whole-program register convention, not an external C ABI.
3. **Use unused vector words: 4 bytes.** Put CLI, CLT and RJMP reset at byte
   addresses 0, 2 and 4. The Timer0 vector remains at 6; initialization starts
   at 8 without repeating CLI/CLT. Hardware reset enters address zero, and only
   the Timer0 overflow interrupt is enabled. Revisit this layout if adding IRQs
   or a software entry that bypasses the reset prefix.
4. **Move a scale into EEPROM: 6 bytes.** Store each logical tap multiplied by
   eight, read it into the sample operand, and use gain as the nonnegative
   coefficient. The existing wide multiplier computes
   `floor((8*tap)*gain/8) = tap*gain`. This removes three LSL instructions.
   Bounds are tap −7…7 and gain 0…15, so scaled samples remain within −56…56
   and products within ±840. Gain can require more addition iterations than
   a tap, so this step spends some timing slack; it is not a speed claim.
   **The new firmware and scaled EEPROM image must be programmed together.**

## Qualification and limits

Five full Vinni builds match all 66,816 samples each in reference, WASM and
unoptimized WASM, including two phrase lengths of midpoint silence. There
are no missed samples, lost overflows or arithmetic wraps for this phrase.
No filtering, recentering, level normalization or new quality fitting occurs.
The existing DC and strict 5-dB problems therefore remain.

Three further final-profile builds exercise:

- Full/low/high/repeat coefficient updates, compact/extended durations, noise,
  all source modes and short periods: 4,800 output samples per engine.
- All 16 gains and all four modes, including noise and periods 1/4/63/64/126:
  12,288 samples per engine. This is an arithmetic fixture, not a quality claim.
- A full 655-byte stream plus EOF: **1024 actual Flash bytes + 64 EEPROM**,
  21,312 output samples per engine. This proves the expanded physical capacity.

The real excitation path is separately checked for all 64 table addresses,
16 gains, three initial flag patterns and three engines: **9,216 cases**.
The real IRQ is checked for all 128 non-I SREG states, two countdown branches,
ready/not-ready and three engines: **1,536 cases**. This confirms preservation
of every non-reserved register, SREG/T, output gating, stack and RETI behavior.

Timing figures are measurements of these inputs at 9.6 MHz / 7,500 Hz, not
universal bounds for arbitrary future streams. Physical hardware is untested.
Only the ordinary floor profile is qualified here; nearest/pole variants have
not been silently changed. Source and dependency fingerprints, compiler,
individual builds and verification results are in [report.json](report.json).

## Reproduction

Configure the repository's Python codec dependencies, then run from its root:

```powershell
python tools/probe-q3-core-compaction.py --model ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json --avr-bin <AVR-bin> --node <Node-executable> --retain ATtiny13A/Sound/research/q3-core-compaction/report.json
```

No ignored input files are needed. The probe extracts the frozen assembly with
guarded substitutions and emits all eight source/firmware/EEPROM images under
ignored `build/q3-core-compaction/`. It also accepts an explicit logical
`--stream ... --table ...` pair. Review transformations if the frozen source
changes; it rejects missing/ambiguous substitutions rather than guessing.
