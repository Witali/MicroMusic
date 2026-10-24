# ATtiny13A CPU phase acquisition tooling, 2026-10-24

[The acquisition program](../native/peripherals/cpu-phase-probe.md) adds22
independently assembled profiles for stack operations, calls/returns, real IRQ
entry, SRAM addressing, LPM, PIN reads and two-word skips. It uses the pinned
manufacturer header and shared wire-v2 sender. This supplies executable tools
for later hardware measurements; it does not supply silicon observations or
change the default CPU phase model.

## Integrated software verification

The [verification data](cpu-phase-probe-20261024/verification.json) retains
source/config/sender/decoder/header/runtime/library identities, ELF symbols,
image/generated-module hashes, decoded raw bytes, exact queued reset times and
waveform hashes. Actual AVR binaries run through the generated CPU and native
board with finite continuous external CLKI at4kHz, not host register substitutes.

- All22 images fit Flash at710/712/714 bytes, with zero data/BSS.
- Uncut runs plus114 reset cuts give136 functional runs and544 decoded frames.
- Each run retains all32000 source transitions. The native ring is drained
  every128 source half-cycles; CPU and peripheral phases remain processed.
- Reset is queued before execution at selected half-cycle boundaries and their
  adjacent picoseconds. These exact ties test the explicit digital convention,
  not the physical RESET receiver or pad propagation.
- Memory/GPR snapshots are saved before test reinitialization after reset.
  The encoder's four-byte stack is disjoint from snapshots and tested bytes.
- Uncut marker spans include actual target/vector/callee instructions. CALL
  return PC256 and IRQ return PC255 come from ELF labels at the low-byte
  boundary, exposing both stack bytes independently.
- IN uses known pre-marker pins and the declared immediate OUT→IN convention
  as its oracle. The CLKI self-read bit alone is masked in assertions; every
  raw result byte remains retained. LPM tests both evena9 and odd36 Flash bytes.

For example, the RCALL image serializes these retained TEST0/1 bytes after
reset in the current model:

| Cut relative to marker | TEST0/1 |
| --- | --- |
| At C2 | 11/22 |
| 1ps after C2 | 11/00 |
| At C3 | 11/00 |
| 1ps after C3 | 01/00 |

These are serialized software observations under the selected C2/C3 write
contract. They demonstrate that the probe can retain partial stack effects;
they do not establish those internal phases on a chip.

## Transport compatibility and remaining limits

The decoder now supports strict restartable pairs: boot0/1, optional
completion2/3, then a new boot0/1 after reset. Incomplete pairs are rejected even
when received frames have valid checksums. Explicit recovery retains both raw
bit fragments and semantic `sequenceGaps`; missing bytes are never invented.
All18 common protocol tests and five legacy Timer0 decoder tests pass.

[Compatibility verification](cpu-phase-probe-20261024/previous-probe-compatibility.json)
also reruns all25 existing CLKPR/RESET/ADC images with the updated decoder and
current native runtime:59 decoded frames, all software controls passed. The
production change integrated with these tools is separately documented in the
[DWEN admission report](debugwire-admission-20261024.md); its full Node suite
passed1208/1208. Probe/decoder additions introduce no subsequent production
runtime changes.

Hardware GPR retention must first be qualified with the actual device's NOP
control, supply, clock and reset conditions. Old SP/SREG are reset I/O state
and are not observed here. Unchanged SRAM cannot reveal RET/RETI's individual
internal read latches. Marker and reset receiver propagation, instrument skew,
input synchronization and SRAM/GPR retention need physical controls and stated
tolerance. Default phases, hardware qualification and complete phase coverage
remain open; `expectedSiliconTrace` stays null. The main checklist remains
21/30 complete with nine open items.

Reproduction:

```text
node web-player/scripts/verify-cpu-phase-probe.mjs
node web-player/scripts/verify-hardware-probes.mjs --python PYTHON_EXECUTABLE
python web-player/native/peripherals/hardware-probe-test.py
python web-player/native/peripherals/timer0-top-zero-probe-test.py
```

Use `--avr-bin`/`--python` for explicit prepared toolchains and `--out` for an
alternate ignored build directory. No external programmer interface is added.
