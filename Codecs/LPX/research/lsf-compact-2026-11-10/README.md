# Exact AVR LSF to LPC compaction

First iteration of the [AVR size plan](../../AVR_DECODER_COMPACT_PLAN_RU.md),
relative to `0320c101`. Reusing the first coefficient and narrowing only the
proven split high part reduces every measured universal Tiny88 program by
48 B and each Mega C/ASM program by 6 B. Compressed streams, fixed PCM16/PWM,
file parameters and floating synthesis stay unchanged.

[The cookbook](../../../../docs/avr-asm-cookbook/lpx-lsf-compact.md) gives the
range proof, backend constraints and reproduction commands. All target timing
below is simulated with active interrupts; no physical board was measured.

## Final source admission

| Evidence | Scope and result |
| --- | --- |
| [tiny.json](tiny.json) | Fresh matched baseline/final full playback on 22 universal P4/P6/sparse80 cases and all 9 actual Tiny website recipes. Every universal program saves 48 B; every fixed-ROM program saves 26 B. All gates pass, no underruns, exact independent old C PWM; published WAVs also match at their catalog gains. |
| [mega.json](mega.json), [full IRQ receipt](mega-irq.json) | All 4 public/synthetic universal controls with each of C and ASM. Every program saves 6 B. ASM CPU totals stay equal; C improves slightly. Exact full baseline PWM and zero underruns. |
| [native-corpus.json](native-corpus.json) | All 181 records, 306 segments, 15188029 samples: current fixed native PCM16 and PWM exactly equal the baseline. Host-only, without another 306-segment AVR timing run. The v9/SRAM512/LPC2 floating preprocessed source and complete host library are byte-identical. |
| [nano.json](nano.json) | All 8 Nano speech images and the dialogue rebuild byte-identically to shipped HEX, with actual public streams/gains and unchanged sizes. No new IRQ timing is claimed for identical binaries. |
| [reproducer-checks.json](reproducer-checks.json) | The retained verifier itself was run afresh on Tiny Chego2k and both Mega backends for Chego2k; all matched gates passed. |

Universal Tiny program Flash is 5556–5557 B (5.426–5.427 KiB), including the
player, tables and startup, excluding only the exact embedded audio array.
Peak observed stack falls 67→64 B, minimum margin 11→14 B; static SRAM stays
433 B. Universal CPU plus complete IRQ never increases: the 400-pair case is
equal; other cases improve by 1.227–8.032 cycles/sample. Fixed-ROM website
controls improve by 0.936–3.980 cycles/sample and also save three stack bytes.
These are mean decoder CPU plus complete IRQ figures, not worst-call bounds.

The independent retained convolution test checks 368640 conversions against
the original cosine ROM using scalar full convolution, all 256 cursors,
145 live history slots, profiles 4/6/15 and LPC segments 1/2/4 under UBSan.
Existing SRAM512 partial-tail/copy/reset tests pass, as do the unrestricted
564288-factor and frozen ordered-anchor checks. The C reference shares the
first-coefficient change and retains the general product path; explicitly
enabled AVR25 ASM alone selects the bounded narrow split high part.

## Isolated screens and rejected alternatives

[First-factor screens](first-factor-screen.json), [range screens](range-screen.json)
and [address screens](address-screen.json) distinguish their own source hashes,
compile-only cases and measured IRQ cases. Their isolated byte savings are not
added to predict the combined result.

The [combined screen](combined-screen.json) compares the selected combination
with a further byte-offset recurrence. That additional variant is smaller,
but slows all four measured Mega ASM cases by about 0.07 cycles/sample.
It remains rejected. Stage dispatch, templating, forced outlining and output
loop alternatives also remain unselected for their recorded size/speed costs.
No rejected branch or extra user-facing build key is added to production.

## Source and release history

[source-transition.json](source-transition.json) binds every new receipt and
the final source, while preserving hashes of all 17 prior receipts/catalogs.
Old measurements keep their original source hashes. The source-history tests
follow the explicit numeric-mode transition and then this separately measured
transition; they never substitute an old timing value for a fresh run.

The published HEX/catalog files remain the previous release. Their identities
and measurements are preserved; the new Tiny builds are compared separately.
Private media, recording identities, fingerprints and source locations are
excluded. Code/tool hashes and already-public fixture identifiers and hashes
are kept for audit and reproduction.

Run `tests/verify_lsf_compaction.py` with a fresh ignored output directory and
`--target tiny` or `--target mega`; add `--wsl Ubuntu` on Windows. The script
reconstructs the original baseline from local Git and measures current source
under the same real-target compiler settings. `--case chego-2k` selects the
small reproduction control. Ordinary C and floating build selections remain
available; no new wire format or approximation is introduced.
