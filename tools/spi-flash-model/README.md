# Portable read-only W25Q128 host model

This C adapter ports the read-only command/state behavior of the
[pinned QEMU model](../../third_party/qemu-m25p80/README.md). It preserves the
original source notice and uses GPL-2.0-or-later. The original QEMU files stay
verbatim in `third_party/qemu-m25p80/upstream/`; project changes are separate.
It is a limited extracted protocol port, rather than the complete QEMU device
or a shim that executes the original QOM/SSI implementation.

The host API is declared in [w25q128_readonly.h](w25q128_readonly.h):

```c
LpxW25q128 flash;
if (!lpx_w25q128_init(&flash, image, LPX_W25Q128_IMAGE_BYTES)) {
    /* Reject an invalid image. The caller owns its exact 16 MiB allocation. */
}
lpx_w25q128_select(&flash, false); /* Electrical CS low: selected. */
lpx_w25q128_transfer8(&flash, 0x0b);
lpx_w25q128_transfer8(&flash, 0x12);
lpx_w25q128_transfer8(&flash, 0x34);
lpx_w25q128_transfer8(&flash, 0x56);
lpx_w25q128_transfer8(&flash, 0); /* Exactly eight dummy clocks. */
uint8_t value = lpx_w25q128_transfer8(&flash, 0xff);
lpx_w25q128_select(&flash, true);
```

The image must outlive the device. The adapter never modifies it. Device struct
fields are implementation state; consumers obtain bytes through `transfer8`,
not by inspecting the backing pointer. C++ callers use the same `extern "C"`
API. Failed initialization leaves the device safely unbound. Initial CS is high;
unbound or deselected transfers return pulled-up `ff` and do not parse commands.
Repeated CS levels are inert. CS rising discards partial commands, addresses,
dummy phases and ongoing reads while retaining volatile write/reset latches.

| Command | Implemented behavior |
| --- | --- |
| `03` READ | Three MSB-first address bytes, then one payload byte per transfer. |
| `0b` FAST_READ | Three address bytes, exactly one dummy byte, then payload. |
| `9f` JEDEC ID | `ef 40 18 00 00 00`, then command state, matching pinned QEMU. |
| `05` status | Repeats WEL in bit 1; WIP remains zero in this read-only model. |
| `35` status 2 | Repeats zero; quad mode is not enabled or implemented. |
| `15` configuration | One zero byte, then command state, matching pinned QEMU. |
| `06` / `04` | Set/clear the volatile write-enable latch without modifying data. |
| `66` / `99` | Enable/reset sequence; any intervening command cancels enable. |

Command, address and dummy transfers return zero, as in QEMU. Dummy values and
MOSI payload-read values cannot become commands. Addresses wrap at 24 bits,
including sequential reads past the final physical byte. Reset clears protocol
and volatile latches while preserving the external CS level, backing image and
diagnostic counters. The six-byte ID response and same-CS command-state behavior
are properties of this pinned model; no broader hardware equivalence is claimed.

Unknown commands, including programming, erase and status writes, return zero
until CS rises, leave storage unchanged, and increment `unsupported_commands`.
They do not simulate modifying-command WEL consumption or busy timing. A supported
audio campaign must require that counter to stay zero. SFDP, writes, erase,
dual/quad I/O, four-byte addressing, power modes and electrical timing are outside
this adapter. The original full model remains available as licensed source.

`lpx_w25q128_get_stats` returns counts of actual transfer calls, selected bytes,
command/address/dummy/data bytes, CS edges, resets and unsupported commands.
It provides no direct payload accessor. `transfer8` represents one completed
eight-clock single-wire transfer; it advances no simulated time. The MCU bridge
must schedule actual SPI completion and account for its divider, CS changes,
software gaps, interrupts and buffer underruns. The flash's maximum advertised
rate does not set the MCU clock. This module alone proves no AVR timing or
complete-player Flash/SRAM/IRQ support.

Run the source-integrity and protocol contracts with host C/C++ compilers:

```text
python tools/spi-flash-model/run_tests.py --cc gcc --cxx g++
```

The runner compiles the adapter as strict C11 with a C++11 caller and separately
as C++11 (`-O2 -Wall -Wextra -Werror -pedantic`). Both builds pass 13 contracts:
exact image bounds, deselected behavior, READ/FAST_READ phases, dummy accounting,
wrap, CS abort/idempotence, JEDEC/status, reset, read-only rejection and a 131073-byte
payload crossing pages and 64 KiB. It also verifies all four vendored source and
license hashes plus the exact preserved notice in the adaptation. No private
audio image, source identity or media fingerprint is needed for these tests.
