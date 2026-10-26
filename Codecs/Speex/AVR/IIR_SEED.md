# Initialize the IIR accumulator from its first product

The AVR ASM order-8/order-10 filters now save **nine cycles per output sample**
without changing fixed-point arithmetic, coefficient ages, state layout or
the public API. Each 40-sample call saves 360 cycles: NB saves 1,440 cycles
per frame and compact WB saves 2,880. The portable C filters are unchanged
and remain explicitly selectable on AVR with `SPEEX_NB3_ENABLE_ASM=0`.
Architecture matching and the separate ASM opt-in retain their existing rules.

## Three changes in the shared kernel

1. The first tap writes its full signed16×signed16 product to the accumulator.
   Subsequent taps add modulo32 using the original MAC. Four CLR instructions
   and three redundant accumulation instructions disappear: seven cycles per
   sample. Warm and steady phases use the same source macro; the steady phase
   still caches three coefficients. There is no new per-tap call or branch.
2. `MOVW r22,r24` replaces two register copies after rounded extraction:
   one cycle per sample, with identical flags.
3. `COM high; NEG low; SBCI high,255` replaces the four-instruction history
   negation: one cycle per sample. NEG sets C when the original low byte is
   nonzero; the high-byte subtract therefore supplies the exact carry. The
   next cursor comparison establishes the flags used by control flow.

The first product's high and low partial products initialize r25:r24 and
r23:r22 directly. Both signed cross products retain their sign corrections
and carry chains. Rounding remains a single wrapped `sum+4096` before the
arithmetic shift by 13, input addition and clipping to [-32767,32767].
History still receives the negated clipped output twice; warm samples update
one coefficient age at a time. All addressing and memory accesses are unchanged.

`src/iir_kernel.inc` emits both filters. `src/iir_direct.c.inc` and
`src/wb_iir.c` retain their production C equivalents. Hardware-memory access
selection is independent of arithmetic backend selection.

## Measured decoder results

Baseline `c8346cb8`, ATmega328P at 16 MHz / 2 KB SRAM, AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, avr8js 0.21.1. NB means weight rounded
stream means; WB uses exact total cycles. Decoder-only intervals exclude
timer/ISR work. All stream means and extrema fall by the stated constant.

| ASM mode | Frames | Mean cycles before → after | Saved | Max cycles before → after | Flash before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| NB8 | 9,100 | 99,126.806 → 97,686.806 | 1.4527% | 105,990 → 104,550 | 10,638 → 10,602 B |
| NB11 | 11,587 | 101,574.400 → 100,134.400 | 1.4177% | 108,177 → 106,737 | 12,980 → 12,944 B |
| WB9.8 | 10,563 | 243,464.585 → 240,584.585 | 1.1829% | 250,264 → 247,384 | 17,150 → 17,078 B |
| WB12.8 | 10,563 | 245,938.570 → 243,058.570 | 1.1710% | 251,512 → 248,632 | 19,948 → 19,876 B |

Static SRAM and observed whole-decoder peak stack are unchanged. On the same
16 Russian/English excerpts, decoder-only CPU means are 30.97%, 31.60%,
74.98%, 75.73% respectively. First-tap, word-move and negate candidates were
also screened independently; their pinned sources and measurements remain
separate from final admission in `reports/seed-admission.json`.

## Arithmetic and ABI evidence

- Both selected ASM and explicitly compiled production C match independent
  BigInt equations on 7,374 cases / 294,960 samples per path. These include
  both orders, every state-pointer low byte, in-place/separate output,
  arbitrary mirrored signed16 history and coefficients, full-state/guard
  checks and four successive coefficient transitions at each address.
- A zero-coefficient sweep covers all 65,536 signed16 input values per order,
  hence every reachable clipped output and history negation (-32768 input
  clips to -32767). A separate no-ASM binary passes the same cases.
- The existing transposed-reference address sweep passes 16,384 blocks /
  655,360 samples, saving exactly 360 cycles on every one of its 512 rows.
  The broad transposed-reference test passes another 327,680 samples.
- Eight boundary-pattern vectors preempt every executed ASM instruction
  boundary in one heavily interrupted replay per vector: **76,667 IRQs**,
  including **50,983 with nonzero r1**. A real compiled MUL-using ISR restores
  all 32 registers, SREG, return PC/SP; arithmetic and opcode traces remain
  exact. This context test does not model hardware entry latency.
- Full decoder/reset tests retain **47,735 exact frames**. NB matches
  untouched Xiph; WB matches the existing compact normalized 16-tap Q7 QMF
  oracle. Four C bare decoder images and 62 rebuilt C PWM images are identical
  to the preceding stage; earlier C PWM execution evidence is reused.

## Continuous PWM admission

All **198 fresh production ASM PWM images** pass with timers/interrupts
active, exact u8 PCM and zero underruns: NB8 31 normal + 31 load40; NB11
2 normal + 2 load40; WB9.8 16 normal + 2 load5 + 16 load8; WB12.8 48 normal
chunks + 2 load5 chunks + 48 load8 chunks. Loads add 128,000 / 16,000 / 25,600
foreground cycles per 20-ms frame (40% / 5% / 8%), excluding ISR work.

NB8 and NB11 normal/load40 queues are 74/36 samples, with 699/681 B free SRAM.
WB9.8/WB12.8 normal queues are at least 31; load8 queues are 6/4, with 452/430 B
free SRAM. The WB12.8 embedded recordings use independently reset chunks to
fit internal Flash; matching reset oracles are regenerated per chunk.

Two additional RAM-input test images reuse the production ISR/queue and
preserve history across **10,563 full-recording/coverage frames per WB mode**.
Both pass exact s16/PWM and 8% extra foreground work with zero underruns;
minimum queues are 6/5, free SRAM 439/431 B for WB9.8/WB12.8 in this harness.
Input packets are assumed ready; no serial/storage transport delay is modeled.
The harness figures are separate from production-player SRAM measurements.

These are observed simulator/corpus results, not worst-case execution or
physical-board measurements. Extra foreground work does not admit arbitrary
additional ISR workloads. No sample rate, filter approximation or quantization
is changed by this optimization.

## Reproduce

From `Codecs/Speex/AVR`, with the pinned toolchain and retained corpora:

```sh
python tools/build_iir_block_test.py --avr-gcc avr-gcc
node tests/verify_iir_block.mjs --firmware build/seed-iir-asm
python tools/build_iir_block_test.py --avr-gcc avr-gcc --backend c
node tests/verify_iir_block.mjs --firmware build/seed-iir-c
python tools/build_iir_block_test.py --avr-gcc avr-gcc --irq
node tests/verify_iir_block.mjs --firmware build/seed-iir-irq
python tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 32 --out build/seed-stream-wb128
node tests/verify_wb_stream.mjs --firmware build/seed-stream-wb128
python tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 25 --out build/seed-stream-wb98
node tests/verify_wb_stream.mjs --firmware build/seed-stream-wb98 --streams build/wb-corpus/streams --oracle build/wb-corpus/oracle
python tests/audit_iir_seed.py --avr-gcc avr-gcc
```

The audit binds sources, retained reports, inputs and executable hashes;
`--avr-gcc` rebuilds eight decoder, three direct-test, two streaming-test and
one legacy IIR image. It does not rerun PWM. Fresh production PWM uses the
existing NB/WB player matrix tools with separate output folders and the loads
recorded in admission; the preceding RAM-input commands execute full histories.

`tools/prepare_iir_seed_candidate.py --candidate production --out <new-dir>`
restores the pinned decoder-only tree. `baseline`, `first`, `move`, `negate`
restore isolated comparisons. Earlier source-bound audits describe their
recorded revisions; current sources use `tests/audit_iir_seed.py`.
Independently restored NB8/WB12.8 binaries match the tested images exactly.
