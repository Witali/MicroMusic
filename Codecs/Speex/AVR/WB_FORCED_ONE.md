# One-tap forced prediction with the original quantizers

Baseline `142df69a` (the exact zero-coefficient stage); runtime `3b056797`. Target ATmega328P,
classic AVR5, 16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0, explicit ASM and the
existing mixed Os/O2/O3, LTO, mcall-prologues and mrelax recipe. Complete
matched images enable all lower profiles and NB4. Submode NB8 means
NB3.95/WB5.75 here, not the default 8 kbit/s NB3 profile.

## Simplify only the adaptive dot product

The generic three-tap kernel receives gains `{0, coefficient, 0}`. Replace
its dot product and rolling window with one signed16 history load and a
signed16-by-unsigned6 product. This needs two AVR byte products rather than
six. Keep the unchanged `speex_nb3_innovation_transform` macro for shape
scaling, pitch clipping, Q14 floors, final rounding and output saturation.
It still uses four byte products for each innovation sample: ten total
products become six. Eighty redundant outer-tap products per twenty-word
row disappear, **640 MULs per nonzero-coefficient frame**.

The adaptive product fits signed22, retained as three AVR bytes until the
original quantizers. The pitch clamp cannot be removed: coefficient 63 and
history -32768 produce -2064384, outside the original -2048000 bound. Keep
both signs of that clamp. Do not round adaptive and innovation separately.

Only the centre history word is read. Direct completed-history blocks now
extend to sample `pitch-1`; short-lag ancestry still recomputes the original
prediction-before-innovation. The ten-word edge no longer needs two neighbors
or a three-byte gain array. Codebook parsing, delays, synthesis, packet formats,
feedback and compact Q7/16-tap QMF are unchanged. The existing exact-zero
fast path remains in use; no amplitude threshold or quiet-speech suppression
is introduced.

The ASM procedure lives in its own section, gated by the NB8 feature. It
reuses source arithmetic macros without a per-sample dispatch or added CALL.
The explicit one-tap C primitive remains available on AVR and other targets.
The existing architecture plus separate ASM-enable selector is unchanged,
as is the independent Flash access backend.

## Arithmetic and memory evidence

An isolated fixture compares new ASM, explicit new C, unchanged generic ASM
and generic C with gains `{0,c,0}`. An independent wide-integer reference
evaluates the original Q14 shape decomposition, both clamps and rounding.
All **44059 cases** match, covering all 640 positions in 32 codebook rows, 49 scales including
all 32 caller scales, all 64 coefficients, counts 0..10, structured history
and clip boundaries, and 8192 random cases. Both positive and negative pitch
clipping execute.

All 88118 monitored ASM returns retain callee-saved registers, argument
registers and r1. Actual LPM addresses and history reads exactly match each
requested range; no output reads or history writes occur. Guards and unused
tails stay unchanged. Count zero accepts null data pointers, touches no data
and takes six cycles. The ten-word new leaf takes 1049..1181 cycles versus
1404..1536, always exactly 355 cycles faster for a matched input. In general
the nonempty leaf saves `32 * count + 35` cycles in every tested case.
Isolated C arithmetic executes; the full C decoder is never executed or timed.

## Complete-image measurements

Fresh after images each pass all 18 streams / 10627 frames, including resets.
Before images/traces match the preceding full admission: **42508 matched raw
frames**, of which 21254 execute freshly after this change. Each profile has
6467 Russian/English speech frames, 4096 coverage and 64 padding frames.
Every PCM word equals the unchanged independent oracle.

| Bare decoder | NB3.95 before | NB3.95 one tap | WB5.75 before | WB5.75 one tap |
| --- | ---: | ---: | ---: | ---: |
| Speech cycles/frame | 96529.805 | 92028.369 | 234202.881 | 229683.728 |
| Decoder CPU at 16 MHz | 30.166% | 28.759% | 73.188% | 71.776% |
| Full-corpus mean cycles | 98429.781 | 93409.422 | 236707.553 | 231675.079 |
| Full-corpus maximum cycles | 112374 | 104897 | 251719 | 244234 |
| Flash | 17266 B | 17488 B | 25538 B | 25762 B |
| Static SRAM | 1108 B | 1108 B | 1289 B | 1289 B |
| Peak stack | 121 B | 108 B | 199 B | 199 B |
| Free SRAM at peak | 819 B | 832 B | 560 B | 560 B |

Speech means use exact per-frame sums, rather than rounded per-recording means.
Intervals include the mailbox, excluding startup, reset and interrupts. Speech
decoding improves 4.66% NB / 1.93% WB relative to the immediately preceding
zero-coefficient optimization. Nonzero frames save 6135..7873 cycles NB and
6139..7881 WB. NB zero frames take exactly the same time. WB zero frames gain
0..12 cycles of overhead: three LPC pair calls cross the linker relaxation
distance and become CALL instead of RCALL, adding three cycles per executed
LPC conversion. Retained layout evidence identifies those calls. The aggregate
and worst-frame results already include this cost. No arithmetic is weakened
to recover it. Flash grows 222/224 B; static SRAM stays fixed. NB peak stack
shrinks 13 B; WB peak stack is governed by another stage and remains fixed.

| Continuous output | Frames | Added cycles/frame | Min queue before -> after | Free SRAM | Underruns |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB5.75 ready-RAM IRQ | 10627 | 9600 (3%) | 14 -> 22 | 406 B | 0 |
| NB3.95 scheduled SPI | 4096 | 0 | 74 -> 74 | 667 B | 0 |
| WB5.75 scheduled SPI | 2200 | 0 | 23 -> 31 | 403 B | 0 |

All runs retain full recording history and exact s16/PWM with active timers
and interrupts. Output intervals remain within 1994..2004 cycles for NB and
990..1010 for WB. IRQ firmware uses 26206 B Flash, 1430 B static SRAM and 212 B
stack. SPI uses 17788/26282 B Flash, 1251/1427 B static SRAM and 130/218 B stack
for NB/WB. Actual SPI/CS reads 40960/33000 bytes starting at 0xff80 and crosses
64 KiB through the unchanged shared W25Q128 model. Total SPI output is 1359360
exact samples, with no added foreground load. Ready RAM excludes transport;
no standalone ready-RAM NB IRQ claim is made here.

Mixed APIs each pass 1024 frames and reset, padding and 6144 NB / 7168 WB
rejected calls. Real decoders execute 3124/3100 new leaf calls across 163/161
nonzero NB8 frames: 26080/25760 samples and exactly 156480/154560 MULs. Each
such frame uses 960 leaf MULs instead of 1600. Other modes, invalid packets
and zero coefficients execute no new leaf. The 42/44 existing zero-path
frames retain eight twenty-word calls, 652 total MULs and no history reads.

Single-feature NB8-only ASM images pass 384-frame screens: 12806 B NB3.95,
19632 B WB5.75. Their C images (13968/22620 B) and full-feature C SPI controls
(21268/31524 B) compile/link only, shrinking 28 B each. The self-contained
21-source portable C11 export also links without assembly or duplicate units.
Four minimum images without NB8 remain byte-identical: NB8 kbit/s, NB11,
WB9.8 and WB12.8. There is no fresh full all-feature other-profile timing claim.

## Reproduction and scope

The parent before images and per-frame traces may be reused only after
checking their firmware/report hashes and the parent's full source admission.
This preserves the already accepted 21254 before raw frames. The normal
builder can instead rebuild the before images and the runner can execute
them again. Per-frame traces remain ignored build artifacts; their paired
aggregate, corpus hashes, reports and source hashes are retained. Generated
firmware, PCM, logs, native link artifacts and model binaries are not committed.

```sh
python Codecs/Speex/AVR/tests/build_forced.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_forced.mjs Codecs/Speex/AVR/build/forced-unit
python Codecs/Speex/AVR/tests/build_forced_admission.py --avr-gcc avr-gcc --baseline-root <parent-codec-root> --low-corpus <low-corpus> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_forced_admission.py --phase before --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat phases after, irq and transport-api.
python Codecs/Speex/AVR/tools/build_wb.py --export-c <new-export-dir> --low-rates 7 --enable-nb4
python Codecs/Speex/AVR/tests/check_refill_c_export.py --clang <windows-clang> --export <new-export-dir>
python Codecs/Speex/AVR/tests/audit_forced.py --corpus <low-corpus>
```

All timing/output measurements use AVR ISA simulation. No physical-board or
analog claim is made. Compact WB output here retains the established Q7/16-tap
QMF and does not claim equivalence to full 64-tap Xiph synthesis. Existing
algorithm/codebook provenance and BSD notices remain intact.

The subsequent [bounded-math stage](WB_FORCED_MATH.md) implements and measures
the exact smaller Q6 ancestry product and unsigned16 coefficient mapping.
Function-section ownership for the old shared vector body remains unmeasured.
