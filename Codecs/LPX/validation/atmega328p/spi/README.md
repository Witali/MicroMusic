# Clocked SPI Flash observer

The host observer retains the standalone ROM observer's ELF, physical PWM,
timer, queue, EOF and stack checks and adds a byte-level read-only Flash bridge.
All MCU registers and pins come from a separately compiled vendor-header object;
that object is never linked into firmware. The chip model has no time shortcut:
it supplies MISO only when a scheduled emulated SPI byte completes.

`patch_simavr_spi.py` accepts exactly the upstream source pinned in
`PROVENANCE.json`. It generates a separate corrected module under ignored build
storage. The packaged library internally binds its own initializer, so loading
an executable symbol with the same name is insufficient. The explicit installer
replaces only the matching existing SPDR write callback. It preserves module
lists, IRQs and input/read handlers and never modifies the installed library.

`build_spi_observer.py` first executes all eight divisor cases and 48 completed
protocol bytes, then checks real vendor metadata, GPIO CS transitions, repeated
dummy/data bytes and two explicit seeks. The second host unit completes 13
bytes. Both gates passed before any player image. Source, compiler, header,
library, binary and test receipts stay in private build storage.

The shortest byte uses 16 CPU cycles at 16 MHz, selecting F_CPU/2 = 8 MHz SCK.
The actual observer records instruction-boundary lateness and software/IRQ gaps
separately. Its fixed four-cycle dispatch bound follows the pinned no-sleep raw
core path; the player rejects sleep. Pinned simavr1.6 does not charge IRQ-entry
cycles in interrupt service/_avr_push_addr. This limitation remains; +100-cycle
ISR stress measures margin and does not repair general simulator timing.

The 64-bit run bound covers complete long audio. Private progress logs contain
only played/expected samples and CPU cycles every 640,000 played samples. The
caller additionally requires zero underruns, exact output, final decoder/queue/
EOF state and exact per-reset command/address/dummy/CS counts. Payload counts
reflect actual requested bytes, including stored headers; unread valid packet
tails are preserved in the image and never forced through the bus.

Build using explicit `--include`, `--lib`, `--upstream`, `--avr-bin`, fresh
`--output` and optional `--wsl` arguments. Fetch the pinned upstream file from
the URL in `PROVENANCE.json` and verify its hash; the builder performs no network
access. Only the SPI observer links the corrected module and chip model. The
matched ROM controls use the unchanged independent ROM observer.

See the [finite 28-row protocol](../../../research/v5-external-spi-player-2026-11-01/PROTOCOL.md)
and [shared codec-independent reader](../../../../shared/avr-spi-flash/README.md).
The host harness uses GPL-3.0-or-later simavr code; its license is retained in
`COPYING.simavr`. QEMU-derived model provenance and licenses remain in
`third_party/qemu-m25p80/` and `tools/spi-flash-model/` at repository root.
