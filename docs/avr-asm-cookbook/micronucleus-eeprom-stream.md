# Micronucleus EEPROM reads through an existing CRC copier

Measured in the standalone MicroNucleus ATtiny88 loader at source commit
`e37c3f7` on October 26, 2026. Target: ATtiny88 / AVR25, external 16 MHz
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

## Share bounded guards and a callable copier

EEPROM and Flash read entry points select different limits and reuse one
full 16-bit address guard. Subtract a validated length from the limit, then
compare the full start address with that maximum start. The low bytes of
both limits are at least 64, so subtracting a count of at most 64 cannot
borrow into the high byte. EEPROM uses limit 64; the Flash layout has a
compile-time assertion for this condition. A new layout with a smaller low
byte needs a different guard, not the same shortcut. Combined with a shorter
branch, this sharing saved 20 bytes relative to the 1318-byte intermediate.

Extracting the entire existing copier/CRC into one callable routine cost
four code bytes and seven foreground cycles per packet. It selects Flash,
SRAM or EEPROM, preserves the live message remainder, and can validate
received CRC through an in-place SRAM copy. YH=1 and r1=0 remain required.
Sharing a complete operation avoids a second CRC body; call overhead and
total preparation time must still be measured.

## General CRC count with a shifting bit mask

The earlier copier packed the byte count in five low bits and the bit phase
in three high bits, limiting a call to 0..31 bytes. The current version keeps
the full byte count
in r23 and uses a separate all-ones mask for the eight bit iterations:

```asm
ldi     r20, 0xff           ; once per byte, preserving initial C=1
; mix the byte, then execute the unchanged inverted-CRC bit body
; ...
lsr     r20
brne    usb_crc16_shift_bit
```

Eight shifts turn 0xff into zero. Every shift exports C=1, supplying the
next inverted-CRC bit's carry input; BRNE preserves that carry. The first
bit still receives carry from the nonempty-byte test. Do not insert a
carry-changing instruction on either path. The byte counter now supports
all counts 0..255, for two extra code bytes. This does not relax the
EEPROM or Flash range checks. The mask initializer also adds an instruction
per byte; an earlier preparation-time bound cannot simply be reused.

Arithmetic C reference for one byte, with CRC stored in complemented form:

```c
static uint16_t inverted_crc_byte(uint16_t crc, uint8_t byte) {
    crc ^= byte;
    uint8_t mask = 0xff;
    do {
        uint8_t low = (uint8_t)(crc & 1u);
        crc = (uint16_t)((crc >> 1) | 0x8000u);
        if (!low)
            crc ^= 0xa001u;
        mask >>= 1;
    } while (mask != 0);
    return crc;
}
```

Initialize the complemented accumulator to zero. Independent checks cover
every whole-call length 0..255 under five patterns, alongside the outgoing
USB packet CRC vectors. This is an arithmetic reference, not a new
MicroMusic backend.

## Reuse protocol state and keep the ACK wait after bit timing

Native multi-packet replies must retain a packet until ACK. In the current
version the existing CTX_CURRENT_TOKEN also records IN ACK expectation.
This removes the separate sent flag, saving four code bytes and one SRAM
byte relative to the corrected 1310-byte version. A new SETUP token cancels
the expectation in the PHY, before foreground dispatch. A malformed ACK
clears the expectation, so another ACK is accepted only after a fresh IN.

Bookkeeping alone did not establish ACK acquisition. In the superseded
1318-byte intermediate, foreground resynchronization could discard a real
host ACK after DATA, although decoder-entry injection tests passed. The
corrected path waits for the host edge immediately after the final bus
release. It reuses the bounded wait-for-data loop and the proved
post-transmit Y invariant: zero after a handshake, low-byte bit 7 set after
DATA. This avoids another mode flag and originally cost eight code bytes.

The wait starts after all sampled/transmitted bit timestamps. The digital
test covers the complete DATA-to-ACK event path and fails on the first case
of the old intermediate. Unsupported-packet discard still takes a longer
path; it is not a new timed response. These model checks do not establish
electrical USB compliance.

## Linked measurements and validation

| LED-off stage | Linked code | Boot address | Application bytes |
| --- | ---: | --- | ---: |
| Stable baseline | 1262 B | `0x1B00` | 6908 |
| Native read draft before ACK tracking | 1294 B | `0x1AC0` | 6844 |
| Superseded intermediate with ACK bookkeeping | 1318 B | `0x1AC0` | 6844 |
| Shared guards, callable copier and bounded ACK acquisition | 1310 B | `0x1AC0` | 6844 |
| Current native reads with shared token and full-length CRC | 1308 B | `0x1AC0` | 6844 |

The current 46-byte increase over baseline includes four bytes from the
changed Flash-boundary encoding. Guard/branch sharing saved 20 bytes,
the callable copier cost four, and bounded ACK acquisition cost eight:
1318 became 1310. Token reuse then saved four bytes and the general CRC count
cost two, producing 1308. These combined linked results are not isolated
helper-size predictions. Current active-high and active-low LED profiles
use 1326 and 1324 bytes. All reserve 1344 Flash bytes, matching the user
ceiling; crossing the former 1280-byte reservation costs one page.
EEPROM writes remain one byte.

Separate noninstallable staging probes measure receive and checksum logic:

| Incoming validation policy | Linked bytes | Excess over 1344 |
| --- | ---: | ---: |
| SETUP and per-packet DATA CRC | 1520 | 176 |
| SETUP CRC only | 1518 | 174 |
| No incoming CRC checks | 1494 | 150 |
| SETUP CRC and expected whole-block CRC16 in wIndex | 1546 | 202 |

These probes restore r2=0 after SETUP CRC validation so legacy dispatch keeps
its default source. They have no native NVM write worker or whole-transfer
replay cache and produce no HEX. Only reception and checksum comparison in
the proposed receive, compare, write, readback and STATUS sequence are
modeled. Full block writes are not claimed to fit 1344 bytes. The sizes are
measured candidates, not a proof that smaller implementations are impossible.

The native-read checks cover 10,400 EEPROM payload/CRC cases; 4,194,304 EEPROM
and 4,194,304 Flash address/length checks; 9,196 outgoing Flash/SRAM CRC
vectors; 1,280 whole-call CRC cases (every length 0..255 under five patterns);
20 host tests; and 3,072 standard-request comparisons per tested LED profile.
IN retries, malformed and unsolicited ACKs, memory guards, legacy Flash
write/read/erase, startup and postscript behavior are exercised.

The digital event test passes 540 actual DATA-to-ACK waveforms: payload
lengths 0..8 and host gaps 21..80 clocks, plus next-IN behavior, absent/corrupt
ACK retention and ACK/NAK handshake return. The timing model also compares
600 TX bus-edge traces, 500 RX sync contexts, 15 PID/handshake cases, reset
polling and pending-edge latency. Opcode mutation checks constrain the
intentional changes. These are software measurements, without board testing
or a new physical throughput claim.

Reproduce in MicroNucleus `experimental/attiny88/updater` with
`build_optimized.py`, `test_native_reads.mjs`, `test_flash_read_bounds.mjs`,
`test_optimized_crc.mjs`, `test_shared_crc.mjs`, `test_optimized.mjs`,
`test_optimized_usb.py`, `test_optimized_timing.py` and `test_in_ack_wire.py`.
Host fixtures are
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

## Compact Pass27: verify operands, then retain proven state

The following measurements belong to a **separate compact Pass27 research
line**, derived from the October 27, 2026 Pass26 handoff. They do not extend
the 1308-byte native-read line above. They are local assembled/model-validated
experiments, not a published release, a 1024-byte result, or physical USB
validation. Target and tools: ATtiny88, classic enhanced AVR/AVR25, 16 MHz,
Clang/LLVM 18.1.3 with `-target avr -mmcu=attiny88`, preprocessed assembly,
GNU `avr-ld` 2.26, Python 3.12.3. These are private standalone-loader register
conventions; no MicroMusic assembly backend is added.

### Reject unresolved operands and inspect the actual branch bits

The handoff's reduced AVR header omitted `SREG_N` and `SREG_S`. The source
assembled and linked, and the final file had no `R_AVR_*` relocations, yet its
symbol table still contained those two undefined names. Three branches encoded
bit zero (C), rather than the intended N/N/S. Checking only relocation output
or comparing two descendants of the same defective header missed the problem.

Keep official device definitions pinned where available. Put any separately
required compatibility definitions in the project's adapter, and reject
undefined symbols in the final candidate ELF as well as unresolved relocations.
Then verify selected raw instruction operands against an independent contract.
Here N is SREG bit 2, S is bit 4; BRBC/BRBS encode the bit in the instruction's
low three bits. The mask `word & 0xfc07` checks both branch sense and flag,
without depending on a disassembler's preferred alias. See Microchip's
[SREG definition](https://onlinedocs.microchip.com/oxy/GUID-80B1922D-872B-40C8-A8A5-0CBE009FD908-en-US-3/GUID-CE0DCB6D-2266-4C24-8BE6-FEC114F6D6E3.html)
and [AVR Instruction Set Manual, DS40002198B](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-InstructionSet-Manual-DS40002198.pdf).

The standard-library Python example
[avr_elf_branch_audit.py](examples/avr_elf_branch_audit.py) reads linked AVR
ELF32 directly and checks the three observed sites:

```sh
python3 avr_elf_branch_audit.py candidate.elf \
  --branch usb_rx_decode_bit6+6:clear:N \
  --branch usb_rx_handle_data+14:set:N \
  --branch usb_rx_handle_in+4:clear:S
```

Offsets are **bytes** from the named symbols and must be refreshed when those
procedures change. The example also accepts numeric addresses. It requires an
unstripped symbol table and rejects all named undefined symbols, including weak
references, so use it for a fully resolved bare-metal candidate, not a deliberately
partially linked object.
It does not validate whole-program control flow, timing or protocol behavior.

### Replace an invariant address calculation with a cycle-matched setup

The single-buffer receiver clears context byte 14 at startup and never changes
it. RX writes context bytes 22..32, while the eight-byte TX payload plus CRC
occupies bytes 2..11. The old initializer therefore always produced Y=0x0116:

```asm
; GPL-2.0-or-later MicroNucleus excerpt; offset is proven zero.
push    r0                         ; 2 cycles, 2 bytes
lds     r28, input_buffer_offset   ; 2 cycles, 4 bytes
ldi     r29, 1                     ; 1 cycle,  2 bytes
adiw    r28, 22                    ; 2 cycles, 2 bytes
pop     r0                         ; 2 cycles, 2 bytes
```

Use two immediate loads and call an already present bare RET:

```asm
ldi     r28, 0x16                  ; 1 cycle, 2 bytes
ldi     r29, 0x01                  ; 1 cycle, 2 bytes
rcall   existing_bare_ret          ; 3 cycles, 2 bytes; RET takes 4 cycles
```

This measured substitution reduces **12 to 6 code bytes**, with **9 cycles**
in either sequence. The existing RET is not duplicated. The ATtiny88 call
temporarily pushes a two-byte return address instead of the former one-byte
PUSH, so peak stack increases by **one byte**. These instruction timings and
stack width follow the classic AVR core; do not transfer the figures to
AVRxt/AVRrc or three-byte-PC devices without remeasuring.

The incoming SREG differs because the removed ADIW updated arithmetic flags.
An emitted-word control-flow audit explored 66 states through successful and
failed SYNC paths and return into the caller: every affected flag is redefined
before it is consumed. All 60 other PHY branch targets normalize to the same
instructions. The call must land directly on `RET`, stay within RCALL range,
and use a valid, sufficiently sized stack. This loader runs with interrupts
disabled; observers of intermediate flags need a separate proof. A future
double buffer, DMA writer, ISR, or mutable context offset invalidates the
fixed-state assumption. Equal initializer delay does not prove that the
inherited bit period is correct or centered within USB tolerance. Audit actual
sampling/output timestamps against the protocol separately; electrical behavior
still needs hardware validation.

### Keep the reply cursor in a genuinely available register pair

The USB reply source pointer is live across packet preparation but its old
representation was a pair of SRAM context bytes. A private persistent pair
`r14:r15` is untouched by this receiver/transmitter and by the loader's other
long-lived state. Replace each paired memory operation with MOVW:

```asm
; Set the reply pointer: two stores become one instruction.
; Before: STD Y+MSG_POINTER_HIGH,r19; STD Y+MSG_POINTER_LOW,r18
movw    r14, r18

; Begin a packet: two loads become one instruction.
; Before: LDD r30,Y+MSG_POINTER_LOW; LDD r31,Y+MSG_POINTER_HIGH
movw    r30, r14

; Preserve the pointer advanced by the copier, for the following packet.
; Before: STD Y+MSG_POINTER_HIGH,r31; STD Y+MSG_POINTER_LOW,r30
movw    r14, r30
```

Each pair shrinks from four bytes to two, saving **six code bytes** in the
isolated linked experiment. This does not mean X/Y/Z can be globally reserved:
polling and reply staging use X, and the PHY clobbers Y/Z. Nor is `r14:r15`
generally free in a C-callable function.
Prove register liveness across every caller, helper, reset/abort path and
interrupt boundary; reserve or save the pair according to the actual ABI.
Persistent state also needs initialization before its first real use.

Related experiments share a two-byte standard-reply tail and keep DATA PID in
another proven-free persistent register (two bytes). The combined candidate
therefore saves ten bytes, not six: at `BOOT_AT=0x1C00`, 1182 becomes 1172.
The isolated cursor variant is 1176 bytes at that placement. These remain
over the 1024-byte target. Validation of the combined reply changes covers
13824 standard-dispatch comparisons, 675 actual-opcode payload/independent
USB CRC16/cursor cases, and 1110 DATA-PID reset/toggle cases across all three
LED profiles. These counts describe specific model workloads, not every USB
error/retry state or electrical compliance.

### Replace generic reply storage with validated descriptor bytes

The compact loader's fixed device descriptor already ends in the string-index
bytes `0, 0, 0` and the configuration count `1`. GET_STATUS and GET_INTERFACE
can read its bytes 14/15 instead of a permanent SRAM zero pair.
GET_CONFIGURATION can point to byte 16 or byte 17, provided every reachable
configuration is zero or one. Enforce that invariant at the complete 16-bit
SET_CONFIGURATION value, not only its low byte:

```asm
; GPL-2.0-or-later MicroNucleus excerpt, source commit 9b3918c.
; r18 = wValueLow; Y = context; r1 = 0. LDD preserves CPI's borrow.
cpi     r18, 2
ldd     r24, Y+CTX_SETUP_VALUE_HIGH
cpc     r24, r1
brsh    reject_without_changing_configuration
std     Y+CTX_CONFIGURATION, r18

; Bytes 16/17 share the descriptor's 256-byte Flash window.
ldd     r18, Y+CTX_CONFIGURATION
subi    r18, lo8(-(device_descriptor + 16))
ldi     r24, 1
; The common reply helper loads the known Flash high byte.
```

The `SUBI` adds a fixed low address without another LDI/ADD pair. The shared
high byte is valid only while these adjacent bytes remain in the same window.
The two valid prior states are established by RESET clearing and preserved by
every accepted setter; invalid values, including nonzero wValueHigh, preserve
the old state. Directly injecting CFG=255 into this representation is no
longer a valid-state fixture. Keep exhaustive malformed-request tests instead.

All remaining reply sources are Flash or EEPROM, so remove the unused SRAM
copy branch and its separate source flag. The persistent byte pointer
`r14:r15` can retain EEPROM in bit 15; the eight-byte READ keeps that tag rather
than moving it into r2 and clearing its high byte. The TX byte reader tests
`r15.7`, uses only ZL for EEARL, and advances the low byte. The host already
restricts valid EEPROM reads to 0..63, so no valid packet crosses a low-byte
wrap. Flash pointers must have bit 15 clear, and every actual reply-pointer
producer and consumer must adopt the tag together. EEPROM readiness and the
final Flash SPM boundary guard are unchanged. **Never remove SPM page-address
alignment:** ATtiny48/88 doc8008 section 19.0.3 requires non-PCPAGE Z bits zero
for Page Write, even though Page Erase ignores them.

This combined linked change saves **eight code bytes**, including strict
full-word configuration validation: **1110 to 1102 bytes at 0x1C00**. It frees
r2; poisoned-r2 tests ensure it no longer selects memory. The fitting
off/high/low profiles change 1114/1132/1130 to 1106/1124/1122 bytes. PHY machine
bytes are identical. The arithmetic C reference in
[micronucleus-state-reuse.c](examples/micronucleus-state-reuse.c) checks the
state invariant independently of EEPROM hardware access; it is not a new
MicroMusic runtime backend.

Validation at source commit `9b3918c05d09ed2977604267cf1b1c4e51476616` covers
13824 standard request combinations, 2658 stateful control transfers including
descriptor wLength 0..256 and 8/8/2 packets, independent CRC/PID checks,
393216 configuration-word/prior-state cases (all 65536 words from both valid
states in each of three profiles), 540 Flash/EEPROM payload/CRC/tagged-pointer
cases, 196608 cursor inputs, and full NVM/host tests. These are instruction/IO
models, not electrical USB or timing admission.

### Merge an idle-time delay with a bounded SRAM initialization loop

After hardware RESET, the loader must disconnect USB for roughly 301 ms and
clear 44 context bytes. Their iteration counts can share Y: delay once per
context byte, then pre-decrement/store zero. This removes the separate outer
delay counter and standalone clear loop:

```asm
; GPL-2.0-or-later MicroNucleus excerpt, source commit 0cd03c7.
; Before this fragment: r1=0; reset cause captured; watchdog disabled;
; D- driven low; Y=0x012c. Interrupts and PCINT remain disabled.
outer:
    ldi     r24, lo8(27359)
    ldi     r25, hi8(27359)
inner:
    sbiw    r24, 1
    brne    inner
    st      -Y, r1
    cpi     r28, 0
    brne    outer
; Y=0x0100, r25:r24=0; only then release D- and enable USB polling.
```

The context cannot be consumed until the complete clear finishes; it is safe
here because USB is physically disconnected and its pin-change source is
disabled. The exact range 0x012B..0x0100 is 44 bytes and never crosses the
low-byte stop condition. A different base/range needs a new end test and
delay calculation. All paths require hardware/watchdog RESET, reset-owned
stack and I=0; a software jump into startup is unsupported. The delay relies
on a 16 MHz CPU clock and an unprogrammed WDTON fuse, as did the previous code.

The invariant is not merely final SRAM content. Execute WDR before changing
watchdog prescaler bits, capture MCUSR before clearing it, clear WDRF before
clearing WDE, and keep the WDCE/WDE timed writes within four CPU cycles.
This loader's two STS instructions write the unlock value 0x18 and then zero
two cycles apart. Disable the inherited watchdog before the 300 ms delay.
See the primary [ATtiny48/88 doc8008](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf),
sections 8.4/8.5.2 for watchdog sequencing and 8.1 for GPIO RESET state.

The inner countdown is exactly `4 * 27359 - 1` cycles. Including 44 outer loads,
stores, comparisons, branches and the initial DDR write, the disconnect
interval is 4815449 CPU cycles: **300.9655625 ms at 16 MHz**. The linked change
saves **six bytes**, **1102 to 1096 bytes at 0x1C00**, at source commit
`0cd03c728f63f7cabb701ea5e2503bf48ecd3027`. The off/high/low fitting profiles
then occupy 1100/1118/1116 bytes. The LED-off build remains 72 bytes above
the 1024-byte target.

`tests27/startup_init.py` executes actual emitted words, accelerating only the
verified `SBIW r24, 1; BRNE` countdown. It checks the exact 44 addresses, untouched
surroundings, zero registers/persistent cursors, final Y, reset-cause capture,
watchdog write timing and ordering, disconnect interval and USB enable order.
Independent rebuilt mutations move MCUSR clearing after watchdog writes or
replace WDR by a same-cycle MOV; both are rejected by the strengthened model
while the measured baseline passes. The portable reference checks the merged
loop's address/count arithmetic; it does not emulate watchdog hardware.

Reproduce both checkpoints from the corresponding MicroNucleus source commits
in `experimental/attiny88/compact` with `sh verify27.sh`. Startup standalone:
`python3 tests27/startup_init.py`. Toolchain remains Clang/LLVM 18.1.3,
`-target avr -mmcu=attiny88 -x assembler-with-cpp`, GNU `avr-ld` 2.26 and
Python 3.12.3. Build/model evidence and exact provenance are added to the
[measurement record](measurements/micronucleus-compact-state.json).

### Evidence and reuse boundary

The [measurement record](measurements/micronucleus-compact-state.json) pins
the exact local experiment sources and verification scripts by SHA-256.
Pass26's original snapshot is `378ebfecb33da72d2bbd460757f364911a46616c`;
the preserved MicroNucleus import is `cfce71f`, and the later modular checkpoint
is `7642197`. Candidate source organization and later optimization may change
independently of these isolated measurements.

The snippets derive from Micronucleus/V-USB and retain GPL-2.0-or-later
provenance. The ELF checker is an original documentation utility. No loader
binary or new handwritten runtime backend is incorporated into MicroMusic.
Any production arithmetic backend adapted here must still retain an explicitly
selectable equivalent C implementation, architecture plus explicit ASM-enable
selection, and a common reference-output check, as required by this repository.
