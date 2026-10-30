# Pinned QEMU SPI NOR source

The files in `upstream/` are byte-for-byte copies of committed Git blobs from
QEMU checkout commit `9135fc89ce3eba7bbb1c2dbed103cd2854436940`:

- `hw/block/m25p80.c`
- `hw/block/m25p80_sfdp.c`
- `hw/block/m25p80_sfdp.h`
- `COPYING`

The observed checkout differed from those blobs only by CRLF line endings.
[PROVENANCE.json](PROVENANCE.json) records committed and observed source sizes
and SHA-256 values. The vendored files retain the committed LF bytes, original
whitespace, complete copyright notices, and license text. They are GPL version 2
or later as specified by their individual notices. The public project reference
is [QEMU](https://www.qemu.org/), with
[upstream flash sources](https://gitlab.com/qemu-project/qemu/-/tree/master/hw/block).
The local commit is the source identifier; its availability at public upstream
is not asserted. No private checkout location or remote URL is recorded here.

These files are provenance, rather than a standalone build of QEMU. The complete
model depends on QOM, SSI, block backends, migration, timers, tracing and QEMU
configuration. Project adaptations live separately in
[the portable host adapter](../../tools/spi-flash-model/README.md). That adapter
is an explicitly limited read-only protocol port. SFDP is preserved here but
is not implemented or used by the adapter.

The pinned model's `w25q128` entry uses JEDEC `ef 40 18` and 256 sectors of
64 KiB, totaling 16 MiB. Its `byte-dummy-cycles=true` mode consumes one dummy
byte for single-wire FAST_READ `0b`; the legacy false mode counts eight dummy
transfer tokens. A byte-oriented AVR bridge needs the former behavior.
