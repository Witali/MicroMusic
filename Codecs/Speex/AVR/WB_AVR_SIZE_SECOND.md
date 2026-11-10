# Second AVR Speex Flash reduction, 2026-11-10

Target: ATmega328P / AVR5 with MUL, 16 MHz, 2 KB SRAM, GNU AVR ABI,
AVR GCC 7.3.0, avr8js 0.21.1. The pinned build retains LTO,
`-mcall-prologues -mrelax -fwrapv -fno-strict-aliasing` and measured per-function
Os/O2/O3 policies. Baseline `1da660ea` is the [first admitted size cycle](WB_AVR_SIZE.md).
All five WB rates and the enabled lower NB modes are linked in each measured
decoder image; these Flash totals exclude audio payload.

The combined raw ASM image shrinks **22940 -> 19880 B**, saving **3060 B
(13.34%)**. The production timer/PWM/queue harness shrinks **23374 -> 20286 B**,
saving **3088 B (13.21%)**, including linked layout/relaxation effects. This is
a Flash-first tradeoff: mean decoder time increases 1.40..1.60%, with sufficient
measured output throughput at the admitted foreground loads.

## Changes admitted together

- Share the exact general-product body and count descending paired LSP
  polynomial updates instead of duplicating them for stages 2/3/4. Preserve
  each Q14 floor, modulo-32 update and final aligned product.
- Share the long-innovation sample loop and epilogue, and use one short-pitch
  controller for the two enabled geometries. Keep geometry, edge-history and
  rounding behavior exact; preserve the existing C selections.
- Share the order-8/order-10 IIR warm/steady output body within each order.
  The bounded sample counter's sign distinguishes the phases without another
  call or stack slot. The T flag keeps its existing coefficient-age role.
- Use O2 for the ASM-backed NB controller while retaining LTO specialization,
  and Os for its WB ready stage. Share sequential HB margin repairs through
  the proven finite mask loop; retain the separate signed half shifts.

The combined linked reduction is measured directly. Isolated component savings
are not summed to predict the final image. No quantization, filter coefficients,
packet format, public API or intended PCM output is changed. Handwritten AVR
arithmetic still requires supported architecture macros and a separate explicit
ASM-enable define. Explicitly selected C and unsupported architectures retain
the portable C path; hardware memory access remains independent of that choice.

## Complete available raw and active-IRQ admission

The [full receipt](reports/wb-size2-full.json) binds the final sources, component
proofs, firmware, input/oracle bytes, per-frame traces and loaded reports.
Baseline raw observations are reused byte-for-byte from the admitted first
cycle; its source manifest and fresh identical baseline rebuild bind that reuse.
All **34869 new raw ASM frames** match signed16 PCM and reset checks. Another
**34869 complete-history frames** match signed16 PCM and emitted PWM using the
production timer/queue/interrupt code, with **zero underruns**. Loaded output
intervals are **995..1005 cycles**, inside the 990..1010-cycle admission bound.

| Profile | Frames per raw/IRQ epoch | Raw CPU before -> after | Extra foreground work | Loaded minimum queue | Loaded free SRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| WB3.95 | 10627 | 68.759% -> 69.856% | 8% | 30 | 443 B |
| WB5.75 | 10627 | 71.548% -> 72.643% | 3% | 25 | 438 B |
| WB7.75 | 10627 | 74.659% -> 75.814% | 3% | 19 | 433 B |
| WB9.8 | 788 | 69.561% -> 70.532% | 8% | 5 | 428 B |
| WB12.8 | 2200 | 73.319% -> 74.447% | 8% | 5 | 421 B |

CPU is raw mean frame cycles divided by 320000 cycles per 20 ms frame; it
excludes startup/reset and interrupt work. Added CPU is 0.971..1.155 percentage
point. The largest paired per-frame increase is 3998 cycles, and the largest
new raw frame costs 248747 cycles (77.733% of a frame). The paired workloads
differ by bitrate; the table is not a controlled bitrate-quality comparison.

Static SRAM is unchanged: **1284..1306 B raw**, **1425..1447 B loaded**. Raw peak
stack is **167 B** versus 166 B; loaded peak is **180 B** versus 179 B. Thus
loaded minimum free SRAM decreases by one byte to **421..443 B**. Each stream's
static SRAM, measured peak stack and remaining SRAM total 2048 B.

## Arithmetic and portability evidence

The component receipts retain their individual frozen baselines and scopes:

- [LSP polynomial scalar/ABI/IRQ and screen evidence](reports/lsp-polynomial-size-screen.json).
- [Innovation/controller scalar, geometry and loaded screens](reports/innovation-controller-size-screen.json).
- [IIR factoring and unchanged-stack evidence](reports/iir-output-size-screen.json).
- [Compiler-policy comparison](reports/compiler-policy-size-screen.json) and
  [final WB controller/interpolation AVR screen](reports/wb-controller-size-screen.json).
- [Actual interpolation-body domain proof](reports/wb-interpolation-mask-domain.json):
  67108864 quarter cases over all 4096 codebook endpoints, exact against both
  baseline and the independent separately-rounded Xiph formula.
- [Refreshed complete HB LPC-response proof](reports/wb-size2-response-domain.json):
  25171968 untouched-Xiph primitive comparisons, response bounds 111..31849.

The IIR primitive preserves complete output/state/guards, alias behavior, ABI,
r1 and interrupted SREG/T. Its 75999 instruction-boundary IRQ injections include
50471 interrupted nonzero-r1 states; own stack and private call counts remain
unchanged. The full combined gate above verifies actual loaded deadlines.

Current [LSP observers](reports/lsp-polynomial-current-compat.json) and
[innovation/WB observers](reports/innovation-controller-current-compat.json)
also pass their bounded primitive checks. Their public-return/stack assertions
now recognize shared bodies and nested private calls. The isolated short-pitch
test builder gained optional NB4 selection after the full decoder observations;
the receipt preserves the observed source graph and records this test-only
update separately. Production builder dependencies are unchanged.

AVR C compatibility controls compile/link at **31244 -> 31062 B** (-182 B).
The **21-source portable C11 export** also compiles/links with ASM disabled,
no assembly source and no duplicate source. These are compile/link checks:
no complete project C decoder was executed or timed. Isolated C, BigInt and
untouched Xiph primitives provide the arithmetic comparisons.

## Limits and rejected overload

The workload consists of three independent 10627-frame lower-rate corpora,
788 historical WB9.8 published phrase/dialogue captures and 2200 independent
continuous-history WB12.8 frames containing Russian/English speech. The original
legacy full WB9.8/WB12.8 corpora remain unavailable. WB9.8 output equality is
bound to historical ASM captures, not a newly generated independent oracle.

Packets are ready in RAM in the loaded gate. This validates the production
decoder, IRQ and queue under the stated synthetic foreground work; it does
not refresh physical-board, analog-output or external SPI/transport latency
measurements, or admit further profiles, sample rates or quality changes.

The LSP component's separate **11% extra-work stress** (35200 cycles/frame,
256 frames) failed with underruns for the baseline and both candidates:
319 baseline, 415 shared-product, 458 counted-loop. It is retained as rejected
evidence, not a supported load. Signed16 comparisons preceded the underrun
assertion; subsequent PWM/timer checks are not admitted for these failed runs.
The successful component 8% screens and the final per-profile loads above
define this cycle's admission.

## Reproduce and audit

Retain the pinned baseline, final source manifests and `build/size-second`
inputs before rebuilding. The codec's `tests/run_wb_ratio_stage.py` separates
build, C compile-only controls, raw ASM and loaded ASM phases. From the worktree
root, pass `--out Codecs/Speex/AVR/build/size-second` and the required phase,
toolchain and frozen-source arguments.
Use the established profile-specific loads and preserve complete recording
history during IRQ verification. Do not substitute C decoder execution.

From the worktree root, audit the retained final evidence with:

```sh
python Codecs/Speex/AVR/tests/audit_wb_size_stage.py --cycle second
```

Generated firmware, audio, packet traces and logs remain under ignored build
paths. This bounded second-cycle admission is complete; new optimizations and
hardware/transport extensions require their own measured work.
