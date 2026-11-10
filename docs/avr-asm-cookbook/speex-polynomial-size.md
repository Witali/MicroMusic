# Count polynomial stages and share an exact product

Measured on ATmega328P / AVR5 with MUL, GNU AVR ABI, AVR GCC 7.3.0,
mixed Os/O2/O3, LTO, mcall-prologues and mrelax; avr8js 0.21.1.
Original project assembly retains the Xiph Speex 1.2.1 equations and BSD
notices. Baseline `1da660ea`; explicit architecture/ASM selection and C fallback
are unchanged. This complements [the paired LSP technique](speex-lsp-twin.md).

Move the five identical general Q14 products into one private local leaf per
object, keeping the aligned P1 product inline. The leaf preserves T and its
factor r16:r17; r1 stays scratch internally. Clear r1 before the p0 addition
and public returns. Never expose a dirty r1 across a C ABI boundary. ISRs must
preserve interrupted r1 and SREG/T.

Replace stage-specific 2/3/4 blocks with a descending coefficient loop. Keep
old p[j] and p[j-1] in two register windows; read p[j-2] before writing the
higher coefficient, then advance the windows using four MOVWs. Retain separate
product floors and modulo-32 additions/subtractions. Preconditions remain:
signed30 coefficient bound, p0/q0=2^20, p1/q1 divisible by 64, disjoint arrays
of n+2 words. This does not reduce the accepted arithmetic domain.

T still selects the first-polynomial private return or final epilogue. The
paired loop saves r2..r17/Y (18 B), with two private return addresses making
its own peak **22 B**, excluding the caller return. Single stages save 12 B
and peak at 14 B. Public-RET observers must identify the entry SP, rather
than treating every RET or symbol boundary as a completed public call.

| Entry through RET | Before cycles, stage2/3/4 | After cycles | Own peak stack |
| --- | --- | --- | --- |
| Pair | 460 / 634 / 804 | 510 / 708 / 908 | 18 -> 22 B |
| Single | 238 / 327 / 416 | 245 / 341 / 437 | 12 -> 14 B |

The complete frozen WB image saves **612 B**, 22940 -> 22328 B; the NB8
compile-only size probe saves 620 B. WB raw means cost +1320.48/+935.63/+1261.56
cycles on the bounded WB3.95/full WB9.8/full WB12.8 workloads, preserving
3372 exact frames/reset and the whole raw 166-byte stack peak. Static SRAM
is unchanged. These isolated savings are not summed blindly across link graphs.

The independent BigInt/forced-C/ASM suites pass **257790 paired** and
**256254 single-stage** cases, all signed16 roots, directed coefficient limits,
guards and odd/page-crossing layouts. Every instruction boundary, including
private returns and dirty-r1 states, is preempted with a compiled MUL-using
ISR. Fresh current-source fixtures rebuild to six identical proven binaries;
current observers pass 33684 pair and 15939 single IRQ injections.

The 256-frame continuous WB12.8 screen passes at +25600 foreground cycles/frame
(8%): exact s16/PWM, zero underruns, queue >=7, 422 B free SRAM. The separate
11% overload fails for baseline/shared/loop with 319/415/458 underruns and
remains rejected evidence. Its later timing/PCM assertions are not admission.
Full combined admission and ready-RAM/board limitations are separate.

[Component receipt](../../Codecs/Speex/AVR/reports/lsp-polynomial-size-screen.json),
[comment-only rebuild](../../Codecs/Speex/AVR/reports/lsp-polynomial-comment-identity.json)
and [current verifier binding](../../Codecs/Speex/AVR/reports/lsp-polynomial-current-compat.json)
retain sources, fixtures, tools, arrays and image hashes. Rebuild current units
with the existing `tools/build_lsp_pair_test.py`, `build_lsp_stage_test.py` and
`build_lsp_stage_irq_test.py`, then use their top-level verifiers. Historical
variants and timing arrays remain under ignored `build/lsp-poly-size/`.
Only isolated C primitives execute; complete C decoder controls compile/link.
