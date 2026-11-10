# AVR Speex Flash reduction, 2026-11-10

Target: ATmega328P / AVR5 with MUL, 16 MHz, 2 KB SRAM, GNU AVR ABI,
AVR GCC 7.3.0; existing mixed Os/O2/O3, LTO, mcall-prologues and mrelax.
The user changed the current priority to decoder Flash. Small measured cycle
costs are accepted while preserving exact PCM and loaded real-time output.
Baseline is merged main `e5350100`. All five WB rates and all lower NB modes
are linked in the measured decoder-mailbox images; audio payload is excluded.

The complete ASM image shrinks **26164 -> 22940 B**, saving **3224 B (12.32%)**.
The loaded production-PWM/queue harness shrinks **26600 -> 23374 B** (-3226 B,
including layout/relaxation). Static SRAM remains 1284..1306 B for raw images
and 1425..1447 B for loaded images. Raw peak stack falls 197..198 -> 166 B;
loaded peak falls 210..211 -> 179 B, retaining 422..444 B free SRAM.

## Changes admitted together

- Count fifteen exact positive-HB division rounds instead of expanding them:
  private leaf 306 -> 58 B, at most 176 extra cycles/frame, no local stack.
- Share one order8/order10 LSP coefficient pair loop and one private rounding/
  saturation routine: 238 B instead of 806 B for the former NB10 kernel alone.
  WB uses the same assembly entry; both orders retain explicitly selected C.
  Replacing the WB sequential C tail also removes caller code and temporaries.
- Share complete HB1 excitation/fold loops through small table/geometry entries.
  Keep each entry independently collectable and retain the inline singleton
  when no second geometry exists. The isolated all-feature screen saves 892 B
  for 84..132 extra cycles/frame; two rounding stages remain distinct.
- Split bounded QMF accumulators into high/low words and outline repeated input
  and finish operations into local fixed-register subroutines. The selected
  recipe saves 276 B for 2160 extra cycles/frame. The measured faster input-only
  alternative remains in the cookbook as an optional future tradeoff.
- Replace the private NB1 pitch root by the already proven 128-entry exact map.
  The complete pitch domain 17..144 matches the original fixed-point polynomial;
  `SPEEX_NB1_PITCH_ROOT_TABLE=0` explicitly restores that arithmetic. The separate
  NB2.15/WB3.95 paired screen and its small zero-gain costs are retained.

These are exact rearrangements and finite maps, not approximate coefficients
or altered quantization. Public packet/API/output formats, clipping, rounding,
reset behavior, history and permitted QMF alias remain intact. Supported target
macros plus the separate explicit ASM-enable define still select assembly;
ASM-disabled and unsupported targets select portable C. Flash access remains
independent of arithmetic backend selection.

## Complete available workload and resource tradeoff

[The full receipt](reports/wb-size-full.json) binds all sources, component
proofs, input/oracle bytes, firmware, per-frame traces and loaded output reports.
The old raw observations are reused from their admitted source-bound receipt;
a fresh byte-identical baseline rebuild verifies that reuse. All 34869 new raw
frames match signed16 PCM and resets. Another 34869 complete-history frames pass
the production timer/PWM/queue code with exact signed16/PWM and zero underruns.
Output intervals remain 990..1010 cycles. Extra foreground work is 8% for
WB3.95/9.8/12.8 and 3% for WB5.75/7.75.

| Mode | Raw decoder CPU before -> after | Raw peak stack | Loaded min queue | Loaded free SRAM |
| --- | ---: | ---: | ---: | ---: |
| wb395 | 68.305% -> 68.759% | 198 -> 166 B | 30 | 444 B |
| wb575 | 71.015% -> 71.548% | 197 -> 166 B | 26 | 439 B |
| wb775 | 74.115% -> 74.659% | 197 -> 166 B | 20 | 434 B |
| wb98 | 68.863% -> 69.561% | 197 -> 166 B | 7 | 429 B |
| wb128 | 72.751% -> 73.319% | 197 -> 166 B | 6 | 422 B |

CPU divides raw mean frame cycles by 320000; it excludes startup/reset and ISR
work. Added CPU is 0.454..0.698 percentage point, or 0.665..1.014% of decoder time.
The input workloads differ by bitrate, so this is a paired before/after
comparison rather than a controlled bitrate-quality comparison.

The available workload is three complete 10627-frame lower-rate corpora,
788 historical WB9.8 public phrase/dialogue frames and 2200 independent WB12.8
continuous frames. Original legacy full WB9.8/WB12.8 corpora remain unavailable;
WB9.8 references are earlier published ASM captures. Inputs are ready in RAM;
this does not refresh external SPI latency, physical-board or analog tests.

AVR C controls compile/link successfully: 31212 -> 31244 B (+32 B). The 21-source
portable C11 export also compiles/links with no assembly. These are compatibility
checks; no complete project C decoder was executed or timed. Isolated C scalar,
BigInt and untouched Xiph primitives provide the arithmetic references.

## Component evidence and reproduction

The receipt includes hashes of the counted-divider scalar/IRQ proof, shared
LSP scalar suites and refreshed complete HB response proof, shared-fold feature
matrix/IRQ screen, QMF boundary-IRQ proof and finite pitch-root integration.
Every component retains its own pinned baseline and scope; its isolated size
change is not blindly summed to predict the linked image.

Use `tests/run_wb_ratio_stage.py --out build/size-next` with the retained source
baseline and inputs; the shared runner keeps `build`, `controls`, `raw` and
`irq` phases separate. The `controls` phase compiles/links C only. Raw and IRQ
execution must select ASM. Preserve complete recording history for IRQ tests.
Then run `python Codecs/Speex/AVR/tests/audit_wb_size_stage.py` from the worktree
root. The audit checks frame-array lengths/totals/extrema, paired PCM hashes,
source and component bindings, export contents and actual loaded deadlines.
Generated audio, firmware, traces and logs remain ignored.

The broader optimization goal remains open. Future size candidates must be
priced against complete Flash, stack and active-IRQ timing; shorter source
or isolated kernel bytes do not establish a useful firmware improvement.
