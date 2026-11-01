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

All 28 target configurations passed, including six complete long chains at both
IRQ loads: 45,433,332 long physical PWM samples and zero underruns. Long linked
Flash is 5,308 / 5,316 B, including 360 B of segment metadata; static SRAM is
764 B. Matched short controls measure a program cost of +381 B for ASM and
+383 B for C. See [results and limitations](RESULTS.md), [costs](cost-summary.json)
and the [strict artifact check](artifact-check.json).

All stored tails are retained; independently measured callback requests may
stop before those tails. Native references and bounded C parity do not establish
sustainable AVR C playback. No physical-board timing claim follows.

`reproduction/run_player.py` binds immutable case/toolchain/observer/source
receipts, runs the 16 bounded rows first, permits four isolated long modulo-4
shards only after those pass, and performs a read-only exact artifact aggregate.
The original bounded worker completed its 16 physical checks before a JSON
tuple/list postprocessing failure. A separately bound read-only admission
reopened those saved proofs; no image was repeated. The final aggregate/export
reopened all 28 proofs. [Source receipts](reproduction/sources.json) distinguish
the executed source, admission, and later fresh-reproduction repair.

No fitting, new quality selection or subjective adoption is part of this
validation.
