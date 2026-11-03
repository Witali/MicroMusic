# Exhaust finite codebooks before narrowing a response calculation

Applicable caller: the pinned Speex HB1 order-8 synthesis on ATmega328P / AVR5,
GNU ABI, and its portable fixed-point C equivalent. This is an exhaustive
numerical bound, measured with isolated host scalar primitives; it is not an
AVR timing, firmware-size or active-IRQ admission. No production code changes
are needed to reproduce the proof.

The WB controller computes the high LPC response as
`d = 8274 + sum(den[odd] - den[even])`. Arbitrary signed16 coefficients allow a
much larger divisor, but this caller uses two six-bit HB1 codebook indices.
They define exactly 4096 correlated eight-angle endpoints. Preserve those
correlations instead of replacing the vectors with independent component
intervals: independent bounds discard useful information about actual LPCs.

The proof decodes every endpoint from the pinned tables, applies the exact
quarter interpolation and sequential margin repair, then calls the current
`speex_wb_lsp8()` C scalar primitive. Every resulting coefficient is checked
against the separately compiled, untouched Xiph 1.2.1 `lsp_to_lpc(order=8)`.
Both use wrapping signed arithmetic and the original fixed-point rounding,
word casts and coefficient clamps. No floating-point approximation is used,
and no full Speex C decoder is linked or executed.

| Domain actually converted | Cases | Minimum d | Maximum d |
| --- | ---: | ---: | ---: |
| Quarter 1, all ordered old/new endpoint pairs | 16,777,216 | 111 | 31,849 |
| Quarter 2, unordered pairs including diagonal | 8,390,656 | 111 | 31,831 |
| Quarter 4, every new endpoint | 4096 | 111 | 31,605 |

These 25,171,968 paired conversions cover all 67,108,864 old/new/quarter
cases: quarter 3 swaps quarter 1's endpoints, quarter 2 is symmetric, and
quarter 4 is independent of the old endpoint. Margin repair depends only on
the interpolated vector, so the same symmetries hold after repair. The runner
also checks the endpoint grid and that the generated primitive is the current
source body. The all-zero initial `den` response is 8274, inside the same bound.

The tight global maximum occurs in quarter 1 from endpoint 2744 to 2232:
repaired angles `[6040,8112,10208,11448,15016,16480,17896,20032]`, coefficients
`[2039,11691,2374,10941,1665,5585,1049,2485]`. Endpoint 2042 to itself gives
the minimum 111. Full witnesses remain in the compact report.

Do not infer intermediate signed16 safety from a final signed16 result. This
proof measures the four differences and cumulative `rh` prefixes separately:

| Pair index | `odd - even` range | Cumulative `rh`, starting at 8192 |
| --- | ---: | ---: |
| 0 | -15,638 .. 12,311 | -7446 .. 20,503 |
| 1 | -13,885 .. 15,426 | -2506 .. 27,364 |
| 2 | -9917 .. 8640 | -3057 .. 30,331 |
| 3 | -6316 .. 5466 | 29 .. 31,767 |

All measured terms and prefixes happen to fit signed16 for this pinned domain.
The driver additionally checks a modulo-65536 reduction against the int32
response on every vector. For future reuse, unsigned word accumulation gives
an explicit algebraic contract even when prefix bounds are not available:

```c
uint16_t response = 8274;
for (unsigned i = 0; i < 8; i += 2)
    response = (uint16_t)(response + (uint16_t)den[i + 1]
                                  - (uint16_t)den[i]);
/* Only the independently proven final 111..31849 bound permits this cast. */
int16_t divisor = (int16_t)response;
```

This permits a two-byte cached response or a dedicated validated-HB1 narrow
divider contract. It does not narrow an existing generic arithmetic API's
documented domain. Any implementation still needs actual AVR cycle/Flash/RAM
measurement, equivalent C selection and complete active-IRQ playback checks.
AVR applicability also relies on the existing exact C/ASM LPC primitive
contract; this host experiment does not execute AVR assembly.

Reproduce on a POSIX GCC/Clang host with GNU-style ELF linker options:

```sh
python Codecs/Speex/AVR/tests/check_wb_response.py --cc gcc --record
```

`--pilot-old-count 16` is explicitly incomplete and cannot update the retained
report. Host GCC 13.3.0 was used for the recorded exhaustive proof, with
`-O3 -fwrapv -fno-strict-aliasing`, separate current/reference scalar objects
and section garbage collection. Disposable source copies, binaries and logs
stay under ignored build directories. The compact
[source-bound report](../../Codecs/Speex/AVR/reports/wb-response-domain.json)
normalizes text hashes to LF and records all witnesses, terms and prefixes.

[Driver](../../Codecs/Speex/AVR/tests/host_wb_response.c),
[runner](../../Codecs/Speex/AVR/tests/check_wb_response.py),
[current primitive](../../Codecs/Speex/AVR/src/compact_lsp.c.inc),
[untouched Xiph primitive](../../Codecs/Speex/AVR/vendor/speex-1.2.1/libspeex/lsp.c),
[pinned codebooks](../../Codecs/Speex/AVR/vendor/speex-1.2.1/libspeex/high_lsp_tables.c),
[BSD license](../../Codecs/Speex/AVR/vendor/speex-1.2.1/COPYING).
The exhaustive-domain proof and driver are original project work; source
algorithm/codebook provenance remains Xiph Speex 1.2.1.
