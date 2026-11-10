# Shared Speex order 8/10 coefficient finish

Measured isolated arithmetic on ATmega328P / AVR5, GNU AVR ABI, AVR GCC 7.3.0
(`-Os -flto -fno-ipa-icf -fwrapv -fno-strict-aliasing -ffunction-sections
-fdata-sections -mmcu=atmega328p -mcall-prologues -mrelax`) and avr8js 0.21.1.
Production integration and full-frame PCM/interrupt timing admission are separate.

For symmetric half-polynomials with `p[0] == q[0] == 2^20`, pair the outputs
using `S = p[j]+p[j-1]`, `D = q[j]-q[j-1]`. The forward/mirrored results are
`clip(asr32(wrap32(S+D+128),8))` and `clip(asr32(wrap32(S-D+128),8))`, with
clipping to `[-32767,32767]`. Do not round `S` or `D` before combining them.
The original sequential walk uses the same terms in reverse order for the
second half; modulo-32 addition/subtraction preserve the equality even when
intermediate signed values wrap. The half-polynomials and output must be disjoint.
This does not restrict the existing finite HB1 LPC/response proof domain.

Use two tiny entry points setting output length, one pair loop, and a local
round/saturate subroutine. Retain the latest input words between pairs. Stop
when the forward and reverse output pointers meet. Order 8 reads 32 input
bytes and writes 16; order 10 reads 40 and writes 20. No static RAM is needed.
The shared kernel saves `r2:r3`, `r6..r17`, and Y (16 bytes); its local call adds
two return-address bytes. `r0:r1` temporarily saves Z during mirror stores;
clear `r1` before the external return. The compiler-generated interrupt handler
saves/clears/restores `r1`; the active-interrupt tests also exercise multiplication.

| Isolated arithmetic kernel | Text | Raw order 8 cycles | Raw order 10 cycles | Own peak stack |
| --- | ---: | ---: | ---: | ---: |
| Previous dedicated order 10 | 806 B | — | 390–417 | 14 B |
| Shared loop, local rounding | 238 B | 432–469 | 516–562 | 18 B |
| Shared loop, inline rounding | 276 B | 396–419 | 471–498 | 16 B |

Cycles include the external RET and local call/return, excluding the caller's
CALL and ISR instructions/entry charges. The 238-byte variant saves 568 bytes
against the previous NB10 kernel alone; replacing the WB8 C tail may save more
after linking. The 276-byte alternative spends 38 more bytes to reduce latency.
For 4,096 structured scalar polynomials, the mean NB10 cycles are 404.199 before,
539.665 with outlined rounding, and 485.199 with inline rounding. Hypothetical
four-call NB10 overhead is 541.86 / 324 cycles (0.169% / 0.101% of a 320,000-cycle
20 ms frame at 16 MHz). These are arithmetic estimates, not decoder CPU figures.
The corresponding WB8 means are 449.687 / 406.612, versus 705 for the original
sequential C body compiled at O3 in this fixture. LPC reuse changes real call counts.

Each candidate passed 41,984 order 8 and 50,688 order 10 cases: arbitrary words,
all 256 rounding low bytes at directed saturation/wrap boundaries in each pair,
odd/page-crossing disjoint pointers, and structured fixed-point polynomials.
Every coefficient matched an independent sequential BigInt model, the original
sequential C at Os/O3, and the paired C fallback. Guards, read-only input, exact
read/write addresses, arbitrary callee-saved values, zero `r1`, and timer ISR
completion/multiply state passed. Completed timer interrupts were 351,916 / 515,875
for the outlined pair and 343,053 / 502,475 for the inline pair, with none lost.
This is a specified vector suite, not exhaustive over all input word combinations.
No full C decoder was executed or timed; no physical board was tested.

Keep both C helpers and selectors in `nb3_lsp_finish.h`, the shared assembly
entries in `lsp_finish.S`, and call `speex_nb3_lsp_finish8(p,q,ak)` from the WB
tail in `compact_lsp.c.inc`. The existing architecture define and separate
assembly-enable define select assembly. Disabled assembly and unmatched targets
must select C; both controls passed and their binaries are identical per order.
The NB10 C body remains unchanged. Refresh the source-bound finite WB response
proof after changing its C caller; then admit exact PCM, whole-image Flash/stack,
frame cycles, and PWM/buffer timing with interrupts active before claiming support.

Reproduce through the tracked driver, which copies the frozen scalar fixtures
and measured alternatives into a fresh ignored directory before building:

```sh
python Codecs/Speex/AVR/tests/run_lsp_size.py --avr-gcc AVR_GCC --node NODE
```

The `tests/lsp-size/` source fixtures preserve the exact measured code and
independent references. Generated binaries and reports stay under `build/`.
The runner refuses an existing output directory; pass a fresh `--out` to retain
older evidence. `--quick` is an explicitly incomplete screen. `--adopt` accepts
a retained evidence pack only after complete rebuilt binary, fixture-source
and verifier identity; it does not relabel observations as fresh executions.

The [scalar receipt](../../Codecs/Speex/AVR/reports/lsp-finish-size-unit.json)
binds the original frozen experiment, including the byte-identical historical
NB10 control and comment-only metadata rebinding. Its detailed historical
audit additionally needs the preserved ignored `build/lsp-size` evidence pack.
The [refreshed domain proof](../../Codecs/Speex/AVR/reports/wb-size-response-domain.json)
checks 25,171,968 current paired-C8/Xiph scalar conversions, covering all
67,108,864 represented quarter cases and preserving divisor bounds111..31849.
No full C decoder runs. Final combined image/PCM/PWM results are recorded
separately from these scalar measurements.

Provenance: original project assembly; polynomial equations derive from the
licensed Xiph Speex 1.2.1 `libspeex/lsp.c` retained under the codec's `vendor/`
directory. Preserve those vendor notices.
