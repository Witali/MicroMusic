# Guarded-selected public firmware validation

All nine selected images pass complete 16 MHz / 8 kHz playback: **112,491 exact
PWM samples**, zero underruns or decoder errors, correct EOF/FIFO draining,
stopped sample timers, four-cycle IRQ entry/completed RETI and positive observed
stack margins. Each portable C reference matches the frozen selected host PWM.
The core/player/builder/observer context is pinned to `ba02e453`.

The 8,466-sample strict-3k selection returns to its exact V3 incumbent with
brightness 0. Its three images were rebuilt and simulated. The 19,200-sample
strict-3k and 9,831-sample 8k streams retain exactly the earlier LPX and host PWM
bytes. Their six measurements are reused after verifying complete input, core,
image, portable-reference, observer and stored AVR-output bindings. Original
receipts and labels remain intact privately; reused rows are marked in the
[numeric proof](firmware.json).

| Preset, kbit/s | Samples / profile / brightness Q14 | Target / arithmetic | Full Flash, B | Static SRAM, B | Stack / margin, B | Active producer mean, cycles/sample |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 3 | 8466 / P4 / 0 | Tiny88 / ASM | 4020 | 418 | 28 / 66 | 1336.006041 |
| 3 | 8466 / P4 / 0 | Mega328P / ASM | 3408 | 417 | 24 / 1607 | 627.321725 |
| 3 | 8466 / P4 / 0 | Mega328P / C | 5064 | 428 | 68 / 1551 | 1543.975835 |
| 3 | 19200 / P4 / 0 | Tiny88 / ASM | 4518 | 418 | 28 / 66 | 1342.129224 |
| 3 | 19200 / P4 / 0 | Mega328P / ASM | 3904 | 417 | 24 / 1607 | 634.011577 |
| 3 | 19200 / P4 / 0 | Mega328P / C | 5562 | 428 | 68 / 1551 | 1552.888663 |
| 8 | 9831 / P6 / 256 | Tiny88 / ASM | 4580 | 418 | 28 / 66 | 1571.793311 |
| 8 | 9831 / P6 / 256 | Mega328P / ASM | 3968 | 417 | 24 / 1607 | 701.603548 |
| 8 | 9831 / P6 / 256 | Mega328P / C | 5624 | 428 | 68 / 1551 | 1709.567044 |

Audio occupies respectively 391, 888 and 951 bytes. Program Flash excluding
only audio is 3629–3630 bytes on Tiny ASM, 3016–3017 on Mega ASM and 4673–4674
on Mega C. Full Flash includes startup, tables, ISR and the neutral ROM player
gain byte. All images fit standard application regions of 6012 / 30720 bytes.
Static SRAM includes the workspace/FIFO. Minimum FIFO occupancy is 23; output
spacing is 1992–2008 cycles around the 2000-cycle sample period.

Foreground means exclude IRQ time. Producer intervals include decoding, PWM
conversion and FIFO publication; decoder intervals are narrower and are retained
separately in JSON. Buffered bursts can exceed a sample period, so these means
are not worst-case execution bounds. The recipe uses AVR-GCC 7.3.0, simavr 1.6,
runtime headers, FIFO32/prefill24, two LPC segments, multiplication unroll2 and
neutral ROM gain128. ASM arithmetic/ISR are explicitly selected on supported
targets; Mega C uses C arithmetic/ISR.

[Prototype-v3 evidence](firmware-prototype-v3.md) and its matched brightness
controls remain historical rationale. On that prototype payload, activating
brightness 128 cost approximately 101/33/71.42 foreground cycles/sample on
Tiny ASM/Mega ASM/Mega C. Those costs are not selected-input runtime, and the
selected guarded input differs from the prototype neutral-brightness control.
No prototype control was substituted for the fresh selected simulation.

These fixed public-input simavr measurements establish no physical-board,
arbitrary-stream, higher-rate or new Tiny C support claim. No source waveform,
private identity, input hash or raw log is exported.
