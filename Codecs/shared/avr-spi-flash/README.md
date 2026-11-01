# ATmega328P SPI Flash reader

`AvrSpiFlashReader.h` is a codec-independent, read-only blocking byte reader.
It supports ATmega328P hardware SPI only: PB2/SS is active-low CS, PB3/MOSI and
PB5/SCK are outputs, and PB4/MISO is input. Vendor `avr/io.h` macros define all
registers and pins. Mode 0, MSB first and SPI2X with SPR=0 select F_CPU/2; at
16 MHz CPU that is 8 MHz SPI. This header introduces no arithmetic backend.
The clock selection follows table 18-5 of the official
[ATmega328P datasheet, 7810D-AVR-01/15](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf).
The [W25Q128JV device's 133 MHz rating](https://www.winbond.com/hq/product/code-storage-flash/qspi-nor/w25q-jv/?__locale=en&partNo=W25Q128JVBIMG)
is a chip limit; this MCU configuration uses 8 MHz. The byte protocol model does
not model analog setup/hold, signal integrity or complete electrical behavior.

Call `avr_spi_flash_init(&reader)`, then
`avr_spi_flash_begin(&reader, address, bytes)`. Addresses and declared lengths
are 32 bit, bounded to one 16 MiB address space. Each begin sends fast-read 0x0b,
three address bytes and exactly one dummy byte. `avr_spi_flash_read(&reader)`
returns 0..255 or -1 when its declared bound is exhausted. The same function can
be used directly as an `int16_t (*)(void *)` decoder callback. Close before
changing streams or after playback with `avr_spi_flash_close(&reader)`.

The consumer need not read all declared bytes. An unread final packet tail is
discarded by close or by the next explicit seek. No byte is prefetched or copied
instantly: every transfer writes SPDR and polls SPIF, allowing interrupts during
the wait. There is no bus timeout, CRC or disconnected-device detection; 0xff is
a legitimate byte. Bounds errors are distinct from electrical fault detection.

Only initialization, sequential reads and CS framing are implemented. This is
not a programming/erase driver. Timing and firmware support require the separate
interrupt-active simavr evidence; no physical-board claim is made here yet.

The caller exclusively owns the SPI controller and PB2 CS during use. The reader
is foreground-only and non-reentrant. Interrupts may run during transfers, but
the PWM ISR and every other ISR must leave SPI registers, CS, MOSI/SCK direction
and DDRB unchanged. This small driver adds no locking or bus arbitration.

`PROVENANCE.json` pins the actual unchanged installed AVR GCC 7.3.0 / avr-libc
2.0.0 header bytes, including `io.h` and `iom328p.h`. `test_compile.py --avr-bin
PATH --output FRESH_BUILD_FOLDER` checks the real target definitions with C99 and
C++11, a callback-compatible signature and 32-bit address/length API. These are
object-only bounded checks; playback/timing evidence is a separate stage.
