# Archived FAST P6/P8 activation-cost pair

**Scope: one immutable calls=0, preserve-level public pair only.** This is
offline activation evidence for existing V9 correction syntax. It does not
measure full search or the latest direct-P8 precision policy, and does not
prescribe a production P6 double encode/comparison.

Both inputs contain 23,757 samples at 8 kHz, prepared from 7.5 kHz with the
shared C++ FIR. They retain pre 13926, brightness 0 and no gain metadata. P6 is
ordinary wire profile 6; archived P8 uses that same profile with its existing
correction-fields flag. Audio occupies 1813/2486 bytes, a 673-byte difference.
The unchanged MCU/player/observer context is pinned to `ba02e453`.

Original input/code/module bindings and the separate native capture receipt
were verified. An independent pinned portable-C build reproduced all captured
PCM/PWM with strict EOF/error/finished checks. Six AVR images then passed
**142,542 exact native/C/AVR PWM samples**, zero underruns or decoder errors,
full EOF/FIFO draining, stopped sample timers, complete IRQ entry/RETI and
positive stack margins. These are simavr 1.6 observations with AVR-GCC 7.3.0,
GNU AVR ABI, 16 MHz/8 kHz, FIFO32/prefill24, LPC2 and multiplication unroll2.
ASM arithmetic/ISR are explicitly enabled on the supported real targets;
Mega C uses explicit C arithmetic/ISR. Tiny C is not measured here.

| Target / arithmetic | FAST policy | Full Flash, B | Audio, B | Program excluding audio, B | Static SRAM, B | Stack / margin, B |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Tiny88 / ASM | P6 | 5442 | 1813 | 3629 | 418 | 28 / 66 |
| Tiny88 / ASM | P8 | 6116 | 2486 | 3630 | 418 | 28 / 66 |
| Mega328P / ASM | P6 | 4830 | 1813 | 3017 | 417 | 24 / 1607 |
| Mega328P / ASM | P8 | 5502 | 2486 | 3016 | 417 | 24 / 1607 |
| Mega328P / C | P6 | 6486 | 1813 | 4673 | 428 | 68 / 1551 |
| Mega328P / C | P8 | 7160 | 2486 | 4674 | 428 | 68 / 1551 |

**Tiny P8 fits the physical 8192-byte MCU budget but exceeds the 6012-byte
MH-ET-LIVE bootloader application region by 104 bytes.** It was measured as a
legal ISP/bare-MCU image; this is no bootloader-board fit claim. Tiny P6 fits
both budgets. Every Mega image fits the 30720-byte application budget. Full
Flash includes the exact audio and neutral ROM player-gain byte. The one-byte
program-excluding-audio variations are linked layout/alignment effects under
unchanged universal sources, not added decoder functionality.

| Target / arithmetic | Producer P6 | Producer P8 | Producer increase | Decoder P6 | Decoder P8 | Decoder increase |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny88 / ASM | 1425.780474 | 1439.878355 | 0.988783% | 1335.780474 | 1349.878355 | 1.055404% |
| Mega328P / ASM | 665.030380 | 670.873509 | 0.878626% | 626.030380 | 631.873509 | 0.933362% |
| Mega328P / C | 1626.009860 | 1635.458939 | 0.581121% | 1563.009649 | 1572.458728 | 0.604544% |

Timing values are active foreground mean cycles/sample, excluding IRQ time.
Added producer and decoder work is respectively 14.097881, 5.843129 and 9.449079
cycles/sample. Producer measurement includes decoder/PWM work and FIFO
publication; the decoder interval is narrower. Complete IRQs cost 35/36/57
cycles by target/backend. Minimum FIFO occupancy is 25/27/23; output intervals
stay 1992–2008 cycles around the 2000-cycle sample period. Static SRAM, observed
stack and margin are unchanged between policies.

These differences include payload-dependent work and are not universal
correction-field instruction costs or worst-case deadline bounds. No encoder
latency, quality ranking, physical-board, arbitrary-stream or higher-rate
support conclusion follows from this archived pair. [Anonymous numeric data](anonymous-fast-pair.json)
contain absolute/delta timing, complete gates and separate physical/application
Flash limits; private bindings, original labels, media and logs remain excluded.
