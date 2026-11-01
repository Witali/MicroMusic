# Clocked external-source reads on ATmega328P

Applicable target: ATmega328P, AVR5, the existing AVR GCC 7.3.0 / avr-libc 2.0.0
toolchain, normal AVR ABI and vendor `avr/io.h` definitions. The
[small shared reader](../../Codecs/shared/avr-spi-flash/README.md) separates SPI
memory access from codec arithmetic and retains the explicitly selectable C
backend. No handwritten arithmetic assembly is introduced.

Use Mode 0, MSB first, hardware SPI at F_CPU/2: 8 MHz for a 16 MHz CPU. Offsets
and reader bounds are 32 bit; encoded audio resides in the external image, with
only segment metadata and code charged to program Flash. The foreground owns
SPI/CS exclusively; an audio ISR may interrupt the polling loop but must not
touch those registers or DDRB. Partial final packets can leave stored bytes
unread, so close and explicitly seek the next segment rather than draining it.

The original simavr1.6 SPI implementation schedules every byte after a fixed
100 us. That delay cannot establish this target's SPI performance. The isolated
[source-pinned correction](../../Codecs/LPX/validation/atmega328p/spi/patch_simavr_spi.py)
uses eight periods of the actual SPR/SPI2X divisor. Packaged library internal
binding means executable symbol interposition is insufficient: explicitly
replace only the existing SPDR write handler, preserving the IO list and the
existing IRQ/read/input paths. Keep the installed library and ROM observer intact.

The pinned [raw run loop](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_avr.c)
services cycle timers before interrupts. Its
[interrupt service](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_interrupts.c)
and [_avr_push_addr](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_core.c)
do not add IRQ-entry cycles. That is a simulator-core limitation, retained here.
The no-sleep player bounds dispatch quantization by the four-cycle AVR5
RET/RETI instruction. Scheduled SPI duration remains 16 cycles; +100 IRQ stress
measures extra margin and does not repair general simulator interrupt timing.

Measured host-unit result: all eight divisor settings complete 48 actual
protocol bytes on AVR NOP cycles. Byte delays are 32, 128, 512, 1024, 16, 64,
256 and 512 CPU cycles; the F_CPU/2 case is 16 cycles. The byte/peripheral bridge
separately records instruction dispatch lateness and foreground/IRQ software
gaps. This unit establishes modeled byte duration, not physical electrical
setup/hold behavior or sustainable codec playback.

The [finite player protocol](../../Codecs/LPX/research/v5-external-spi-player-2026-11-01/PROTOCOL.md)
reserves bounded C/ASM output parity and full long ASM playback with active
normal/+100 IRQ loads. Those player measurements are pending at this stage.
C support remains explicit output parity; no sustainable C 8 kHz claim follows.
Charge actual complete linked images and metadata, SRAM, stack and underruns;
unrepresentable long ROM images have no invented linked program-size baseline.

References: [Microchip datasheet 7810D-AVR-01/15, table 18-5](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf),
[upstream simavr1.6 SPI source](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/avr_spi.c).
The host correction retains GPL-3.0-or-later source provenance; QEMU-derived
protocol-model provenance/licenses are retained separately in the model package.
