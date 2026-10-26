# Calibrating short AVR instruction probes with Timer1

Applicable target: AVRe ATtiny88, AVR-GCC 7.3.0 / `-Os`, nominal 16 MHz board.
This is an assembled validation fixture, not an optimization or a measured
hardware improvement. See [source and acquisition procedure](../../web-player/native/devices/attiny88/CORE_PROBE.md).

With interrupts disabled, Timer1 in normal mode at CPU /1, read TCNT1L then
TCNT1H, execute the stimulus, capture SREG, and read TCNT1L/H again. The high
byte must follow the low byte to use the hardware TEMP latch. Subtract an
otherwise identical empty control. In this wrapper the read overhead is five
ticks; stimuli must preserve the timer, destination pointer and timestamp
registers, and must fit in one 16-bit timer wrap. This checks instruction cycle
totals, not each internal bus phase or interrupt behavior.

Use `_SFR_IO_ADDR(SREG)` with an ordinary `%[sreg]` operand in GNU inline
assembly `IN`/`OUT`. AVR-GCC's `%i` address printer subtracts the I/O offset
itself; applying both would incorrectly access EECR instead of SREG on Tiny88.
Timer LDS operands use `_SFR_MEM_ADDR(TCNT1L/H)`. All register symbols come
from the original manufacturer header; do not duplicate numeric addresses.

Declare every clobbered register and `memory`/`cc`. The non-C-ABI RCALL/RET
stimulus is called only from assembly and declares its changed register.
These are test stimuli rather than a replacement arithmetic backend; there
is no assembly-optimized library path to select instead of C.

Bootloader startup is a separate validation axis: clear MCUSR.WDRF, execute
WDR and disable inherited watchdog through its protected window. The Tiny88
generated runtime now matches shared JS/C startup-reset diagnostics. Running
watchdog modes remain outside that music profile; the full ATtiny13A device
controller remains separate.

Software evidence: twelve cases pass in all three engines from reset and
inherited watchdog/stack state, with matching full CPU/data snapshots. EEPROM
commit and LED output remain beyond the checked software boundary. No silicon
result, speedup, portable timing equivalence or IRQ-active audio result is
claimed. Sources: [Microchip ISA](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
[ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf),
[AVR-LibC inline assembly reference](https://avrdudes.github.io/avr-libc/avr-libc-user-manual/inline_asm.html).
