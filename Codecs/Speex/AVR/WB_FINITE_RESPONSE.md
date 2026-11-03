# Exact WB response, QMF and IIR speed improvements

Target: ATmega328P / classic AVR5, 16 MHz, 2 KB SRAM, GNU ABI, AVR GCC 7.3.0,
existing mixed Os/O2/O3 attributes, LTO, mcall-prologues and mrelax. Baseline
`7ca56cf1` includes the preceding bounded generic divider. All five WB rates
and optional lower-band modes are linked in the measured images.

The final stage combines four independently checked changes:

- Shared quarter interpolation with the exact finite margin repairs, documented
  in [the interpolation stage](WB_INTERPOLATION_SPEED.md).
- Signed16 high-response accumulation and a dedicated positive-HB divider.
  All 25171968 paired current/Xiph LPC conversions prove every difference and
  prefix fits signed16 and the final divisor is 111..31849. Low-band arithmetic
  stays signed32; its positivity check and the ratio-zero error remain.
  The older generic ratio API retains its wider domain. Each assembly entry
  has a separate section, so the unused generic leaf is discarded.
- QMF reuse of related 7/-14 and -10/15 constant products, preserving exact
  signed24 arithmetic, original rounding, clipping, state and alias behavior.
- A register cache for the second-last old IIR coefficient during warm-up.
  The phase uses T; compiled IRQs restore SREG and dirty r1 exactly.

Every handwritten optimization retains its explicit C equivalent. Architecture
matching and the separate assembly-enable flag still select ASM; unsupported
targets and disabled ASM select C. Hardware memory access remains independent.
No packet layout, quantizer, QMF coefficients, output format, public callback
or persistent state is changed. No complete C decoder is executed or timed.

## Complete available-corpus comparison

The [full receipt](reports/wb-finite-response-full.json) binds sources, compiler
controls, component proofs, firmware, every input/oracle and both per-frame
timing traces. Before artifacts are reused only after hash verification and a
fresh byte-identical baseline rebuild. After observations are fresh, except
completed records were retained across the explicitly requested cleanup stop.
Only unfinished work was restarted after the human authorized resumption.

Both raw epochs pass 34869 frames and all reset checks with exact signed16
PCM. Every frame is faster. Another 34869 complete-history frames pass the
production timer/PWM queue with exact signed16/PWM and zero underruns. Sample
intervals remain 990..1010 cycles. The additional foreground load is 8% for
WB3.95/9.8/12.8 and 3% for WB5.75/7.75.

| Profile | Before cycles/frame | After | Decoder CPU before -> after | Loaded min queue |
| --- | ---: | ---: | ---: | ---: |
| WB3.95 | 221580.720 | 218575.848 | 69.244% -> 68.305% | 31 |
| WB5.75 | 230252.190 | 227247.319 | 71.954% -> 71.015% | 26 |
| WB7.75 | 240167.464 | 237166.593 | 75.052% -> 74.115% | 21 |
| WB9.8 | 222831.359 | 220360.183 | 69.635% -> 68.863% | 7 |
| WB12.8 | 235741.397 | 232804.295 | 73.669% -> 72.751% | 7 |

Savings are 2471..3005 cycles/frame, or 1.109..1.356% of decoder time relative
to the admitted post-divider baseline. CPU percentages divide raw frame time
by 320000 cycles; they exclude startup/reset and interrupts. These are paired
whole-workload means, not a comparison of different bitrates on identical audio.

Bare ASM images grow from 25920 to 26164 B (+244 B), with identical static SRAM and
measured peak stack. Loaded images use 26600 B, static SRAM 1425..1447 B and
retain 391..412 B free at peak. AVR C compile/link controls shrink from 31374 to 31212 B
(-162 B); the portable export with 21 C sources compiles/links without assembly.
This does not establish real-time performance of the C decoder.

Available data comprises three complete 10627-frame lower-rate corpora,
788 WB9.8 public phrase/dialogue frames and 2200 continuous WB12.8 frames.
The original complete legacy WB9.8/WB12.8 corpora remain unavailable; WB9.8
uses historical published ASM captures, and WB12.8 uses the existing independent
SPI-corpus oracle. These limits are retained in every frame receipt.
Ready-RAM input does not measure SPI delivery latency. No new physical-board,
analog measurement, media publication or firmware-gallery rebuild is claimed.

## Component evidence and reproduction

- [HB finite domain](reports/wb-response-domain.json): all 67108864 represented
  quarter cases, including the initial zero-den response 8274.
- [Private divider](reports/wb-hb-ratio-unit.json): full validated divisor sweep,
  original generic API, explicit C/generic selection, ABI, active timer IRQs and
  matched scalar replay. Timing arrays are hashed and reconciled with totals.
- [QMF common products](reports/qmf-common-product-screen.json): all 2244 blocks,
  independent C object, all signed16 inputs, clipping/rounding/alias and every
  executed IRQ boundary. Measured 200 cycles and 160 byte MULs saved per block.
- [IIR warm cache](reports/iir-second-cache-screen.json): both orders, exact
  C/ASM output and state, boundary IRQs, unchanged C objects and stack.
- [Five-profile screen](reports/wb-finite-response-screen.json): 3769 raw and
  loaded frames before complete validation.

Use the shared stage runner with `--out Codecs/Speex/AVR/build/hb-finite-speed`,
the same retained inputs and a separate baseline checkout at `7ca56cf1`.
Its `controls` phase compiles/links C and rebuilds the baseline without running
a C decoder. `raw` and `irq` phases execute the ASM images. Then:

```sh
python Codecs/Speex/AVR/tests/audit_wb_hb_ratio.py --check
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py --stage finite --screen
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py --stage finite
```

Generated firmware, audio, logs and timing arrays remain ignored. The broader
speed goal remains open: split QMF accumulators and the finite pitch-root map
have useful measured candidates that still need their own final integration.
