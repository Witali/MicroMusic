# LPX speech: bitrate is not decoder cost

Measured prototype on ATmega328P (AVR5, 16 MHz), AVR-GCC 7.3.0 `-Os`,
existing explicit ASM backend, local O2 tuning 7, unroll9, 8 kHz PWM,
queue512/prefill384, v3 mask24 and the additional speech parser enabled.
AVR-LibC supplies device registers and interrupt vectors. No new register
definitions or handwritten assembly were introduced by this experiment.

The speech format stores one scalar spectrum per 40 ms, energy/pitch per
20 ms and one innovation pulse per 2.5 ms. The encoder searches on the PC;
the MCU shares the existing ten-pole integer synthesis, pitch ring, sparse
excitation and PWM arithmetic. Five-bit LSF at 4k and six-bit LSF at 6k change
quality and bits, while both routes retain essentially the same sample work.
The 4k position mapping also costs instructions. Keep data-dependent route
costs in mind when comparing different encodings of the same source.

Across four common 4-second speech clips, mean decode **wall** cost is
948.921 cycles/sample at 4k and 948.226 at 6k, including active IRQ and
instrumentation. Lower bitrate is slightly slower on this workload; neither
the nominal bitrate nor fewer bit reads establishes a CPU improvement.
The same firmware needs 8334 Flash bytes excluding the encoded stream,
1104 static SRAM bytes including the 512-byte queue and harness, and a
123-byte observed stack high-water after `profile_ready`. The observed
minimum free stack margin is 821 bytes. These are complete-firmware numbers,
not the isolated library footprint or a proof of worst-case stack usage.

Continuous 8-second controls (state is not reset halfway):

| Profile/backend | Mean wall cycles/sample | Underruns |
|---|---:|---:|
| 4k explicit AVR ASM | 950.041 | 0 |
| 4k ASM, extra100 IRQ cycles | 965.427 | 0 |
| 4k C fallback | 2761.175 | 27007 |
| 6k explicit AVR ASM | 951.320 | 0 |
| 6k ASM, extra100 IRQ cycles | 967.327 | 0 |
| 6k C fallback | 2765.653 | 27145 |

All useful PWM bytes equal native C output, including underrunning controls;
underruns are separately observed inserted silence ticks. C fallback is
arithmetically equivalent but does **not** support uninterrupted 8 kHz output
at 16 MHz with these settings. ISR and queue overhead are included in the
observed behavior. ASM controls fit the 2000-cycle audio tick budget with
the measured queue, not a per-call maximum deadline (frame setup can exceed
one tick). Normal output intervals span 1985..2009 cycles on these clips.

The final legacy LPX8 comparison, under the same speech-enabled binary,
averages 810.249 cycles/sample on the same four references. Its heaviest
continuous 8-second control is 855.535 cycles/sample (extra100 IRQ: 863.573),
zero underruns. C fallback costs 2572.889 and underruns 21007 times.
Enabling the parser on those same legacy streams costs 808 Flash bytes,
2 static SRAM bytes and 3.52..6.36 decode wall cycles/sample. This control
separates feature overhead from the different encoded audio parameters.

`LPX4_ENABLE_SPEECH=1` enables v4 parsing independently of arithmetic.
`LPX4_ENABLE_ASM=1` still selects ASM only with a matching real AVR5 target;
without it the C backend remains explicitly available even on AVR. Flash
access remains selected by the platform, not by the arithmetic flag.
Do not remove the C route to make a performance claim.

Old v2/v3 streams remain compatible: fresh complete AVR runs over all 91
frozen streams/2,912,000 samples give the same 2,495,466,530 total decode wall
cycles as round19, exact PCM/PWM and zero underruns with speech disabled.
Fresh native decoding with speech enabled also preserves all golden bytes.

This is simulator evidence for these recorded workloads, not a board result
or a music quality claim. The 40 ms packet trades spectral resolution and
latency for storage. No output quality equality with the source is claimed.
The implementation is original project code using the existing arithmetic;
no external codec/codebook implementation was adapted.

See [format and encoder](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/SPEECH_V4.md),
[plan](../../Codecs/LPX/SPEECH_4_6_8_PLAN_RU.md) and the compact measured report
under `Codecs/LPX/research/speech-4-6-8-2026-10-26/`.
