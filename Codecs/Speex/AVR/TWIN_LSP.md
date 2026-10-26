# Paired LSP polynomial stages

The AVR ASM backend now constructs the p and q polynomials through paired
stage-2/3/4 entries. One prologue saves r4..17/Y; r4..7 retain the second
pointer/root while the shared arithmetic body processes p, then q. Direct
calls also remove the old outlined C stage wrappers. Rounding, wrap, all four
LSP interpolation steps, cache decisions and synthesis delays are unchanged.

The existing architecture plus explicit ASM-enable selector remains in force.
`nb3_lsp_pair.h` provides an explicitly callable C pair on AVR too. Disabled
or unsupported ASM uses the previous C call sequence; all four C decoder
images and all 62 existing NB8 C PWM images rebuild byte-identically.
Flash table access and public NB/WB APIs are unchanged.

## Measured result

Baseline `a03dc2ba`, AVR GCC 7.3.0, ATmega328P at 16 MHz / 2 KB SRAM,
`-Os -flto -mcall-prologues -mrelax`, avr8js 0.21.1. Decoder measurements
exclude interrupts; NB means weight rounded per-stream cycle counts, WB
means retain the verifier's exact total. Workload and input/PCM hashes are
bound in `reports/twin-admission.json`.

| ASM profile | Corpus frames | Mean cycles before → after | Mean saved | Max cycles before → after | Flash before → after | Observed stack before → after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NB8 | 9,100 | 102,515.127 → 102,239.323 | 0.2690% | 109,830 → 109,518 | 10,986 → 11,064 B | 103 → 107 B |
| NB11 | 11,587 | 105,113.897 → 104,825.944 | 0.2739% | 112,017 → 111,705 | 13,330 → 13,408 B | 117 → 117 B |
| WB9.8 | 10,563 | 249,924.629 → 249,404.368 | 0.2082% | 257,129 → 256,577 | 17,484 → 17,564 B | 178 → 178 B |
| WB12.8 | 10,563 | 252,436.833 → 251,916.573 | 0.2061% | 258,420 → 257,868 | 20,300 → 20,380 B | 190 → 190 B |

Static SRAM is unchanged. NB8 costs four bytes of observed peak stack; its
PWM player has 699 B free, versus 703 B before. Other profiles' observed
whole-decoder/player peaks remain unchanged. These are corpus measurements,
not a worst-case proof or a physical board test. WB retains the existing
compact 16-tap QMF approximation; full 64-tap Xiph output is not claimed.

The pair primitives take 456/634/812 cycles including external RET and the
internal RCALL, excluding the caller's CALL. Two separate primitives took
476/654/832 cycles. Own saves occupy 16 bytes, with another two bytes during
the internal call. Sharing the prologue through an extra dispatcher saves
Flash but was slower in the archived screening; direct entries were chosen
for the primary speed target. The five old prototypes remain screening
evidence, separate from current admission in `reports/twin-candidates.json`.

## Correctness and output timing

- Direct C and ASM builds each pass 257,790 cases / 2,062,320 result words per
  selected or forced-C path. Both root positions cover every signed16 value;
  signed30 boundaries, aligned p1, random pairs, disjoint adjacent arrays,
  odd addresses and all 256 pointer low bytes are checked against BigInt.
  ASM reads exactly the needed polynomial bytes once and writes only the
  updated words. Guards, callee-saved registers and external r1 are checked.
- A compiled MUL-using Timer2 ISR preempts entry and every instruction
  boundary, including the internal RET: 30,870 injections over 63 vectors.
  All 32 registers, SREG including T, return PC/SP and output match; 11,561
  interrupts occur with nonzero r1. This context proof does not model hardware
  entry latency; the separate full PWM tests exercise timer delivery.
- Whole-converter tests compare real AVR execution with untouched non-LTO
  Xiph: fused/separate geometry and margins, 49,680 bounded interpolation
  calls and 12,288 overlapping LPC outputs. Factoring the common assembler
  source leaves the old single-stage unit binary byte-identical.
- Decoder tests cover 47,735 exact/reset frames across NB8/NB11/WB9.8/WB12.8,
  including pitch, zero-gain, cache transitions and HB LSP coverage. NB matches
  original Xiph; WB matches the independent existing compact-QMF oracle.
- All 134 current ASM PWM images pass with active timers/interrupts: NB8
  31 normal + 31 with 40% extra work; NB11 two + two with 40%; WB9.8 16 + two
  with 5%; WB12.8 48 Flash-sized chunks + two with 5%. No underruns. The 62
  C player images reuse their earlier executed evidence after exact binary
  identity checks; they were rebuilt, not resimulated in this stage.
- Exported C manifest/CMake archives both pass legacy/higher/mixed modes
  through public includes, including invalid-call history and reset checks.

## Reproduce

From `Codecs/Speex/AVR`, with the existing retained corpora and tools on PATH:

```sh
python tools/build_lsp_pair_test.py --avr-gcc avr-gcc
node tests/verify_lsp_pair.mjs
python tools/build_lsp_pair_test.py --avr-gcc avr-gcc --backend c
node tests/verify_lsp_pair.mjs --backend c
python tools/build_lsp_pair_test.py --avr-gcc avr-gcc --irq
node tests/verify_lsp_pair.mjs --irq
python tests/audit_lsp_twin.py --avr-gcc avr-gcc
```

The audit binds sources/reports and optionally rebuilds eight decoders and
four direct-test images, checking their exact executable hashes. It audits
retained simulation evidence; it does not rerun PWM itself. For fresh playback
use `tests/verify_nb_players.py` / `tests/verify_wb_players.py`, with the same
corpora, widths and extra-load settings recorded in the admission report.

`tools/prepare_lsp_twin_candidate.py --candidate production --out <new-dir>`
restores a pinned decoder-only replay tree from the admitted baseline and
source payloads. It keeps the historical five screening choices available.
Earlier `audit_higher.py` is bound to the pre-pair higher-profile admission;
use the current paired audit after this optimization.
