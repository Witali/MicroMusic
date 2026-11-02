# Exact zero-context NB1 quarter synthesis

Baseline `2e47ed00`; runtime `943f37bd`. Target ATmega328P / classic AVR5, 16 MHz / 2 KB SRAM,
GNU ABI, AVR GCC 7.3.0, existing mixed Os/O2/O3 with LTO, mcall-prologues and
mrelax. Full images enable all lower rates and NB4. This stage changes compact
WB3.95 only; the standalone NB2.15 image remains byte-identical.

## Preserve the original recurrence

For a prepared NB1 context, `previous[0]==0` proves that all five previous-noise
coefficients and both new pulse values are zero. If gain>0, a negative first
raw-noise word makes its Q15 previous value strictly negative. A zero first word
requires scale<=4096; then the entire previous array and pulse amplitude vanish.
Gain0 makes these terms zero at every scale. This is a prepared-context contract,
not a predicate for arbitrary caller-supplied tables.

An independent integer proof covers 945344 negative-noise/gain pairs and
262208 small-scale/gain pairs. The actual 32 pinned packet scales start at
16384, so a positive-gain zero context cannot arise from a current packet.
The broader small-scale case is an arithmetic proof, not an invented packet test.

The zero primitive still processes all forty samples. Sample0 uses the original
incoming pulse-minus-noise, with exact word wrap; later samples use current
noise only. Preserve the exact mean recurrence, phase/pitch progression and
last class. Return both cursor pulse/noise fields as zero. No noise generation,
RNG transition, high-band quantizer, filter, delay or QMF is removed or changed.
There is no new amplitude threshold or silence detection.

The general primitive retains arbitrary-table behavior. A separate zero entry
shares its ASM prologue and epilogue; a short-lived T bit selects the body through
flag-neutral setup, before arithmetic starts. Normal compiled IRQs preserve
SREG. The original mean macro remains shared source; no per-sample call overhead
is added. Both functions preserve GNU saved registers/r1 and leave IRQs enabled.
The zero primitive has equivalent C and ordinary architecture-plus-explicit-ASM
selection. No new buffer, context field or RAM flag is allocated.

## Primitive and complete-image evidence

Each ASM-enable1/0 isolated fixture runs five paths on 33255 vectors: general
ASM/C, zero ASM/C and selected zero. Tests cover every signed16 current-table
word, all 18432 pitch/phase pairs and incoming pulse/noise/mean overflow edges.
Every output word/cursor matches the original two-product BigInt recurrence;
inputs and guards are unchanged. There are 166275 checked ASM saved-register/r1
returns across the fixtures. Explicit ASM-disable selects C on AVR itself.
Only these isolated C primitives execute, never the full C decoder.

Zero ASM takes 2660..2745 cycles per forty samples, 517..526 fewer than the
matched general entry. It removes 80 previous-table bytes and four pulse bytes
read per call: 336 bytes/frame. Both paths retain 160 hardware MULs per call for
the exact mean. The existing arbitrary-context fixture also passes all 31540
cases, with original C/ASM output, ABI and bounds intact.

| Fully enabled bare WB3.95 | Before | After |
| --- | ---: | ---: |
| Natural-speech cycles/frame | 222041.839 | 221510.204 |
| Decoder CPU at 16 MHz | 69.388% | 69.222% |
| Full-corpus maximum cycles | 225433 | 225533 |
| Flash | 25724 B | 25912 B |
| Static SRAM | 1284 B | 1284 B |
| Peak stack | 200 B | 200 B |
| Free SRAM at peak | 564 B | 564 B |

Fresh raw verification covers all 18 streams /10627 frames, including reset:
6467 natural Russian/English, 4096 coverage and 64 padding frames. Every PCM
word matches the unchanged oracle. Before raw traces/reports/images are reused
from the source/hash-verified parent. Natural speech has 1977 zero-context
frames. Zero frames save 1959..1986 cycles; ordinary frames cost exactly 100
extra cycles, already included in the means and the 100-cycle maximum increase.
Average saving is 531.635 cycles/frame, 0.166 percentage points CPU, for 188 B
Flash and unchanged static/peak RAM. Intervals exclude reset/startup/IRQ.

Fresh +8%/+11% ready-RAM IRQ runs each cover 10627 full-history frames with exact
s16/PWM and zero underruns. Flash 26348 B, static SRAM 1425 B, free 410 B and minimum
queues 30/22 retain the previous margins. Ready RAM excludes transport latency.
Actual SPI/CS reads 36000 bytes from 0xff80 across 64 KiB through the unchanged
shared W25Q128 model: 3600 frames / 1152000 exact samples, no underruns, minimum
queue 30. SPI Flash 26432 B, static SRAM 1422 B, peak stack 219 B, free 407 B;
timer intervals 994..1005 cycles. SPI adds no extra foreground stress.

Fresh before/after mixed APIs each pass 1024 frames, padding/reset and 6144/7168
rejected calls. The new images select 196 zero and 628 general quarters per API;
each call retains 160 MULs and rejected calls execute neither path. Preparation,
gain lookup, RNG and folding observations remain exact. The independent state
fixture checks 820 quarters, 624 general/196 zero, all partial states, seed,
workspace and guards. Four injected nonzero-prior-pulse cases cover codes 0..3
absent from natural transition input; their excitation/state/fold are checked
independently, without claiming a PCM oracle for injected states.

Eight rebuilt controls remain byte-identical: standalone NB2.15 and its SPI
player, plus NB8/NB11/WB9.8/WB12.8/NB3.95/WB5.75 images with NB1 disabled.
There is no fresh full all-feature timing claim for other modes. NB1-only WB
ASM passes 384 frames (20176 B). Its C control 21606 B, full C SPI 31696 B and the
portable 21-source C11 export compile/link only. All runtime evidence is ISA
simulation, not physical-board or analog measurement. Compact QMF is unchanged.

## Reproduce and continue

`reports/zero-synthesis-admission.json` binds 201 sources, parent admission,
reports and firmware hashes. Old reports remain unchanged. Generated binaries,
traces, PCM, logs and model artifacts remain ignored.

```sh
python Codecs/Speex/AVR/tests/verify_nb1_zero_context.py
python Codecs/Speex/AVR/tests/build_nb1_vocoder.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_vocoder.mjs <generic-unit-dir>
python Codecs/Speex/AVR/tests/build_nb1_zero_vocoder.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_zero_vocoder.mjs <zero-unit-asm-dir>
node Codecs/Speex/AVR/tests/verify_nb1_zero_vocoder.mjs <zero-unit-c-dir>
python Codecs/Speex/AVR/tests/build_nb1_zero_synthesis.py --avr-gcc avr-gcc --clang <windows-clang> --baseline-root <parent-codec-root> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_nb1_zero_synthesis.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat irq8, irq11 and transport-api.
python Codecs/Speex/AVR/tests/audit_nb1_zero_synthesis.py --corpus <low-corpus>
```

Remaining unmeasured candidates include moving prepared-context dispatch into
ASM, complementary pulse/feedback coefficients, finite pitch-root lookup and
paired opposite-noise prefold. This stage admits none of them. Retain pinned
Xiph Speex 1.2.1 BSD provenance; specialization and proof are project work.
