# Prepared-context dispatch beside the NB1 ASM prologue

Baseline `0e8776be`; runtime `4bc887c5`. Target ATmega328P / classic AVR5, 16 MHz / 2 KB SRAM,
GNU ABI, AVR GCC 7.3.0 with existing mixed Os/O2/O3, LTO, mcall-prologues and
mrelax. Full images enable all lower rates and NB4. Only compact WB3.95 changes.

## Move selection, retain both synthesis bodies

The C controller previously tested the prepared context, selected a function
and arranged its arguments. It now calls a prepared-context entry with the same
four-pointer ABI. ASM reads previous[0], then branches directly into the existing
general or zero entry. There is no nested call, extra return address, new mean
kernel, buffer or state flag. The unrestricted general entry remains available.

The final displacement load reuses ZH after reading through Z. The original
context pointer remains in r20:r21; common setup reloads Z before any subsequent
memory read. Only caller-clobbered r0/Z are changed. r1 and all arguments remain
intact. This is LDD without pointer auto-update, not an undefined LD Z+ alias.
See the [cookbook and pinned ISA reference](../../../docs/avr-asm-cookbook/speex-prepared-dispatch.md).

Equivalent C selection is explicitly available through the ordinary architecture
and ASM-enable settings. It calls the unchanged C general/zero primitives.
Both C firmware controls remain byte-identical. Hardware memory selection,
public APIs, quantizers, RNG, pulse/mean/phase state and compact QMF are unchanged.

## Measured results

| Fully enabled bare WB3.95 | Before | After |
| --- | ---: | ---: |
| Natural-speech cycles/frame | 221510.204 | 221455.758 |
| Decoder CPU at 16 MHz | 69.222% | 69.205% |
| Full-corpus maximum cycles | 225533 | 225481 |
| Flash | 25912 B | 25894 B |
| Static SRAM | 1284 B | 1284 B |
| Peak stack | 200 B | 200 B |
| Free SRAM at peak | 564 B | 564 B |

Every frame in the complete 18-stream / 10627-frame corpus is faster: exactly
60 cycles for zero contexts, 52 for ordinary contexts. Natural Russian/English
speech covers 6467 frames, 1977 zero contexts; mean saving is 54.446 cycles/frame.
All PCM words and resets match the unchanged oracle. Before reports/images and
raw traces are reused from the source/hash-verified parent; after is fresh.
Timing excludes startup/reset/interrupts. Flash shrinks 18 B with unchanged RAM.

Fresh full-history WB IRQ runs each cover 10627 frames at +8%/+11% extra work,
with exact s16/PWM and no underruns. Images use 26330 B Flash / 1425 B static
SRAM, leave 410 B free and retain minimum queues 30/22. Ready RAM excludes
transport latency. Actual SPI/CS reads 36000 bytes from 0xff80 across 64 KiB:
3600 frames / 1152000 exact samples, no underruns and minimum queue 30. The SPI
image uses 26414 B Flash / 1422 B static SRAM / 219 B peak stack / 407 B free;
intervals 995..1005 cycles. SPI adds no foreground stress. Model/driver are unchanged.

Isolated ASM-enable 1/0 fixtures each check 98791 vectors: 33256 zero contexts and
65535 ordinary contexts. They cover all 65536 selector words, every signed16
current-table word, all 18432 pitch/phase pairs and incoming-state overflow edges.
General/zero/selected C and ASM outputs/cursors match the original BigInt model;
inputs and guards stay intact. The prepared entry branches to the correct body
at the same stack depth. Across fixtures, 362885 ASM returns check saved registers
and r1. The prepared path retains 160 MULs/forty samples and reads exactly two
selector bytes in addition to its chosen body. Only isolated C vectors execute.

Fresh before/after mixed APIs retain 1024 frames each, 6144/7168 rejected calls,
padding/reset, exact PCM and identical arithmetic/lookup counters. Independent
state checking retains 820 quarters, all partial states/seed/guards and four
injected nonzero-prior-pulse cases. Eight NB/no-NB1 control images remain
byte-identical. NB1-only WB ASM passes 384 frames (20158 B). The C feature 21606 B
and full C SPI 31696 B images are byte-identical; the portable 21-source C11
export compiles/links without handwritten ASM. Full C decoders never execute.
All runtime evidence is ISA simulation, not physical-board or analog measurement.

## Reproduce and continue

`reports/prepared-admission.json` binds 204 sources, parent admission and retained
reports/firmware hashes. Generated firmware, traces, PCM and logs remain ignored.
The shared timing helper also reproduces the complete parent's timing report.

```sh
python Codecs/Speex/AVR/tests/build_nb1_zero_vocoder.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_nb1_zero_vocoder.mjs <unit-asm-dir>
node Codecs/Speex/AVR/tests/verify_nb1_zero_vocoder.mjs <unit-c-dir>
python Codecs/Speex/AVR/tests/build_prepared_dispatch.py --avr-gcc avr-gcc --clang <windows-clang> --baseline-root <parent-codec-root> --spi-corpus <spi-corpus>
python Codecs/Speex/AVR/tests/run_prepared_dispatch.py --phase raw --node node --low-corpus <low-corpus> --mixed-corpus <low-mixed> --spi-corpus <spi-corpus> --spi-model <model.wasm>
# Repeat irq8, irq11 and transport-api.
python Codecs/Speex/AVR/tests/audit_prepared_dispatch.py --corpus <low-corpus>
```

Unmeasured candidates remain: finite pitch-root lookup, complementary pulse/
feedback coefficients and paired opposite-noise prefold. None is admitted here.
Retain pinned Xiph Speex 1.2.1 BSD provenance; dispatch and proof are project work.
