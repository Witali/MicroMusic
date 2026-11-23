# Final V3 firmware measurements

All six final V3 images passed complete playback against decoder/player core
`69e915d4ad5023d6a1521c8ba3b31b06c76d7496`. The inputs are two whole,
preserve-level encodings of one fixed public phrase: 19,200 samples at 8 kHz,
with 3 and 8 kbit/s complete-file ceilings and no gain metadata. Every AVR PWM
sample matched both the separately compiled portable C reference and frozen
host decoder output: **115,200 exact samples, zero underruns or decoder errors**.
EOF, FIFO draining, stopped sample timers, four-cycle IRQ entry, completed RETI and
positive observed stack margins passed in every image.

| Target / arithmetic | Preset, kbit/s | Full Flash, B | Program excluding audio, B | Audio, B | Static SRAM, B | Stack, B | Stack margin, B | Minimum FIFO |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny88 / ASM | 3 | 4516 | 3629 | 887 | 418 | 28 | 66 | 26 |
| Tiny88 / ASM | 8 | 5110 | 3630 | 1480 | 418 | 28 | 66 | 25 |
| Mega328P / ASM | 3 | 3904 | 3017 | 887 | 417 | 24 | 1607 | 27 |
| Mega328P / ASM | 8 | 4496 | 3016 | 1480 | 417 | 24 | 1607 | 27 |
| Mega328P / C | 3 | 5560 | 4673 | 887 | 428 | 68 | 1551 | 24 |
| Mega328P / C | 8 | 6154 | 4674 | 1480 | 428 | 68 | 1551 | 23 |

Full Flash includes startup, tables, player, ISR, the neutral ROM player-gain
byte and the exact compressed stream. The program column excludes only audio.
All images fit the standard application regions: 6012 bytes on Tiny88 and
30720 bytes on Mega328P. Static SRAM includes the decoder workspace and FIFO;
stack and margin are observed across startup, prefill and interrupt playback.

| Target / arithmetic | Preset, kbit/s | Active producer mean, cycles/sample | Active decoder mean, cycles/sample | Complete IRQ, cycles |
| --- | ---: | ---: | ---: | ---: |
| Tiny88 / ASM | 3 | 1340.387098 | 1250.387098 | 35 |
| Tiny88 / ASM | 8 | 1394.036035 | 1304.036035 | 35 |
| Mega328P / ASM | 3 | 634.003755 | 595.003755 | 35 |
| Mega328P / ASM | 8 | 665.093972 | 626.093972 | 36 |
| Mega328P / C | 3 | 1552.843189 | 1489.842929 | 57 |
| Mega328P / C | 8 | 1627.357322 | 1564.357322 | 57 |

These foreground means exclude IRQ time during active playback. Producer work
covers the head read through decoding, PWM conversion and FIFO publication;
the decoder measurement covers its narrower call interval. Buffered frame
conversion can exceed one sample period, so means are not worst-case bounds.
The 16 MHz / 8 kHz sample period is 2000 cycles; observed output spacing across
all six images was 1992–2008 cycles. [Numeric results](firmware.json) retain
per-image spacing, complete IRQ checks and producer peaks.

The source-pinned recipe uses AVR-GCC 7.3.0, simavr 1.6, runtime stream headers,
FIFO32/prefill24, two LPC segments, multiplication unroll2 and neutral ROM player
gain128. ASM arithmetic and ISR are explicitly enabled on supported targets;
Mega C uses C arithmetic and ISR. The [runner](firmware.py) and
[reproduction instructions](firmware-reproduction.md) preserve exact source,
input and model bindings privately.

Earlier Tiny C failures against the gain-enabled `9d15e9f9` core and V2 input
remain historical. Tiny C was not rerun against the final core, and those
earlier sizes or timings do not describe these final images. These fixed-input
simavr results establish no physical-board, arbitrary-stream or higher-rate
support claim. Source audio quality is evaluated separately from exact decoder
implementation output.
