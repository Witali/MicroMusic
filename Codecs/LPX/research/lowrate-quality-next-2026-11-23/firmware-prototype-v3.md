# Prototype-v3 public firmware evidence

These measurements precede the retained brightness and octave safeguards. They
are historical prototype-v3 evidence; reuse for a selected input requires exact
LPX, host PWM, core and image bindings.

The two changed strict-3k public streams and the strongest changed 8k preset
were played completely on Tiny88 ASM, Mega328P ASM and Mega328P C, at 16 MHz /
8 kHz. Decoder, player, builder, observer and vendor-header source paths match
the pinned `ba02e453` context. The immutable prototype inputs preserve level and
contain no gain metadata. **All nine images passed: 112,491 exact PWM samples,
zero underruns or decoder errors**, full EOF, drained FIFO, stopped sample
timers, four-cycle IRQ entry/completed RETI and positive observed stack margins.
Each prototype portable C reference also matched its frozen host PWM sidecar.

| Preset, kbit/s | Samples / profile / brightness Q14 | Target / arithmetic | Full Flash, B | Static SRAM, B | Stack / margin, B | Active producer mean, cycles/sample |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 3 | 8466 / P4 / 128 | Tiny88 / ASM | 4020 | 418 | 28 / 66 | 1519.006870 |
| 3 | 8466 / P4 / 128 | Mega328P / ASM | 3408 | 417 | 24 / 1607 | 660.322554 |
| 3 | 8466 / P4 / 128 | Mega328P / C | 5064 | 428 | 68 / 1551 | 1615.382018 |
| 3 | 19200 / P4 / 0 | Tiny88 / ASM | 4518 | 418 | 28 / 66 | 1342.129224 |
| 3 | 19200 / P4 / 0 | Mega328P / ASM | 3904 | 417 | 24 / 1607 | 634.011577 |
| 3 | 19200 / P4 / 0 | Mega328P / C | 5562 | 428 | 68 / 1551 | 1552.888663 |
| 8 | 9831 / P6 / 256 | Tiny88 / ASM | 4580 | 418 | 28 / 66 | 1571.793311 |
| 8 | 9831 / P6 / 256 | Mega328P / ASM | 3968 | 417 | 24 / 1607 | 701.603548 |
| 8 | 9831 / P6 / 256 | Mega328P / C | 5624 | 428 | 68 / 1551 | 1709.567044 |

Embedded audio is respectively 391, 888 and 951 bytes. Program Flash excluding
only audio is 3629â€“3630 bytes on Tiny ASM, 3016â€“3017 on Mega ASM and 4673â€“4674
on Mega C. Full images include startup, tables, ISR and the neutral ROM player
gain byte. All fit standard application regions of 6012 / 30720 bytes. The
minimum observed FIFO occupancy was 23; output spacing was 1992â€“2008 cycles
around the 2000-cycle sample period.

The first P4 stream newly activates brightness128; its V3 incumbent had zero.
The P6 stream already used brightness256. Unchanged decoder code therefore
does not imply unchanged runtime. A private control reset only the first P4
stream's brightness128 to zero. For all three targets, the linked executable
code and compressed payload were identical; only the brightness data byte
differed. These matched controls also passed 25,398 exact AVR/portable-C samples
with zero underruns.

| Target / arithmetic | Neutral producer mean | Bright128 producer mean | Added producer / decoder mean, cycles/sample |
| --- | ---: | ---: | ---: |
| Tiny88 / ASM | 1418.006515 | 1519.006870 | 101.000355 / 101.000355 |
| Mega328P / ASM | 627.322199 | 660.322554 | 33.000355 / 33.000355 |
| Mega328P / C | 1543.960436 | 1615.382018 | 71.421582 / 71.421582 |

Flash, static SRAM and observed stack were unchanged in the matched pairs.
These are measured filter/output-path costs on one payload, rather than
universal per-sample instruction costs. Foreground means exclude IRQ time;
producer measurement includes decode/PWM conversion and FIFO publication,
whereas decoder measurement covers its narrower call interval. Buffered bursts
can exceed one sample period, so means are not worst-case execution bounds.

The source-pinned recipe uses AVR-GCC 7.3.0, simavr 1.6, runtime headers,
FIFO32/prefill24, two LPC segments, multiplication unroll2 and neutral ROM
gain128. ASM arithmetic/ISR are explicitly enabled on supported targets; Mega C
uses C arithmetic/ISR. [Anonymous numeric results](firmware-prototype-v3.json) retain all
complete checks, sizes and decoder timing. Inputs, code/data bindings, images
and logs remain private. These fixed public-input simulations establish no
physical-board, arbitrary-stream, higher-rate or new Tiny C support claim.
