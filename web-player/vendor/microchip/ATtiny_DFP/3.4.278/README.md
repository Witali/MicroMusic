# Pinned Microchip ATtiny13A device definitions

Source: [Microchip.ATtiny_DFP.3.4.278.atpack](https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack),
from the [official Microchip Packs Repository](https://packs.download.microchip.com/).
The downloaded archive is 33,433,639 bytes, SHA-256
`41f09d5825abaa764c9000f4488f8ba3fab152afe6229b359de4a5efe9a21eda`.
Only the following four package members are retained, byte for byte, with their
original paths and line endings:

- `include/avr/iotn13a.h`: manufacturer C register/bit/vector definitions.
- `avrasm/inc/tn13Adef.inc`: manufacturer assembler definitions, including common
  CPU `SPL`/`SREG` I/O offsets absent from the device-specific C header.
- `atdf/ATtiny13A.atdf`: manufacturer data-space addresses, CPU flags, geometry,
  fuse masks and vector metadata.
- `LICENSE.txt`: original package license notice.

`iotn13a.h` carries its own complete BSD-style three-clause license notice, kept
inside the unmodified file. The package license notice identifies Apache-2.0 for
package material such as ATDF/assembler definitions; it does not replace the C
header's own notice. A full Apache-2.0 license copy is additionally retained as
`LICENSE.Apache-2.0.txt`, downloaded from
[Apache's license text](https://www.apache.org/licenses/LICENSE-2.0.txt), not
extracted from the device pack. `provenance.json` distinguishes that additional
file and pins all five source/license byte hashes. This README and provenance
are project-maintained additions.

## Project adaptation

`native/attiny13a-registers.h` includes the original C header using numeric
`_SFR_IO8`/`_SFR_IO16` definitions. It materializes `AT13_*` enums, then undefines
the vendor's generic macros and temporary SFR helpers. This avoids AVR target
pointer/lvalue access on a host or WASM CPU. Do not combine it with `<avr/io.h>`.
No manufacturer file is patched.

`scripts/generate-attiny13a-registers.mjs` produces:

- `native/attiny13a-registers.generated.h`, included only through that adapter.
- `lib/attiny13a-registers.js`, frozen prefixed maps for tests/generators/JS.
- `lib/attiny13a-registers.json`, the same maps for Python/other tools under
  schema `micromusic-attiny13a-register-map-v1`, in its `maps` object.
- `native/attiny13a-registers.generated.inc`, simple `.set NAME,numeric` lines
  for the project's assembler: original I/O, bit-position and memory names plus
  `*_vect_num`. The manufacturer AVRASM file remains untouched.

Run from the repository root:

```powershell
node web-player/scripts/generate-attiny13a-registers.mjs
node web-player/scripts/generate-attiny13a-registers.mjs --check
node --test web-player/tests/attiny13a-registers.test.mjs
```

The generator checks original byte hashes, C/ATDF register offsets and C/ATDF
vector indices. It derives the I/O-to-data-space offset from all matching C and
ATDF registers. `SPL` and `SREG` data addresses come from ATDF and their I/O
addresses are independently checked against the assembler include. C compile-time
checks compare memory/default-fuse constants against ATDF. Tests compile the
original header through the adapter and compare every generated JS value against
the C enum, including aliases, widths, CPU flags and fuse masks.

| C names | JavaScript map | Meaning |
| --- | --- | --- |
| `AT13_IO_OCR0A` | `AT13_IO.OCR0A` | AVR I/O offset (`0x36`) |
| `AT13_DATA_OCR0A` | `AT13_DATA.OCR0A` | Data-space address (`0x56`) |
| `AT13_WIDTH_ADC` | `AT13_WIDTH.ADC` | Register width in bytes (`2`) |
| `AT13_BIT_ADEN` | `AT13_BIT.ADEN` | Bit position (`7`) |
| `AT13_MASK_ADEN` | `AT13_MASK.ADEN` | Set-bit mask (`0x80`) |
| `AT13_MASK_SREG_I` | `AT13_MASK.SREG_I` | CPU flag mask from ATDF |
| `AT13_VECTOR_ADC` | `AT13_VECTOR.ADC` | Vector index/word address (`9`) |
| `AT13_FLASH_BYTES` | `AT13_CONST.FLASH_BYTES` | Device geometry (`1024`) |
| `AT13_MEMORY_RAMSTART` | `AT13_MEMORY.RAMSTART` | Original memory macro name (`0x60`) |
| `AT13_FUSE_LOW_CKDIV8_MASK` | `AT13_FUSE_MASK.LOW_CKDIV8` | Fuse bit mask (`0x10`) |

Fuse masks here identify physical fuse bits; programming clears those bits. They
are not the C header's complemented `FUSE_*` programming values. ADC/ADCW and
ADCL/ADCH register aliases remain separate metadata entries; these definitions do
not implement ADC locking, bus strobes, reserved-bit behavior or instruction
semantics. The datasheet/errata remain the authority for behavior. Manufacturer
ATDF field captions/masks can differ in granularity from the C bit names; the
generator uses C bit names for device registers and ATDF for common CPU/fuse
metadata rather than silently inventing missing C definitions.

`AT13_MEMORY` retains `RAMSTART`, `RAMSIZE`, `RAMEND`, `FLASHEND`, `SPM_PAGESIZE`,
`E2END` and `E2PAGESIZE` names. The C adapter evaluates the original C macros,
with compile-time checks against geometry extracted from ATDF. The `.inc` uses
these original names directly, for example `.set OCR0A,0x36` and
`.set RAMSTART,0x60`; these are I/O offsets, not the `+0x20` data addresses.

`build-device-wasm.mjs` runs the generator's `--check`, includes the vendor tree
recursively in normalized source hashes, and records additional exact-byte vendor
hashes and package identity in its manifest. `.gitattributes` disables text
conversion for this pinned tree. To upgrade, extract a new version to a separate
versioned directory, verify its URL/archive/member hashes and licenses, then
review regenerated mappings and behavioral differences. Do not edit a pinned
manufacturer file to change emulation behavior.
