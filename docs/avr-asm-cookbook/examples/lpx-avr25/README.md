# AVR25 software products and exact shifts

Original, standalone arithmetic prototype for ATtiny88 / AVR25 GNU ABI,
AVR-GCC 7.3.0, `-Os -mrelax`, 16 MHz. It uses no hardware multiply. The later
[integrated AVR25 player](../../lpx-avr25.md) has its own complete image,
active-IRQ and stack measurements; the standalone numbers below remain
historical arithmetic evidence. The public function interface is in
`avr25_math.h`; `math.cpp` provides the default C implementation, including
on AVR25 itself. Compile both C++ and `.S` with `LPX25_ENABLE_ASM=1` to
explicitly select assembly on a real supported AVR25 target. Other targets
retain C; for a non-AVR build compile `math.cpp` alone.

The product computes unsigned 16 x 16 by conditional addition and carry
rotation, then subtracts unsigned y from the high word when x is negative
and unsigned x when y is negative. The correction is modulo 2^32 and retains
the complete signed product, including -32768 x -32768. Only caller-saved
r18-r25 are changed; r1 remains zero. The shifts reuse the project's exact
byte-aligned signed 24-bit shift identity from `Lpx4Math.h` and restore the
full sign byte. No multiplication source listing was copied from a vendor.

| Primitive | C cycles | ASM cycles |
| --- | ---: | ---: |
| Signed 16 x 16 -> 32 | 33..481, mean 312.75 | 112..130, mean 119.75 |
| Signed floor shift by 12 | 88 | 21 |
| Signed floor shift by 14 | 102 | 27 |

Counts run from routine entry through RET, excluding the caller's RCALL
(three cycles). Means refer only to the retained boundary/random vectors;
C is faster for some trivial operands. The ASM product follows
`112 + popcount(uint16_t(y)) + (x < 0) + (y < 0)` cycles. Do not infer a
whole-decoder speedup from this table.

Two actual linked images were each run with Timer1 overflow interrupts off
and on. All 2,288 results matched host integer arithmetic: 272 products and
150 values for each shift, per run. Each run checked 572 arbitrary
callee-saved-register sentinels and r1 at primitive entry/return. Active
interrupt runs delivered 689 C / 343 ASM ISRs, with zero lost interrupts.
Gross IRQ-inclusive ranges were 33..610 / 112..173 cycles for C / ASM
products, 88..131 / 21..64 for shift12, and 102..145 / 27..70 for shift14.
The existing transpiled AVR CPU supplied instruction/cycle/stack observations.
This is simulator evidence, not physical-board timing or 8 kHz playback proof.

Full benchmark Flash is 2,118 B C / 2,354 B ASM (+236 B), including the same
1,688 B PROGMEM vector tables. Static RAM is 14 B. Standalone ASM routines
occupy 254 B for multiplication and 36 / 48 B for the shifts, including RET.
These are benchmark costs; a complete LPX image needs its own Flash, RAM,
stack, output and active-IRQ admission. [`measurements.json`](measurements.json)
retains numeric results and exact source hashes without private runtime paths.

Example compile commands, run in this folder with the existing toolchain:

```sh
avr-g++ -mmcu=attiny88 -DF_CPU=16000000UL -Os -mrelax -ffunction-sections -fdata-sections -DLPX25_ENABLE_ASM=0 math.cpp math.S probe.cpp -Wl,--gc-sections -o c.elf
avr-g++ -mmcu=attiny88 -DF_CPU=16000000UL -Os -mrelax -ffunction-sections -fdata-sections -DLPX25_ENABLE_ASM=1 math.cpp math.S probe.cpp -Wl,--gc-sections -o asm.elf
```

The harness reports through observation symbols, not a serial port. Its IRQ
control is externally set before entering main; retaining the ELF alone does
not reproduce the ABI-sentinel observer. Full build/runtime dependencies and
the two preserved setup failures remain in ignored source-bound receipts.
The inherited short vendor include path did not exist: the measured builds
used the installed toolchain's Atmel `avr/iotn88.h` through `<avr/io.h>`, not
the repository's newer Microchip DFP. No register address was recreated.

Primary references: [Microchip AVR200 / AN0936, 0936D-AVR-09/09](https://ww1.microchip.com/downloads/en/Appnotes/doc0936.pdf)
describes the shift/add tradeoff; its signed Booth variant excludes some
signed-minimum multiplicands and is not used here. Instruction costs come
from the [ATtiny48/88 datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf).
[Microchip's GNU register-usage guidance](https://onlinedocs.microchip.com/oxy/GUID-BD1C16C8-7FA3-4D73-A4BE-241EE05EF592-en-US-9/GUID-2AD18C68-727F-4761-80EA-B64055441545.html)
defines the preserved registers. Those references are algorithm/ABI sources;
they are not a license to redistribute an unverified vendor source archive.
