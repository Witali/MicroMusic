# Private fixed-register helpers can reduce a repeated ASM block

Measured on ATmega328P / classic AVR5, GNU AVR ABI, AVR GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax -fwrapv -fno-strict-aliasing`,
avr8js 0.21.1. This stage prioritizes Flash size while preserving exact compact
Speex Q7/16-tap QMF output and loaded PWM throughput. The portable explicit
C fallback and architecture/ASM-enable selection remain unchanged. Existing
Xiph Speex 1.2.1 BSD provenance is retained; the allocation and outlining are
original project work.

Start with the [validated split H/L accumulators](speex-qmf-split-accumulators.md).
They save both cycles and Flash, providing a useful budget for sharing code.

The paired loop contains two identical WB_INPUT bodies and four WB_FINISH
bodies. A local `.type name,@function` helper shares each operation with a
private fixed-register contract. Omit `.global`: these helpers are not callable
through the public C interface. Keep the public function's `.size` separate
from each helper's size, so symbol-based ABI checks identify public returns.

The input helper uses the original WB_INPUT macro and RET. It preserves
r0:r1 and X, including the oldest history words saved before either insertion.
r20 is the caller's existing bias constant 128 on entry and exit. Its two
RCALL/RET pairs add 280 cycles per forty-pair block.

The finish helper accepts signed24 low/middle/high bytes in r20/r24/r25,
uses r21 as scratch and writes through Z. One MOV plus MOVW supplies each
argument triplet. It retains the original rounding, clipping and stores.
Before the four calls, save the live cursor limit from r25 into r0; restore
it afterward. The helper performs no MUL and does not touch r0, so no extra
stack save is needed for this value. The four calls, argument moves and cursor
preservation add 760 cycles per block.

Private RET may leave r1 dirty: both helpers return only to handwritten ASM,
with no C call in between. The public epilogue still clears r1 and restores
callee-saved registers. Compiled interrupts must restore interrupted r1,
r0 and SREG. Classic AVR5 RCALL/RET uses two stack bytes; other return-address
widths and toolchains require their own measurements.

## Measured alternatives

The baseline is the merged combined-common-product QMF. Each isolated recipe
passes 2244 blocks / 179520 output words per backend, complete signed16 channel
sweeps, 92 explicit rounding/clipping boundaries, alternating permitted alias,
exact mirrored state, guards/read-only inputs and 2244 public ASM ABI returns.
Explicit C object bytes and primitive cycles remain identical.

| QMF recipe | Probe Flash | Delta | Cycles saved/call | Own ASM stack |
| --- | ---: | ---: | ---: | ---: |
| Baseline common products | 2710 B | 0 B | 0 | 18 B |
| Split accumulators | 2636 B | -74 B | 500 | 22 B |
| Split + shared input | 2584 B | -126 B | 220 | 22 B |
| Split + shared finish | 2486 B | -224 B | -260 | 24 B |
| Split + both helpers | 2434 B | -276 B | -540 | 24 B |

The smallest recipe adds exactly 540 cycles on every tested call; sharing
only input remains a measured faster alternative. No production feature flag
is needed to retain these comparison recipes in the isolated screen.

The smallest recipe passes 72436 instruction-boundary IRQ injections,
including 41394 interrupted nonzero-r1 states. All 32 registers, SREG, PC and
SP are restored, with identical interrupted traces, arbitrary callee patterns,
both incoming T values, permitted alias and exact whole-arena state/guards.
Its whole IRQ probe peak is 37 B, versus 31 B for the original kernel.

## Complete decoder and loaded-player screens

Sources are frozen in a separate tree, retaining the original Codecs/common
relative header layout. Only the QMF source argument changes between recipes;
the compiler/options, other sources, inputs and oracles stay the same. This
frozen baseline includes the independently measured compact divider and uses
25916 B raw Flash, compared with 26164 B in the merged main baseline.

| Profile / recipe | Raw Flash | Mean cycles/frame | IRQ free SRAM | Minimum queue |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 baseline | 25916 B | 217254.063 | 412 B | 31 |
| WB3.95 shared input | 25790 B | 216374.063 | 411 B | 31 |
| WB3.95 both helpers | 25640 B | 219414.063 | 409 B | 30 |
| WB12.8 baseline | 25916 B | 232147.188 | 391 B | 8 |
| WB12.8 shared input | 25790 B | 231267.188 | 389 B | 8 |
| WB12.8 both helpers | 25640 B | 234307.188 | 387 B | 7 |

The QMF-only complete-image saving is exactly 276 B; the selected raw image
is 524 B smaller than merged main when the separate divider saving is included.
Every screened frame adds exactly 2160 cycles, or 0.675 CPU percentage point
at 16 MHz / 50 frames per second. Raw whole stack peaks are 201 B for both
profiles; loaded IRQ peaks are 214 B. Static SRAM is unchanged.

All candidates preserve raw PCM/reset and production s16/PWM exactly. Loaded
screens use the real timer/queue implementation plus 8% foreground work and
have zero underruns. The selected IRQ image is 26076 B, versus 26352 B for the
frozen baseline. WB3.95 covers 18 streams capped at 64 frames (1152 frames);
WB12.8 covers one 64-frame prefix of the retained long recording. Ready RAM
inputs do not establish transport latency or physical-board timing. The final
five-profile full gate owns broader integration admission.

## Reproduce

The [driver](../../Codecs/Speex/AVR/tests/screen_qmf_size.py) reconstructs the
exact recipes and freezes source/header dependencies under ignored
`build/qmf-size/`. It accepts existing tool/cache/input paths without downloads:

```sh
python Codecs/Speex/AVR/tests/screen_qmf_size.py --source-root <merged-baseline codec root> --avr-gcc avr-gcc --node node --avr8js-entry <avr8js/dist/cjs/index.js> --profile-cache <profile/source> --corpus <data/screen>
python Codecs/Speex/AVR/tests/screen_qmf_size.py --phase audit --corpus <data/screen>
```

The [receipt](../../Codecs/Speex/AVR/reports/qmf-size-screen.json) records
LF-normalized source/test hashes, exact tool/header/binary/C-object hashes,
input/oracle hashes and resource results. Complete decoder tests select ASM;
only isolated C primitives execute. Firmware, raw timings and logs remain
ignored. Existing baseline proofs are reused only after exact binary identity.
