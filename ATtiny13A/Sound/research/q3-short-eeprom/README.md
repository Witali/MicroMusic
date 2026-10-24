# Exact short excitation tables with EEPROM speech prefixes

The same complete Vinni sound fits **972 Flash + 64 EEPROM bytes**, versus
990 + 64 for the preceding 368-byte-core image. The confirmed net Flash saving
is **18 bytes**, after accounting for the new reader and all table addressing.
Speech capacity increases from **655 to 673 bytes**. No audio fitting or
quantization is performed; all output bytes remain identical.

## Controlled comparison

The logical book is still four signed 16-tap rows. The retained model has only
four active taps per row; removing the remaining zeros is exact. The encoder
rejects any attempted removal of nonzero taps. It compares widths 4/8/16 and
both byte and nibble representations, with and without an EEPROM speech prefix.

| Width / representation | Waveform EEPROM | Speech EEPROM | Core | Complete Flash | Minimum slack |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16 / scaled bytes, previous layout | 64 | 0 | 368 | 990 | 352 |
| 4 / scaled bytes, tables only | 16 | 0 | 372 | 994 | 352 |
| **4 / scaled bytes + prefix** | **16** | **48** | **398** | **972** | **208** |
| 4 / signed nibbles, tables only | 8 | 0 | 384 | 1006 | 346 |
| 4 / signed nibbles + prefix | 8 | 56 | 410 | 976 | 202 |
| 8 / scaled bytes + prefix | 32 | 32 | 396 | 986 | 211 |
| 8 / signed nibbles + prefix | 16 | 48 | 408 | 982 | 205 |
| 16 / signed nibbles + prefix | 32 | 32 | 406 | 996 | 205 |

All byte counts are actual linked AVR images, including EOF and alignment.
The report also preserves the remaining table-only controls: eleven full Vinni
builds in total. All 66,816 phrase/silence samples per build match the frozen
integer decoder in reference, WASM and unoptimized WASM. The logical stream
remains 620 bytes and the full phrase remains 22,272 samples at 7,500 Hz.

The best layout contains 398 code + 572 Flash speech + 1 EOF + 1 alignment byte.
EEPROM holds 16 waveform bytes and the other 48 original speech bytes. Thus
the 30-byte code increase is paid for by moving 48 data bytes out of Flash.
The Flash reserve is now 52 bytes. Tighter nibble packing frees eight more
EEPROM bytes but costs twelve more code bytes, giving a four-byte worse total.

## Physical formats and reader

- **Raw:** store each logical tap multiplied by eight as one signed byte.
  The existing wide Q3 multiplier then computes `floor((tap*8)*gain/8)` exactly.
- **Nibble:** store signed two's-complement taps, even tap low and odd tap high.
  The code selects the nibble, moves its sign into bit 7 and shifts right once
  to obtain the same signed `tap*8`. Nibble 8 (−8) is forbidden by the model.
  This format is distinct from the older coefficient-plus-eight pulsebook.
- **Speech prefix:** append unchanged leading stream bytes after the table.
  ZH=0 identifies EEPROM reads; after the final prefix byte, Z switches to
  the Flash suffix. Five stream-reader sites use the shared 26-byte routine.
  A split can occur inside a header or coefficient update; no frame padding
  or additional data bytes are introduced. EOF always remains in Flash.

Firmware and its EEPROM image are one pair. The source declares its width,
packing and prefix boundary at assembly time; there are no per-sample format
tests. The automatic selection minimizes the complete verified Flash image,
not the isolated waveform table. Public firmware is unchanged.

## Qualification

Five pure-layout tests cover all signed tap values and widths, strict zero-tail
checks, every possible prefix split, short streams, invalid physical encodings
and complete storage accounting.

Four AVR tests additionally assemble full frames with noise, short periods,
all four source modes, all four coefficient-update modes, compact/extended
headers, prefixes of zero/one/seven bytes, and a complete short stream in
EEPROM. Active tails at widths 8 and 16 are exercised, rather than testing
only zero-padded four-tap books. Physical 673-byte/raw and 669-byte/nibble
maximum streams actually fill **1024 Flash + 64 EEPROM**; larger streams are
rejected. The maximum tests retain complete frames and duration.

Real assembly kernel checks include interrupts between address calculation
and EEPROM access, between reading a prefix byte and advancing its pointer,
and at the EEPROM→Flash seam. All modes, taps, gains and flag cases are checked;
zero tails must bypass EEPROM access, including the speech region. The retained
[qualification](qualification.json) records image counts, exact kernel counts
and full-suite results; [report.json](report.json) preserves every Vinni variant,
source fingerprints, hashes and timing.

The best full phrase has 208 cycles of preparation slack at 9.6 MHz. This is a
measurement for this stream, not a universal bound. Every newly fitted stream
must be assembled and checked again. Physical hardware remains untested.
Because PCM is unchanged, STOI/spectrum, DC offset and strict 5-dB violations
are unchanged as well; this result provides more data capacity, not new quality.

## Reproduction

Configure the repository's Python codec dependencies, then run:

```powershell
python tools/probe-q3-short-eeprom.py --model ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json --avr-bin <AVR-bin> --node <Node-executable> --retain ATtiny13A/Sound/research/q3-short-eeprom/report.json
python tools/test-q3-short-eeprom.py
python tools/test-q3-short-eeprom-avr.py
```

Set `AVR_BIN` and `NODE` for the AVR tests. Both tests are also included in
`tools/test-speech-quality.py`. Generated assembly, paired HEX files, EEPROM,
PCM and detailed verification remain under ignored `build/q3-short-eeprom/`
and `build/q3-short-eeprom-validation/`.
