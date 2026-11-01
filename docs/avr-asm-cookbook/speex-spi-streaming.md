# Read long compressed audio without a file cache

Target: classic AVR5 ATmega328P, 16 MHz / 2 KB SRAM, AVR GCC 7.3.0, avr-libc
device headers. This is original project integration code, using the shared
read-only [SPI reader](../../Codecs/shared/avr-spi-flash/AvrSpiFlashReader.h).
It optimizes input storage/framing, independently of C/ASM decoder arithmetic.

Keep a single fast-read transaction open while the foreground decoder consumes
packets. Fill the existing 10..32-byte WB packet buffer, decode it, and read the
next packet. The reader keeps only a 32-bit remaining-byte count. The compressed
file and the PCM frame do not need large extra SRAM buffers.

The model consumes no payload while SCK is idle; the output ISR can run during
every SPI byte. This requires exclusive ownership of SPI and CS: no ISR or other
consumer may change the controller or pins. Validate 32-bit address + declared
length against the 16 MiB device space before issuing the 24-bit address.

At 8 MHz SPI, each eight-bit transfer takes 16 CPU cycles. One `0b` command,
three address bytes and one dummy byte cost five wire bytes per entire stream.
For 1800 twenty-byte packets, that is 36005 transfers rather than 45000 for a
fresh command per packet: a calculated difference of 143920 wire cycles.
This is a framing calculation, not a measured before/after decoder speedup;
polling, loop instructions, interrupt latency and queue waits add their own time.

Validation must run actual SPDR/SPIF instructions, scheduled transfer completion,
GPIO CS, timers and interrupts. A host callback that instantly copies a packet
into SRAM cannot establish this timing. Compare complete s16/PWM output with the
same continuous oracle, count underruns, and record stack high-water usage.
See the [Speex integration and evidence](../../Codecs/Speex/AVR/SPI_FLASH.md).
The arithmetic fallback selection and portable library API are unchanged.

Measured on the above toolchain with avr8js 0.21.1, the shared C model and
production output interrupts: six continuous streams total 14600 frames,
with exact PWM and zero underruns. WB3.95 capture-off firmware uses 25260 B
Flash / 1422 B static SRAM / 230 B peak stack, leaving 396 B; its 3600-frame
stream retains at least 17 queued samples. All three lower-rate features and
NB4 are enabled as documented in the linked admission. This is a measured working
integration, not a measured speedup over another SPI implementation or a
physical-board result.
