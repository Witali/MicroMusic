# Full-length external SPI player

The [finite protocol](PROTOCOL.md) fixes 12 full long ASM SPI rows, eight bounded
C/ASM SPI rows and eight matched short ROM controls. The complete stream data
stays in external 16 MiB images; actual linked program Flash includes the reader,
callback, code and segment metadata. No long-ROM linked cost is invented.

The shared reader is a separate reusable component under
`Codecs/shared/avr-spi-flash/`. The optional firmware example is `AVR_V5_SPI_PLAYER`.
The isolated host bridge uses the audited QEMU-derived read subset and a
source-pinned simavr1.6 timing correction; installed libraries and old observers
are unchanged. Its eight-divisor and GPIO/seek unit gates passed.

Preparation has materialized all eight exact cases and native ROM/callback
PCM/PWM references. The 28-row target-image phase has not started yet. All stored
tails are retained, while callback-requested byte counts are independently
recorded. Native references and helper work do not establish AVR timing support.

`reproduction/run_player.py` binds immutable case/toolchain/observer/source
receipts, runs the 16 bounded rows first, permits four isolated long modulo-4
shards only after those pass, and performs a read-only exact artifact aggregate.
No fitting, new quality selection, physical-board claim, sustainable C 8 kHz
claim or subjective adoption is part of this validation.
