# Huffman and simple prefix/Rice coding on the actual 600/608-byte streams

Lossless compression was measured on both complete Vinni streams after the
COREOPT/DATAOPT cycles. The baseline images are actually assembled and
three-engine verified; the entropy containers and their readers are PC
experiments. An AVR entropy reader has **not** been written or measured.

Both streams contain 132 frames and 288 raw header bytes. Cycle 01 has 312
coefficient bytes, cycle 02 has 320. All 64 EEPROM bytes contain the current
pulsebook, so an entropy table must use Flash. [report.json](report.json)
retains source/build hashes, every packed size and independent roundtrip.

## Actual packed bytes, including tables

| Coding | Complete PC container, cycle 01 / 02 | Headerless fixed-firmware data lower bound, 01 / 02 |
| --- | ---: | ---: |
| Original speech data | 600 / 608 | 600 / 608 |
| Dense byte canonical Huffman | 654 / 662 | 647 / 655 |
| Whole-stream nibble canonical Huffman | 578 / 586 | 571 / 579 |
| Whole-stream nibble preorder tree | 602 / 610 | 594 / 602 |
| Raw headers + coefficient canonical Huffman | **562 / 569** | **547 / 554** |
| Raw headers + coefficient preorder tree | 582 / 589 | 566 / 573 |
| Best tested fixed prefix, split top-4 | 597 / 604 | 581 / 588 |
| Best tested ranked Rice, split k=1 | 569 / 576 | 553 / 560 |

Dense byte Huffman has 172 used symbols: its payload is 519/527 bytes, but the
128-byte packed length table outweighs that saving. The sparse pair table is
worse, yielding 872/880-byte complete containers; both are measured rather than
rejecting byte Huffman solely on the sparse representation.

The best measured deployable-data lower bound is:

- Cycle 01: 288 raw header bytes + 2007 coded bits (251 packed bytes) + eight
  length-table bytes = **547 bytes**, saving **53 bytes**.
- Cycle 02: 288 + 2058 coded bits (258 packed bytes) + eight table bytes =
  **554 bytes**, saving **54 bytes**.

The universal `HQY1`/`HQE1` framing is not charged in those lower bounds.
Counts/modes/pointers can be compiled into a fixed firmware, but their actual
instruction/constant costs and EOF handling are not assumed free. Complete PC
containers save only 38/39 bytes; those smaller figures are not used as the
fixed-firmware break-even budget.

## The decompressor must fit too

The whole incremental reader/constants budget must be below **53/54 bytes**
for a positive Flash gain before alignment; that is the measured-data
break-even threshold. Under the explicitly provisional **70-byte** reader
estimate, the best headerless representation instead grows total memory by
**17/16 bytes**. This is arithmetic on measured data plus an estimate, not
actual AVR assembly, and does not prove that every possible smaller reader
is impossible.

A simple Flash preorder-tree decoder has a different table cost: 27 bytes for
the actual 14 coefficient symbols, rather than the eight-byte canonical length
table. Even with no universal header its split data is 566/573 bytes, saving
only 34/35 bytes before code. Canonical decoding can save table bytes but needs
its own logic or table construction; those costs have not been established.

The baseline cycle-01 firmware uses 392 code bytes, 600 speech bytes, EOF and
one padding byte: 994 Flash plus 64 EEPROM. Cycle 02 uses 414 code bytes,
608 speech bytes, EOF and one padding byte: 1024 Flash plus 64 EEPROM.
These are actual old-image measurements; no corresponding exact full-Flash
number is claimed for a nonexistent entropy firmware.

## Timing and conclusion

The verified baseline minimum margins are 330/299 cycles. Whole-stream nibble
Huffman would traverse up to 57 coded bits in a frame, while coefficient-only
Huffman reaches 32 bits (maximum code depth 9). Bit counts are measured; the
new reader's AVR cycles, SRAM, initialization, pointer setup and parsing costs
are unmeasured. Combining independent maxima is not proof of an overrun.

Five focused tests pass, and all **40 actual containers** independently restore
the original byte streams exactly. No speech samples or codec parameters are
changed. Packed experiment binaries remain in ignored `build/hq4-stream-entropy/`;
only source and this research report are committed.

None of the measured representations saves roughly 100 bytes of data, and
none leaves a substantial verified budget for its reader. An AVR port is
therefore not justified by this measurement. The best candidate for a future
deliberately small decoder would be the split canonical coefficient code,
with a strict incremental-code target below 53/54 bytes and actual complete
image/timing verification. Current firmware remains unchanged.
