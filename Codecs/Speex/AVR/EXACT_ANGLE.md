# Exact AVR LSP cosine leaf

Historical stage: current sources also include the [IIR first-product and
word-operation optimization](IIR_SEED.md). Its source-bound audit is now
`tests/audit_iir_seed.py`; the measurements below describe the cosine stage.

The primary ASM backend now evaluates the original Xiph 1.2.1 fixed-point
`ANGLE2X` polynomial in a leaf function with no own stack or explicit data
memory accesses. It preserves the original approximation, every rounded
P13 operation, signed16 cast and final word shift. This is bit-exact to the
upstream integer calculation, not a different approximation to cosine.
The selected architecture must support the existing GNU AVR/MUL backend,
and `SPEEX_NB3_ENABLE_ASM=1` must explicitly enable it.

`nb3_lsp_angle.h` keeps an explicitly selectable C implementation on AVR too.
Default/unsupported ASM continues using the old production C sequence. All
four C decoder images and all 62 NB8 C PWM images rebuild byte-identically;
the portable manifest/CMake archives retain exact output and public APIs.
Flash-memory access remains independent of arithmetic backend selection.

## Arithmetic and ABI

For `P13(a,b)=floor((a*b+4096)/8192)`, the function folds the reflected half,
then evaluates the same steps as Xiph:

```text
y = signed16(P13(x,x))
a = 340 + P13(-10,y)       # 300..380 for every signed16 y
b = -4096 + P13(y,a)
r = 8192 + P13(y,b)
return signed16((reflected ? -r : r) * 4)
```

The square uses three MUL operations, doubling the signed cross term in
17 bits. The positive nine-bit `a` has high byte 1, so the next product needs
two MULs plus a signed `y<<8`. Integral offsets enter the preceding rounding
bias. The final extraction explicitly clears the two bits discarded by P13;
simply shifting by 11 would change output. All intermediates fit signed32.

Input/result use r25:r24; only call-clobbered registers are modified. MULSU
operands remain in r16..23, as required by the
[Microchip instruction manual, DS40002198C (2024), section 6.79](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/ReferenceManuals/AVR-InstructionSet-Manual-DS40002198.pdf#page=92).
T holds the reflected-half flag and r1 may contain a private MUL result.
No C calls occur inside the leaf; r1 is zero before its external RET.
Interrupt handlers must preserve interrupted r1 and SREG/T, as in the normal
GNU AVR ABI. Arithmetic introduces no hardware IO or interrupt masking.

The paired-stage private entry layout also changes: stages 2/3 jump into the
shared tail, and stage 4 falls through. Its primitive timings become
460/634/804 cycles, versus 456/634/812 before. On the screening subset it
saves about 12 NB cycles/frame, with no linked Flash reduction; the cosine
leaf accounts for most of the final gain. Both changes have separate commits.

## Measurements

Baseline `05b1e70a`, ATmega328P at 16 MHz / 2 KB SRAM, AVR GCC 7.3.0 with
`-Os -flto -mcall-prologues -mrelax`, avr8js 0.21.1. Decoder-only intervals
exclude timer/ISR work. NB means weight rounded per-stream counts; WB means
use the exact total from the verifier. Source, corpus and binary hashes are
bound in `reports/angle-admission.json`.

| ASM profile | Frames | Mean cycles before → after | Saved | Max cycles before → after | Flash before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| NB8 | 9,100 | 102,239.323 → 99,126.806 | 3.0443% | 109,518 → 105,990 | 11,064 → 10,638 B |
| NB11 | 11,587 | 104,825.944 → 101,574.400 | 3.1019% | 111,705 → 108,177 | 13,408 → 12,980 B |
| WB9.8 | 10,563 | 249,404.368 → 243,464.585 | 2.3816% | 256,577 → 250,264 | 17,564 → 17,150 B |
| WB12.8 | 10,563 | 251,916.573 → 245,938.570 | 2.3730% | 257,868 → 251,512 | 20,380 → 19,948 B |

Static SRAM and observed whole-decoder/player peak stack are unchanged. A
stackless scalar does not remove the peak caused by other decoder stages.
The leaf takes 123 cycles for inputs below 12868 and 131 otherwise, including
RET/excluding CALL. Its full signed16 domain includes wrapping edge cases.

The initial profile measured 1,456 frames, at most the first 48 of each of
31 retained NB streams. `lsp_angle` consumed 6.612% of those intervals.
Isolated cosine/layout screening and pinned source payloads are retained
separately from the full-corpus admission; they are not broad timing claims.

## Correctness and continuous output

- Separate C and ASM unit builds each check all 65,536 signed16 inputs against
  untouched non-LTO Xiph and an independent BigInt model. Each build invokes
  selected, forced-C and upstream implementations: 196,608 calls. ABI, r1,
  input preservation, initial T states and explicit RAM accesses are checked.
- A compiled MUL-using ISR preempts every instruction boundary on 14 boundary
  vectors: 1,533 IRQs, including 737 with nonzero r1. All 32 registers, SREG,
  return PC/SP and outputs match. This context proof does not model hardware
  entry latency; separate PWM tests exercise timer delivery.
- The new paired layout passes 257,790 cases / 2,062,320 result words per
  selected/forced-C path, plus 30,828 instruction-boundary IRQ injections.
- Whole LSP→LPC tests pass fused/separate geometry, 49,680 bounded calls,
  4,096 generic inputs and 12,288 overlapping outputs against untouched Xiph.
  Decoder tests pass 47,735 exact/reset frames across all four profiles.
- All **198 fresh ASM PWM images** pass with active timers/interrupts: the
  previous 134 normal/load40/load5 cases, plus WB9.8's 16 recordings and
  WB12.8's 48 chunks with **25,600 extra foreground cycles/frame (8% CPU)**.
  Each WB load8 set covers 6,467 frames / 2,069,440 samples, with zero underruns.
  Minimum queues are 5/3 samples, free SRAM 452/430 B for WB9.8/WB12.8.
- Two additional RAM-input test images reuse the production ISR/queue and
  run all 17 complete streams per WB mode, including 4,096 consecutive HB
  coverage frames. Each mode passes **10,563 frames without resets inside a
  recording**, exact s16/PWM, active interrupts and 8% extra foreground work.
  Minimum queues are 5/4 samples, free SRAM 439/431 B for WB9.8/WB12.8.
  These are separate harness measurements, not production-player SRAM figures;
  ready input packets are supplied by the simulator without transport latency.
- NB8's normal/load40 queues are 74/36, free SRAM 699 B; NB11's are 74/35,
  free SRAM 681 B. The 62 byte-identical C PWM images reuse earlier executed
  evidence after rebuilding; they were not resimulated in this stage.
- Host C tests cover all inputs with default selection, unavailable ASM and
  unknown architecture. Manifest and CMake archives both pass legacy, higher
  and mixed modes through public includes, including rejection/reset checks.

These are simulator/corpus results, not a worst-case execution proof or board
measurement. Extra work is a foreground delay before each frame, not an
arbitrary interrupt workload. WB keeps the existing normalized 16-tap Q7 QMF;
PCM matches the independent compact-profile oracle, not full 64-tap Xiph.
NB PCM remains bit-identical to unmodified Xiph. No transport is added.

## Reproduce

From `Codecs/Speex/AVR`, with retained corpora and pinned tools prepared:

```sh
python tools/build_lsp_angle_test.py --avr-gcc avr-gcc
node tests/verify_lsp_angle.mjs
python tools/build_lsp_angle_test.py --avr-gcc avr-gcc --backend c
node tests/verify_lsp_angle.mjs --backend c
python tools/build_lsp_angle_test.py --avr-gcc avr-gcc --irq
node tests/verify_lsp_angle.mjs --irq
python tools/build_lsp_angle_test.py --cc clang --out build/angle-host-check
python tests/audit_lsp_angle.py --avr-gcc avr-gcc
```

The audit checks retained evidence and optionally rebuilds eight decoder,
three scalar, two paired-stage and two streaming-test images. It does not rerun PWM. For a fresh
WB load8 run use `tests/verify_wb_players.py --frame-load-cycles 25600` with
the WB9.8 speech corpus or the WB12.8 reset-chunk corpus and matching oracles.
Use separate output/source trees for concurrent builds.

For continuous history across full WB recordings, use the RAM-input test
application. It includes the production player's timer ISR, queue, output
conversion and marked extra-work function. The host supplies a ready packet;
SPI/UART timing and external input latency are outside this test:

```sh
python tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 32 --out build/angle-wb-stream-32
node tests/verify_wb_stream.mjs --firmware build/angle-wb-stream-32
python tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 25 --out build/angle-wb-stream-25
node tests/verify_wb_stream.mjs --firmware build/angle-wb-stream-25 --streams build/wb-corpus/streams --oracle build/wb-corpus/oracle
```

The default test load is 25,600 foreground cycles/frame; production sources
are unchanged by this harness. These two test images are separate from the
198 production PWM images. Their reports are `reports/angle-stream-wb98.json`
and `reports/angle-stream-wb128.json`.

`tools/prepare_lsp_angle_candidate.py --candidate production --out <new-dir>`
restores a pinned decoder-only tree. `baseline`, `layout` and `cosine` restore
the earlier screening variants. Independently restored NB8 and WB12.8 images
match current binaries. Earlier audits are historical stage gates; the current
gate is `tests/audit_lsp_angle.py`.
