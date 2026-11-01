# SPI Flash input for Speex playback

The original integration measurements below are preserved at their source
baseline. The later [exact RNG optimization](WB_NOISE_SPEED.md) retests the
complete WB3.95 SPI file with unchanged PWM and zero underruns: minimum queue
17 -> 25, Flash 25260 -> 25316 B, free SRAM 396 -> 397 B. The current source
overlay is checked by `tests/audit_noise_speed.py`.

The standalone [SPI player](examples/spi_flash_player.c) reads uniform raw
Speex packets from external W25Q128 storage into the existing packet buffer,
then calls the unchanged NB or compact-WB decoder API. Arithmetic backend
selection remains independent of the input source. No external-file cache,
heap or additional PCM frame is allocated. Counts and addresses are 32 bit;
the reader bounds every stream to the 16 MiB device address space.

It reuses [the shared AVR reader](../../shared/avr-spi-flash/README.md), also
used by LPX. The decoder library has no SPI dependency, and its exported C
package stays portable to other architectures.

## Pins and source contract

ATmega328P at 16 MHz uses the manufacturer's `avr/io.h` definitions:

| Function | Pin |
| --- | --- |
| PWM output, Timer1 OC1A | PB1 / Arduino D9 |
| Flash active-low CS, hardware SS kept output | PB2 / D10 |
| MOSI | PB3 / D11 |
| MISO | PB4 / D12 |
| SCK | PB5 / D13 |

Hardware SPI runs Mode 0, MSB first, F_CPU/2 = 8 MHz. Begin sends `0b`, three
address bytes and one dummy byte. CS remains low during sequential playback;
each byte is obtained by writing SPDR and polling SPIF. Interrupts remain
enabled after audio prefill, including during transfers and waits. The PWM ISR
does not touch SPI or its pins. Close deasserts CS before the final queue drain.

The bus is owned exclusively by this foreground reader. It is not reentrant
and provides no arbitration, erase/program operation, CRC, timeout or electrical
fault detection. A returned `ff` is valid data. The byte callback returns -1
when the declared software length is exhausted. Bad packets use the decoder's
existing error return; playback then closes input and drains queued samples.

The stored stream has one complete raw frame per packet and one fixed width
for the whole demo. It contains no Ogg headers, index or new codec format.
Rate/length/address metadata is generated into small firmware constants. The
compressed bytes are stored only in external Flash. A file can cross pages
and 64 KiB boundaries; no `uint16_t` pointer or frame index truncates its address.

## Build

Explicitly select ASM for real-time WB on this MCU. For example:

```sh
python Codecs/Speex/AVR/tools/build_spi_player.py --avr-gcc avr-gcc --backend asm --wideband --enable-nb4 --low-rates 7 --stream <raw-file> --address 0xff80 --out Codecs/Speex/AVR/build/spi-demo --image-out Codecs/Speex/AVR/build/spi-demo/flash-image.bin
```

Omit `--wideband` for NB. Defaults without `--backend asm` use the selectable
C arithmetic fallback; no C real-time claim is made here. Optional feature-mask
bits retain their meanings from [LOW_RATES.md](LOW_RATES.md).

`player.hex` programs the MCU. The optional `flash-image.bin` is an exact
16 MiB programmer image, filled with `ff` outside the supplied sound. It must
be programmed separately into the SPI Flash; this read-only example does not
write the chip. The image writer refuses to overwrite an existing file.
The generated `input.json` binds packet count, address, length and firmware
hash. Media, programmer images and firmware stay in ignored build directories.

## Reproducible simulation

The host verifier uses the shared, pinned QEMU-derived read-only C model,
compiled to WASM without changing its protocol implementation. The model and
bridge are host-only GPL-2.0-or-later tooling; neither is linked into the
Speex library or MCU firmware. Original source/license/provenance are in
`third_party/qemu-m25p80/`, and the shared port is in `tools/spi-flash-model/`.

Every AVR SPDR write schedules completion through the avr8js SPI peripheral
after 16 CPU cycles at 8 MHz. At completion the transmitted byte is passed to
the C model; only its returned byte is delivered to SPDR. GPIO CS framing,
software gaps, timer activity and interrupt entry all advance normally.
The host never supplies a ready packet in MCU RAM. Model counters verify the
command, three address bytes, one dummy byte and every payload byte.

```sh
python Codecs/Speex/AVR/tools/build_spi_player.py --wasm-clang <wasm-capable-clang> --wasm-sysroot <sysroot> --out Codecs/Speex/AVR/build/spi-model
node Codecs/Speex/AVR/tests/verify_spi_model.mjs Codecs/Speex/AVR/build/spi-model/model.wasm
python Codecs/Speex/AVR/tests/prepare_spi_streams.py --legacy-root <codec-root-with-existing-corpora> --oracle <independent-oracle>
python Codecs/Speex/AVR/tests/build_spi_matrix.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_spi_player.mjs Codecs/Speex/AVR/build/spi-final/wb395 Codecs/Speex/AVR/build/spi-corpus/wb395/long.spxraw Codecs/Speex/AVR/build/spi-corpus/wb395/long.pcm Codecs/Speex/AVR/build/spi-model/model.wasm
```

`--capture-pcm` adds diagnostic observation before the production output queue;
it does not bypass SPI or decoding. The matrix also builds WB3.95 without that
instrumentation. The prepared long streams interleave retained Russian/English
clips without resetting decoder history; the independent oracle processes the
same concatenation. Physical-board, electrical and analog-output measurements
are outside this simulation.

## Retained results

The final reader comes from the neighboring LPX SPI task, original focused
commit `318b56e23a33790e104095bfc02f506053807eae`. The imported header is
byte-identical to the tested integration candidate. AVR GCC 7.3.0 builds the
firmware; avr8js 0.21.1 plus `avr_tick.mjs` models the ATmega interrupt timing.
The host model is compiled with freestanding wasm32 Clang 24.0.0git / O2.

All optional low rates and NB4 are enabled in every measured image. Each file
interleaves retained Russian/English clips and begins at address `0xff80`,
so every run crosses a 64 KiB address boundary. WB12.8 is itself larger than
64 KiB. Playback preserves decoder history for the entire file.

| Mode | Frames | Compressed bytes | MCU Flash | Static SRAM | Peak stack | Free SRAM | Min queue |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NB11 | 1200 | 33600 | 17538 | 1269 | 140 | 639 | 74 |
| WB3.95 | 3600 | 36000 | 25282 | 1426 | 230 | 392 | 17 |
| WB5.75 | 2200 | 33000 | 25282 | 1431 | 238 | 379 | 22 |
| WB7.75 | 1800 | 36000 | 25282 | 1436 | 238 | 374 | 27 |
| WB12.8 | 2200 | 70400 | 25282 | 1448 | 218 | 382 | 30 |
| WB3.95, capture disabled | 3600 | 36000 | 25260 | 1422 | 230 | 396 | 17 |

The first five runs compare every s16 block and the entire PWM stream with
the independent oracle: **11000 frames**. The production WB3.95 image adds
3600 frames with entire-PWM comparison, totaling **14600 frames**, **4480000
output samples** and **zero underruns**. No extra foreground stress is added
to these SPI runs. NB2.15 and WB3.95 also pass separate 32-frame integration
probes; other NB rates and WB9.8 are covered by core/internal-Flash admission,
rather than independent long SPI runs.

Every long run uses exactly one command, three address bytes, one dummy byte
and exactly the declared payload length. Unsupported commands and resets stay
zero. Wire scheduling reserves 16 CPU cycles per byte. Observed host callback
service takes 17..23 cycles at instruction boundaries; polling and interrupts
continue to consume their normal CPU cycles. No zero-time packet injection is
used. PCM timer intervals remain within +/-10 cycles of 1000/2000 cycles.

The same standalone player also compiles/links with C arithmetic: NB11 uses
21098 B and WB3.95 uses 30750 B Flash.
Those C images are not executed or timed, as requested. Original minimal
decoder builds and the low-rate exact-PCM admission remain unchanged.

Reports are `reports/spi-input-*.json`. Source, reader, protocol model, oracle
and firmware hashes are checked by:

```sh
python Codecs/Speex/AVR/tests/audit_spi_input.py --corpus Codecs/Speex/AVR/build/spi-corpus
python Codecs/Speex/AVR/tests/audit_spi_input.py --corpus Codecs/Speex/AVR/build/spi-corpus --avr-gcc avr-gcc --wasm-clang <wasm-capable-clang> --wasm-sysroot <sysroot>
```

The second command rebuilds all six ASM images and the host model and requires
byte identity with the tested binaries. It does not rerun or time C decoding.
