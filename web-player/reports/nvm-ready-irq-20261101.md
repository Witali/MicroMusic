# Flash erase, NVM ready interrupt and stopped CLKI

New generated-firmware integration checks confirm the existing NVM/IRQ
behavior without changing production code or artifacts. The authoritative
[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
section 5.6.4 describes EE_RDY as a level for nonvolatile-memory readiness.
Sections 4.7 and 9 specify interrupt priority and the main instruction after
RETI; section 16 describes the CPU halt during Flash programming. EE_RDY thus
stays suppressed while the Flash controller is busy, even when EEPROM is idle.

The source-only fixture configures GPIO, Timer0 and EERIE, then executes SEI
immediately followed by SPM. The SEI delay permits the erase to start before
the ready interrupt. Page 30 contains non-erased data outside executing code;
the test observes its erasure and a generation increment. Timer0 is either
masked or has a pending overflow. Its ISR disables that mask and toggles PB0.
The EE_RDY ISR records the main-program progress byte (R18), disables EERIE and
toggles PB0. The recorded byte distinguishes whether the required main INC
ran between the two interrupts.

Four scenarios run in both verification and optimized CPU policies:

| Scenario | Required outcome |
| --- | --- |
| Internal source, Timer0 masked | EE_RDY ISR runs once after erase completion |
| Internal source, Timer0 enabled | Timer0 ISR, one main instruction, then EE_RDY ISR |
| CLKI held low | Flash completes in wall time; CPU/stack/ISR effects wait for more phases |
| CLKI held high | Same independent completion and source-phase requirement |

The explicit fixture uses a 1 MHz source, zero startup and the selected maximum
4.5 ms Flash-erase duration. SPM starts at 17 us in this digital phase model;
the check brackets completion at 4517 us and 1 ps before it. This is not an
observed silicon erase time or proof of internal bus phases. CLKI uses actual
queued 700 ns high / 300 ns low transitions, followed by a published hold and
a second batch. Timer0 remains pending during the CPU halt; accepting EE_RDY
does not clear its level. Both ISRs finish after source phases resume.

All **56 focused checks** pass, including four new paired scenarios/eight
executions plus existing NVM, system and CLKI cases. The paired scenarios
compare data/SREG/stack, Flash/EEPROM, PC/cycles, IRQ counts, continuation state
and exact pin timestamps. No host per-edge callback is introduced. Runtime,
compiler, cache identity and peripheral code are unchanged. The preceding
2669-test default suite belongs to commit `742c7031`; no new full-suite total
is claimed for this test-only addition. The plan remains **24/31**, seven open.

Reproduce from the repository root:

```text
node --test web-player/tests/attiny13a-nvm-ready-irq.test.mjs web-player/tests/nvm.test.mjs web-player/tests/attiny13a-device-system.test.mjs web-player/tests/attiny13a-clki-runtime.test.mjs
```

The native runtime remains SHA-256
`0e00866562e59ab8a40bb7295889386f7132b9a3d7e2c63ba02a804f387135a3`.
Raw TAP stays local under `build/nvm-ready-irq-focused-final-20261101.tap`.
Its SHA-256 is
`6a82b0a15457ad69e0210b45eebfe9bf5040e36b54158fb9a58edd27016ae020`.
The new test source, normalized from CRLF to LF, is SHA-256
`438d5d01d60f6e3c9b732b3cacdd2b5f8b60565d8993dd37a38914c3567401dd`.
The original manuals/definitions/toolchain are reused; no download or
installation occurred, and no official simulator or physical capture was used.
