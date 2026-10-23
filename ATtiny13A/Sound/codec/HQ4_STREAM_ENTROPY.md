# Lossless coding of the actual small HQ4 streams

`tools/probe-hq4-stream-entropy.py` measures complete PC containers and a
separate optimistic fixed-firmware data layout. It does not implement an AVR
reader, assemble a new firmware or claim its timing. Original HQ4 byte streams
are restored exactly before any speech decoding; no quantization changes.

The methods are byte Huffman (sparse or dense canonical lengths), 16-symbol
canonical Huffman, a compact preorder nibble tree, top-1/2/4 fixed prefixes and
frequency-ranked Rice parameters 0 through 3. They are tested both on the whole
stream and, for nibble methods, on coefficient bytes alone while retaining the
frame headers verbatim. The HQ4 grammar separates headers and coefficient
updates losslessly, including extended pitch and full/half/reused updates.

## Measured formats

`HQE1` has a seven-byte magic/method/uncompressed-size header. The codebooks are:

| Method | Actual stored codebook |
| --- | --- |
| Sparse byte canonical | Two-byte count, then symbol/length pairs |
| Dense byte canonical | 128 bytes: all 256 lengths packed in nibbles; max length 15 |
| Nibble canonical | Eight bytes: all 16 lengths packed in nibbles |
| Nibble preorder tree | One-byte node count plus 2L-1 nodes for L used symbols |
| Top-K prefix | One-byte log2(K) plus ceil(K/2) bytes of frequent symbols |
| Ranked Rice | One-byte parameter plus eight-byte symbol-rank permutation |

The compact tree uses one byte per node: an internal node's right-child offset
(left child is adjacent), or a leaf flag and four-bit symbol. Sixteen used
symbols require 31 tree bytes; the actual coefficient alphabet has 14 symbols
and requires 27. Those bytes occupy Flash because all 64 EEPROM bytes already
hold the current pulsebook. A canonical eight-byte length table does not
provide a free 27/31-byte traversal tree or free startup construction.

`HQY1` adds eight bytes of framing before raw headers and the nested coefficient
container. Low nibbles precede high nibbles. Bit payloads are MSB first and
zero padded. Independent decoders check termination/padding and reproduce exact
source bytes. Five tests cover every method, all 256 byte values, empty and
single-symbol inputs, compact trees, corruption/truncation, and grammar splits.

## Fixed-firmware lower bound and code costs

The report explicitly removes universal magic, size/mode fields, known tree
node counts, known Rice parameters and other compile-time framing. It retains
the packed payload, coding table and verbatim HQ4 headers. This is an
**optimistic data lower bound**, not an assembled layout: pointer initialization,
termination/EOF, counter state and decoding logic must still exist somewhere.

`incremental_reader_break_even_bytes` is raw data bytes minus that lower bound.
For a positive Flash gain the complete incremental reader/constants budget
must be smaller than this number; equality merely breaks even before alignment.
The report separately applies an explicitly estimated 70-byte incremental
reader. No exact total Flash figure is assigned to unwritten code. Register,
SRAM and initialization costs have not been established.

The actual baseline timing margins are copied from the existing three-engine
reports. Measured coded bits per frame describe work the new reader would
perform, not AVR cycles. Maximum Huffman depth, variable traversals, extra LPM
loads and frame parsing all need an instruction trace before a timing claim.
No new reader is ported when the measured savings do not justify that work.

```text
python tools/test-hq4-stream-entropy.py
python tools/probe-hq4-stream-entropy.py --stream cycle-01=build/q3-core-data-cycles/vinni/cycle-01/after/speech.hq --stream cycle-02=build/q3-core-data-cycles/vinni/cycle-02/after/speech.hq --output build/hq4-stream-entropy --retain ATtiny13A/Sound/research/hq4-stream-entropy
```

The probe writes packed experimental containers under ignored `build/` and
retains only a JSON report when requested. It verifies that each source stream
matches its actual baseline build hash. See the measured
[study](../research/hq4-stream-entropy/README.md) before considering a port.
