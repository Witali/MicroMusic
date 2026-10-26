# Grouped IIR and phase-specific coefficient caches

The AVR ASM backend now saves **247 cycles per order-10 IIR call** and
**238 per order-8 call**, each producing 40 samples. NB saves 988 cycles per
frame before the additional one-cycle saving on every reflected cosine call;
compact WB saves 1,940. The production C filters and public APIs are unchanged.
ASM still requires a matching real architecture/ABI and explicit opt-in.

## Register lifetimes and shared groups

- Warm-up processes exactly `order` samples. Reset Y once afterwards, using
  its retained base, rather than testing its low byte after every sample.
- Steady processing uses a private subroutine for exactly `order` samples,
  followed by one Y rewind. Three calls finish NB's remaining 30 samples;
  four finish HB's remaining 32. The dot-product body is emitted once.
- Immediate SUBI/SBCI rounding preserves wrapped `sum+4096` and frees r3
  for the sample count. Removing the cursor-end test frees r16:r17. Four
  coefficients now fit in registers; put the first in r16:r17 so MULSU can
  read it directly. The other cached pairs still use MOVW into r18:r19.
- During warm-up, that same r16:r17 pair holds the **last old coefficient**.
  It changes only after its final warm use. Two initial LDDs replace repeated
  loads on all warm outputs; the steady preload then replaces it with the
  first new coefficient. This saves another 36/28 cycles per call, with no
  extra Flash, static memory or stack versus the grouped prototype.

Both signed cross-product corrections, modulo32 sums, P13 rounding, clipping
and coefficient-age updates remain exact. X keeps its fixed rewind; state
layout is still `6*order` bytes. The architecture-specific arithmetic does
not change hardware-memory selection or timer configuration.

The separate cosine change uses `COM high; NEG low; SBCI high,255`. It takes
123/130 cycles including RET, versus 123/131 before, with identical size.
Every signed16 input matches untouched Xiph and independent BigInt.

## ABI and memory tradeoff

The IIR entry still saves 18 register bytes. A private RCALL adds **two
temporary stack bytes** on ATmega328P: 20 own bytes at peak. Private RET may
leave r1 dirty; only assembly follows, and the external return clears r1.
Compiled interrupt handlers must preserve interrupted r1 and SREG, including T.

Observed bare-decoder peaks remain 107/117 B for NB8/NB11; WB9.8/WB12.8 grow
178→180 and 190→192 B. Static SRAM is unchanged. Their bare harnesses retain
589/569 B free SRAM. These target-specific observations do not establish the
return-address width, stack budget or timing of other AVR families.
`SPEEX_NB3_ENABLE_ASM=0` still selects C on this same AVR.

## Full decoder measurements

Baseline `f80752a2`, ATmega328P 16 MHz / 2 KB SRAM, AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, avr8js 0.21.1. NB means weight rounded
stream means; WB uses exact totals. Decoder-only intervals exclude ISR/output.

| ASM mode | Frames | Mean cycles before → after | Saved | Maximum cycles before → after | Flash before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| NB8 | 9,100 | 97,686.806 → 96,682.821 | 1.0278% | 104,550 → 103,546 | 10,602 → 10,598 B |
| NB11 | 11,587 | 100,134.400 → 99,129.839 | 1.0032% | 106,737 → 105,733 | 12,944 → 12,940 B |
| WB9.8 | 10,563 | 240,584.585 → 238,611.592 | 0.8201% | 247,384 → 245,412 | 17,078 → 17,072 B |
| WB12.8 | 10,563 | 243,058.570 → 241,085.577 | 0.8117% | 248,632 → 246,660 | 19,876 → 19,870 B |

On the retained 16 Russian/English clips, CPU means are **30.65%, 31.29%,
74.37%, 75.11%** respectively. The original byte-identical C decoder images
and 62 rebuilt C player images retain their earlier C PWM execution evidence.

## Correctness evidence

- Both IIR orders match explicitly compiled production C and independent
  BigInt on 7,374 cases / 294,960 samples per path: all state low bytes,
  in-place/separate output, arbitrary mirrored histories, four coefficient
  transitions per address, every signed16 input through a zero-coefficient
  filter, and complete work-arena/state/guard checks.
- The transposed-reference tests pass 655,360 address-sweep and 327,680 broad
  samples. Each of the 512 NB sweep rows saves exactly 247 cycles per call.
- Eight full IIR traces receive **75,479 instruction-boundary IRQs**, including
  **50,102 with nonzero r1**. All 32 registers, SREG and return PC/SP are
  restored. Normal direct tests observe 25,809 private CALL/RET pairs; the IRQ
  test includes 56, with dirty-r1 private returns. External ABI checks remain
  intact. This context test does not model hardware entry latency.
- Cosine checks cover all 65,536 signed16 inputs against C/original Xiph and
  BigInt, plus 1,533 IRQ boundaries, including 737 with nonzero r1.
- All **47,735 decoder/reset frames** remain exact. NB matches untouched
  Xiph; WB matches the existing compact normalized 16-tap Q7 QMF oracle.

The final sources pass **198 production PWM images** with timers and interrupts
active, exact PWM output and zero underruns. NB8/NB11 retain minimum queues
74/74 normally and 36/36 with 40% extra foreground work; free SRAM is 699/681 B.
WB9.8/WB12.8 retain queues 32/31 normally, 18/16 with 5% extra work and 6/5
with 8%; free SRAM is 450/428 B. The loaded WB speech runs cover 6,467 frames
per mode; WB12.8 Flash demos reset between chunks of at most 192 frames.

Two RAM-input images separately pass all 17 full streams / 10,563 frames per
WB mode without chunk resets, with exact s16/PWM, active interrupts and 8%
extra foreground work. Minimum queues are 6/5 and free SRAM 437/429 B. This
harness assumes ready input packets; it does not model a storage/serial
transport. These are simulator measurements, not physical board tests or a
guarantee for arbitrary additional interrupt work. The compact QMF profile
is unchanged; no new audio approximation was introduced.

## Reproduce

From `Codecs/Speex/AVR`, with the retained corpora and pinned tools:

```sh
python tools/build_iir_block_test.py --avr-gcc avr-gcc --out build/group-check
node tests/verify_iir_block.mjs --firmware build/group-check
python tools/build_iir_block_test.py --avr-gcc avr-gcc --irq --out build/group-irq-check
node tests/verify_iir_block.mjs --firmware build/group-irq-check
python tools/build_lsp_angle_test.py --avr-gcc avr-gcc --out build/group-angle-check
node tests/verify_lsp_angle.mjs --firmware build/group-angle-check
python tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 32 --out build/group-stream-wb128
node tests/verify_wb_stream.mjs --firmware build/group-stream-wb128
python tests/audit_iir_groups.py --avr-gcc avr-gcc
```

Use `--backend c` for explicitly disabled ASM. The audit binds current sources,
reports, corpus and executable hashes, and optionally rebuilds 17 images:
eight decoders, six IIR/cosine direct tests, two RAM-input PWM tests and one
legacy IIR mailbox. Rebuilds verify identity; they do not rerun PWM.

`tools/prepare_iir_groups.py --candidate production --out <new-dir>` restores
a pinned decoder-only tree. Other choices retain warm-only, three/four-cache,
direct-register, cosine-only and grouped-before-warm-cache comparisons.
Earlier source-bound gates describe their recorded revisions; current sources
use `tests/audit_iir_groups.py`.
