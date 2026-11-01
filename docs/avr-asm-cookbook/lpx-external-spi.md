# Clocked external-source reads on ATmega328P

Applicable target: ATmega328P, AVR5, the existing AVR GCC 7.3.0 / avr-libc 2.0.0
toolchain, normal AVR ABI and vendor `avr/io.h` definitions. The
[small shared reader](../../Codecs/shared/avr-spi-flash/README.md) separates SPI
memory access from codec arithmetic and retains the explicitly selectable C
backend. No handwritten arithmetic assembly is introduced.

Measured builds use `-mmcu=atmega328p -Os -std=gnu++11 -flto -mcall-prologues
-mrelax -fno-exceptions -fno-rtti`, compact-only speech, dot unroll 1 and function
tuning 0. Queue 256 / prefill 192 and explicit callback/backend defines are
fixed by the source-bound player recipe.

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

The [completed finite player campaign](../../Codecs/LPX/research/v5-external-spi-player-2026-11-01/RESULTS.md)
passed all 28 case/configuration rows. Six full 60-reset chains at both normal
and +100 IRQ loads verified 45,433,332 physical PWM samples without underruns.
Long ASM images use 5,308 / 5,316 B complete Flash, including 360 B metadata,
and 764 B static SRAM; minimum long stack margin was 1,223 B. Exact matched short
controls measure +381 B program Flash for ASM, +383 B for C and +8 B SRAM.
C support remains bounded output parity; no sustainable C 8 kHz claim follows.
Long observations separate 16-cycle SPI duration from at most two dispatch
cycles and up to 80,372 cycles of software gaps; 4,849 byte completions occurred
inside audio IRQs. These measurements retain the simulator limitations above.
Unrepresentable long ROM images have no invented linked program-size baseline.

Untested next step, outside this campaign: these images concatenate full stored
segments. One 32-bit base plus uint16 sizes would use 4+2N metadata bytes rather
than 6N: 124 instead of 360 B for 60 resets, saving 236 raw metadata bytes before
code and linked-layout costs. A 32-bit running address must advance by the full
stored span, including unread packet tails. Measure actual linked Flash, SRAM
and IRQ-active timing before adoption; no implementation or new run is included.

References: [Microchip datasheet 7810D-AVR-01/15, table 18-5](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf),
[upstream simavr1.6 SPI source](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/avr_spi.c).
The host correction retains GPL-3.0-or-later source provenance; QEMU-derived
protocol-model provenance/licenses are retained separately in the model package.
