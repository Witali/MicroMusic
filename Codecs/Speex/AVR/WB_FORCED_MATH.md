# Bounded forced-pitch arithmetic in NB3.95/WB5.75

Baseline admission `3bbca078`; isolated primitive `7e89e352`; runtime
`938ef47a`. Target ATmega328P / classic AVR5 / 16 MHz / 2 KB SRAM, GNU ABI,
AVR GCC 7.3.0, explicit ASM, existing mixed Os/O2/O3 with LTO,
mcall-prologues and mrelax. Full matched images enable all lower rates and
NB4. Only submode8 (NB3.95/WB5.75) is connected to these helpers here.

## Exact smaller arithmetic

For signed16 history x and coefficient c in 0..63, factor 128 from both the
product and bias:

```c
(x * (c << 7) + 4096) >> 13 == (x * c + 32) >> 6
```

The signed22 product plus bias fits, and the rounded output fits signed16.
Keep negative floor rounding and ties toward positive infinity. The inline
AVR implementation uses two byte products, forms signed24, adds 32 and
extracts bits6..21 by two left shifts and a word extraction. Its complete
16-instruction body takes 18 cycles. Early-clobber constraints keep outputs
away from inputs; CLR restores r1 while preserving the product carry.

The four-bit coefficient code also permits unsigned16 rather than signed32:

```c
(2185L * (code << 6) + 16384) >> 15
    == (uint16_t)(2185u * code + 256u) >> 9
```

The numerator is at most 33031; signed16 would overflow. Return 0..64, retaining
submode8's existing separate clamp to63. The helper can also serve submode1,
which needs code15 ->64, but **that caller is unchanged at this stage**.

The existing zero-coefficient branch still skips prediction and decodes all
innovation/gain. Short-lag ancestry retains prediction-before-innovation and
all original quantizers. No amplitude threshold, table approximation, packet
change, new buffer, altered synthesis delay or QMF change is introduced.
The explicit C Q6 helper remains callable on AVR. The existing supported-CPU
plus separate ASM-enable selector defaults to C otherwise; hardware memory
access and public interfaces remain independent of arithmetic selection.

## Independent and real-caller checks

The selected AVR scalar primitive passes **4194304** combinations: every
signed16 input and every coefficient 0..63. Another 9856 structured/random
cases per backend compare selected, explicit C, original and independent
wide arithmetic, including negative ties. All sixteen coefficient codes match.
The ASM firmware checks r1 on 4223904 primitive returns and randomized GNU
saved registers on 33696; disabled-ASM C checks 29600 returns and GCC folds
its selected and explicit C wrappers to the same address.

Scalar wrapper timing is 24 cycles / 2 MULs for selected Q6 versus 70..73 / 5
for the original-expression wrapper, which also forms coefficient<<7. The
coefficient wrapper takes 17 / 2 instead of 154 / 5. These are isolated bounds;
production can hoist work, so full-caller gains are measured separately below.
Only isolated C arithmetic executes; the full C decoder is never run or timed.

The mixed APIs each pass 1024 frames, padding/reset and 6144 NB / 7168 WB
rejected calls. They retain all earlier zero-path and one-tap observations.
An external instruction observer locates the exact inline Q6 body in the real
controller, checks its value against the original wide formula, unchanged
input registers, r1, two MULs and 18 cycles. It observes 3148 NB / 3172 WB calls,
6296/6344 MULs and 56664/57096 cycles. Every valid nonzero submode8 frame must
execute exactly `4 * sum(j/pitch, j=0..39)` floored ancestor steps. Rejected
packets, other modes and zero coefficients execute none.

## Complete-image results

Each new image freshly passes 18 streams / 10627 frames, including reset:
**21254 fresh raw frames**, paired with the source/hash-verified parent's
21254 before frames. Each profile has 6467 natural Russian/English frames,
4096 coverage and 64 padding frames. All PCM words match the unchanged oracle.

| Bare decoder | NB3.95 before | NB3.95 bounded | WB5.75 before | WB5.75 bounded |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 92028.369 | 91654.760 | 229683.728 | 229309.671 |
| Decoder CPU at 16 MHz | 28.759% | 28.642% | 71.776% | 71.659% |
| Full-corpus maximum cycles | 104897 | 101934 | 244234 | 241271 |
| Flash | 17488 B | 17400 B | 25762 B | 25674 B |
| Static SRAM | 1108 B | 1108 B | 1289 B | 1289 B |
| Peak stack | 108 B | 108 B | 199 B | 199 B |
| Free SRAM at peak | 832 B | 832 B | 560 B | 560 B |

Means use exact per-frame sums; command intervals include the mailbox but no
startup/reset/interrupts. Speech saves 373.609 NB / 374.057 WB cycles/frame,
0.117 percentage points CPU. Nonzero frames with pitch>=40 save 277..279
cycles; short-lag frames save 409..2963. Zero frames cost five extra cycles
in the complete image, already included in the totals; their arithmetic and
652-MUL producer are unchanged. Both maxima improve 2963 cycles. Bare Flash
shrinks 88 B each, with no static/peak memory increase.

| Continuous output | Frames | Added cycles/frame | Min queue before -> after | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB5.75 ready-RAM IRQ | 10627 | 9600 (3%) | 22 -> 25 | 406 B | 0 |
| NB3.95 scheduled SPI | 4096 | 0 | 74 -> 74 | 667 B | 0 |
| WB5.75 scheduled SPI | 2200 | 0 | 31 -> 33 | 403 B | 0 |

All output retains full recording history and exact s16/PWM with active
timers/interrupts. Ready-RAM IRQ occupies 26110 B Flash / 1430 B static SRAM
and 212 B stack, 96 B smaller. Scheduled SPI occupies 17698/26194 B Flash,
1251/1427 B static SRAM and 130/218 B stack for NB/WB. Output intervals remain
1994..2004 cycles NB and 990..1010 WB. Actual SPI/CS reads 40960/33000 compressed
bytes from 0xff80, crossing 64 KiB through the unchanged shared W25Q128 model:
1359360 exact samples total. SPI adds no foreground stress; ready RAM excludes
transport. No standalone NB ready-RAM IRQ admission is claimed here.

A matched three-stream / 384-frame screen compares coefficient-only, Q6-only
and combined variants. Each is exact and faster; combined is fastest and
smallest. Combined mean savings are 213.000 NB / 230.010 WB cycles on that
specific screen; do not substitute those for full speech results above.
Four minimum images without NB8 (NB8 kbit/s, NB11, WB9.8, WB12.8) remain
byte-identical. No fresh full all-feature timing is claimed for other modes.

NB8-only ASM images pass 384-frame screens, 12674 B NB / 19502 B WB. Their
explicit C images, 13896/22548 B, and full C SPI controls, 21196/31452 B,
compile/link only. C controls shrink 72 B each. The 21-source portable C11
export links without handwritten ASM or duplicate sources. All measurements
are ISA simulation, not physical-board or analog measurements; compact WB
still uses the established Q7/16-tap QMF, not full 64-tap Xiph synthesis.

## Reproduction and remaining work

`reports/forced-math-admission.json` binds sources, reports, scalar/decoder
firmware hashes, screen variants and parent admission. Historical reports
remain intact. Full corpus hashes are rechecked with `--corpus`. Generated
firmware, per-frame traces, PCM, logs and model/link binaries stay ignored.

```sh
python Codecs/Speex/AVR/tests/build_forced_math.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_forced_math.mjs Codecs/Speex/AVR/build/forced-math-unit/asm
node Codecs/Speex/AVR/tests/verify_forced_math.mjs Codecs/Speex/AVR/build/forced-math-unit/c
python Codecs/Speex/AVR/tests/screen_forced_math.py --avr-gcc avr-gcc --node node --corpus <low-corpus> --baseline-root <parent-codec-root> --baseline-images <parent-after-images>
python Codecs/Speex/AVR/tests/build_forced_math_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_forced_math_admission.py --phase before --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat phases after, irq and transport-api. Verified parent before images/traces may be reused.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_forced_math.py --corpus <low-corpus>
```

Further unmeasured candidates: reuse the unclamped coefficient helper in NB1,
inline the sole-caller zero-frame controller, and improve section ownership
for the old shared ASM vector body. None is included in these results. Existing
Xiph algorithm/table BSD provenance remains intact; helper/register/test
adaptations are original project work.
