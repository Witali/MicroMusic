# UM88: compile only the selected output channels

Original MicroMusic size/timing technique for ATtiny88 / AVR25, GNU AVR GCC
7.3.0, GNU ABI, `-Os -fno-jump-tables -ffunction-sections -fdata-sections
-Wl,--gc-sections`. Source commit: `2cfcec2f`; previous release: `565e8958`.
C remains the default and explicitly selectable fallback on AVR itself. ASM
still requires the real target macro and a separate opt-in.

`audio-channels.h` selects `UM_OUTPUT_CHANNELS=1|2`, default one. The builder
requests the effective score channels explicitly. `--channels auto` follows
source data; `mono` and `stereo` override only the effective channels field.
Original events, voices, grammar, pitches and timings remain intact. Platform
header conflicts and source/destination alias conversions fail before output.

| Output | Return ABI | Producer | Fixed ISR |
| --- | --- | --- | --- |
| Mono | signed16 in r25:r24 | Four contiguous bytes | OCR1B only, one FIFO byte |
| Stereo | packed L/R in r22:r25 | Interleaved four-point interpolation | OCR1A/B, two FIFO bytes |

Mono preserves the historical left mix, including its left-pan attenuation.
It has no right accumulator/pan, stereo interpolation function, runtime channel
variable, OCR1A initialization/IRQ stores or PB1 output enable. Stereo removes
the mono producer branch. Shared Timer1 setup remains required: mode 5 has
fixed TOP 0x00FF, and COM1A=0 disconnects only the unused A output.
See [Microchip 8008H tables 12-3 and 12-5](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf#page=110).
Register names remain from the pinned manufacturer DFP. Bootloader watchdog,
PRR ordering, factory fuses and application boundary are unchanged.

The no-OCR1A-write requirement is tested externally. The startup/runtime test
independently decodes effective store addresses, including pre/post increment
and displacement. It catches even same-value writes to either byte, tests
negative controls, and observes initialization, 1024 IRQs and a control tick.
Shared TCCR1A cleanup is allowed. **No runtime check or OCR1A read is added to
the firmware.** SREG, nonzero r1 and all ABI rules are checked separately.

Final compact192 cores at 8/16 MHz: ASM mono 2132/2184 bytes, stereo
2236/2288; C mono 2202/2254, stereo 2346/2398. These combined figures include
the separately documented smaller decoder/control and bounded gain loops;
they are not isolated channel-selection savings. Tight word-aligned placement
starts music after the actual linked code, without the old 2560-byte floor or
32-byte padding. Per-song reports record the real address and padding.

Active-IRQ validation covers all18 retained full loops and restart, 176 decoder
cases, 48 control variants, exhaustive C/ASM arithmetic and fixed-channel IRQs.
The measured C stereo workload still fails its deadline; arithmetic equivalence
is distinct from real-time qualification. Physical hardware was not measured.
[Combined hashes, sizes and results](../../ATtiny88/Music/universal/reports/configured-channels-comparison.json).
