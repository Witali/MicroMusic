# Micronucleus EEPROM reads through an existing CRC copier

Measured in the standalone MicroNucleus ATtiny88 loader at source commit
`5f6c58b` on October 26, 2026. Target: ATtiny88 / AVR25, external 16 MHz
clock, no hardware MUL. Build: Clang 18.1.3, `-target avr -mmcu=attiny88`,
assembler with C preprocessing, GNU AVR linker 2.26, and the pinned Microchip
ATtiny DFP 3.4.278 headers. This is a private assembly register convention,
not a GNU C-callable function. No MicroMusic runtime or backend is changed.

## Reuse the byte stream instead of buffering it

The loader already copies SRAM or Flash bytes into an eight-byte USB reply
while computing CRC. Add EEPROM as a third source and retain the existing
packet split, message pointer, CRC recurrence and remaining-length logic.
This permits one 1-to-64-byte control transfer without another EEPROM data
buffer. The wire still carries DATA packets of at most eight bytes.

Validate the complete address and length before reading, reject high address
or length bytes, and check EEPE. The source pointer's high byte is then zero
and its low byte stays within 0..64. Each nonempty iteration reads 0..63:

```asm
; Excerpt from the GPL-2.0-or-later MicroNucleus source cited above.
; Y is the context base, Z is a validated EEPROM cursor, r18 is the byte.
out     _SFR_IO_ADDR(EEARL), r30
sbi     _SFR_IO_ADDR(EECR), EERE
in      r18, _SFR_IO_ADDR(EEDR)
inc     r30
rjmp    usb_tx_store_payload_byte
```

`INC ZL` matters here: the inverted CRC loop needs carry set before mixing
each byte. `ADIW Z,1` would change carry and corrupt the checksum. The
validated range makes a low-byte-only increment sufficient. This is not a
general replacement for 16-bit pointer arithmetic. A zero-length reply
never enters the helper; reaching cursor 64 does not read EEPROM address 64.

The equivalent byte-stream structure is ordinary C; hardware access and
CRC implementation remain separate:

```c
for (uint8_t left = count; left != 0; --left) {
    uint8_t byte = read_eeprom(address++);
    write_payload(byte);
    crc = update_crc(crc, byte);
}
```

A reusable MicroMusic backend derived from this example must keep an
explicitly selectable C implementation and architecture plus ASM-enable
selection. The measured loader itself is an existing standalone ASM program.

## Exploit proven state and the actual caller count

Every new SETUP clears the source flag register `r2`. EEPROM selection can
use `DEC r2`, producing `0xff`, instead of loading an immediate through an
upper register and moving it into `r2`. The copier tests EEPROM bit 1 before
SRAM bit 0, so the other set bits have no effect. This saves two code bytes;
it requires the dominating clear and the ordered bit tests.

After reads acquire a complete-range guard, only EEPROM WRITE calls the old
single-address checker. Inline that sole call and remove its `RCALL/RET`
pair, saving four bytes. Do not inline a multiply-used helper on this evidence.

## Keep ACK bookkeeping outside bit timing

Native multi-packet replies must retain a packet until ACK. Repeated IN after
a lost ACK repeats the same DATA PID and payload. The loader replaces a
two-cycle `STD` that prematurely marked TX idle with a two-cycle `STD` to a
sent flag. A separate helper recognizes a one-byte ACK before releasing TX;
SETUP clears the flag. This adds one SRAM byte and 24 code bytes over the
read draft, including its SETUP flag clear.

The sampler and transmitter keep their instruction timing. The helper makes
the unsupported-packet discard path longer; it is not a new timed response.
This does not establish physical USB compliance or justify moving foreground
CRC into a timing-critical receive path.

## Linked measurements and validation

| LED-off stage | Linked code | Boot address | Application bytes |
| --- | ---: | --- | ---: |
| Stable baseline | 1262 B | `0x1B00` | 6908 |
| Native read draft before ACK tracking | 1294 B | `0x1AC0` | 6844 |
| Native read intermediate with ACK bookkeeping | 1318 B | `0x1AC0` | 6844 |

The 1318-byte result is a measured intermediate. Independent review found
that the current tests inject ACKs at a decoder entry and do not establish
that the polling loop acquires a real host ACK after transmitting DATA.
Foreground resynchronization may discard a late ACK. A bounded ACK wait and
a wire/event-level test are being added; their resulting size is not yet
recorded here. The arithmetic, linked-size and listed test counts remain
valid, but this intermediate is not a qualified complete USB receiver.

The 56-byte total increase includes four bytes from the changed Flash-boundary
encoding. It is not a 56-byte isolated cost for the source helper. The final
active-high and active-low LED profiles use 1336 and 1334 bytes. All reserve
1344 Flash bytes; crossing the former 1280-byte reservation costs one page.
EEPROM writes remain one byte. Native block OUT writes are not measured here.

The linked-code checks cover 10,400 EEPROM payload/CRC cases; 4,194,304 EEPROM
and 4,194,304 Flash address/length checks; 9,196 Flash/SRAM CRC vectors; 20 host
tests; and 3,072 standard-request comparisons per tested LED profile. IN
retries, malformed and unsolicited ACKs, memory guards, legacy Flash
write/read/erase, startup and postscript behavior are exercised. The timing
model compares 600 TX traces, 500 RX sync contexts, DATA/IN turnaround, reset
polling and pending-edge latency; opcode mutation checks constrain the
intentional changes. These are software measurements, without board testing
or a new physical throughput claim.

Reproduce in MicroNucleus `experimental/attiny88/updater` with
`build_optimized.py`, `test_native_reads.mjs`, `test_flash_read_bounds.mjs`,
`test_optimized_crc.mjs`, `test_optimized.mjs`,
`test_optimized_usb.py` and `test_optimized_timing.py`. Host fixtures are
`experimental/attiny88/tests/test_native_read_host.py` and `test_host.py`.
Register definitions and the excerpt's provenance remain in MicroNucleus
`experimental/attiny88/variants/strict_usb_optimized/micronucleus_t88_optimized.S`.

The original MicroNucleus contributors and modifications retain
GPL-2.0-or-later licensing. No third-party implementation is imported into a
MicroMusic runtime by this documentation entry. See the
[ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf)
for EEPROM sequencing, and
[Microchip AVR4027](https://ww1.microchip.com/downloads/en/AppNotes/doc8453.pdf)
and [AVR035](https://www.microchip.com/content/dam/mchp/documents/OTH/ApplicationNotes/ApplicationNotes/doc1497.pdf)
for the broader advice to use bounded data types, direct I/O and measured
code sharing. The cookbook's [control-size recipe](um88-control-size.md)
likewise treats shared work and caller-count changes as measurements.