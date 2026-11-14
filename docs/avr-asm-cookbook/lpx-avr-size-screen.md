# Exact LPX size candidates on AVR

Matched prototype builds from `e0939e89`, AVR-GCC 7.3.0, GNU AVR ABI,
universal v9 SRAM512, LPC segments 2, `-Os -flto`, 16 MHz, 8 kHz and FIFO32
with prefill24. ATmega328P uses the explicit C arithmetic and C ISR recipe.
ATtiny88 uses AVR25 software multiplication with unroll2 and the reserved
register ISR. Timings come from full simavr playback with IRQ active.
Program Flash includes startup, tables and the player, excluding the verified
unchanged audio array. The prototypes use the existing arithmetic and memory
selection.

## Power of two division in C interpolation

`lpx4LpcInterpolate` forms `prev + trunc((cur-prev)*t / 2^bits)`. On the
tested AVR5 C build the compiler emits a signed 32-bit divide. For the
supported shifts 2, 3 and 4, `t` is at most 16 and the product magnitude is
at most 1,048,560. This leaves room for the bias. For a negative product,
adding `2^bits-1` before the arithmetic shift gives truncation toward zero.
The positive case needs no bias. Use the arithmetic signed shift already
assumed by the supported compiler in the fixed-point code.

```cpp
const int32_t product = ((int32_t)cur - prev) * t;
const int32_t bias = product < 0 ? (1L << bits) - 1 : 0;
return (int16_t)(prev + ((product + bias) >> bits));
```

| Mega C workload | Program before → after, bytes | Mean cycles per sample including IRQ, before → after |
| --- | ---: | ---: |
| Chego 2k | 4889 → 4619 | 1779.002 → 1620.056 |
| Chego P4 | 4888 → 4618 | 1810.343 → 1641.149 |
| Chego P6 | 4888 → 4618 | 1815.037 → 1645.514 |
| Changing sparse80, lag18, boundary filters | 4889 → 4619 | 1860.531 → 1687.222 |

The divider symbol disappears. Stack falls from 75 to 68 bytes. All four
outputs match baseline PWM and complete playback with zero underruns.
The C fallback now uses this expression. The full reference and paired
interrupt runs are recorded in the [LPC interpolation report](../../Codecs/LPX/research/lpc-interpolation-2026-11-13/README.md).

## Select spectrum addresses before the loop

The compact segments 1/2 path calls `convertLsfAt` with `t` in `{0,8,16}`.
The existing grid index uses `prev*(2-u) + cur*u - 1` for `u=t/8`.
Select two sources before the loop: previous twice at 0, one of each at 8,
and current twice at 16. Then compute the same index with a byte addition.
The profile 4 doubling and cosine table are retained. The profile 6/15 sum
of two stored indices is at most 128. LPC segments 4 keep their existing
quarter-anchor expression.

```cpp
const uint8_t* left = t == 16 ? cur_ : prev_;
const uint8_t* right = t == 0 ? prev_ : cur_;
const bool doubleNode = !(LPX4_SPEECH_FLAGS & 2);
// In the existing loop over i:
uint8_t node = left[i] + right[i] - 1;
if (doubleNode) node += node;
```

| Tiny ASM workload | Program before → after, bytes | Mean cycles per sample including IRQ, before → after |
| --- | ---: | ---: |
| Chego P4 | 5556 → 5550 | 1600.445 → 1597.087 |
| Chego P6 | 5556 → 5550 | 1592.964 → 1589.652 |
| Bread low15 | 5557 → 5551 | 1311.991 → 1311.199 |
| Changing sparse80, lag18, boundary filters | 5557 → 5551 | 1765.769 → 1762.518 |

All four outputs match baseline PWM with zero underruns. Stack grows from
64 to 65 bytes in this prototype.
Selecting the weighted value inside the loop instead grows program Flash by
4 bytes despite speeding all four cases.

The admitted AVR25 ASM runtime-profile build tests `LPX4_SPEECH_FLAGS & 2`
at use. AVR-GCC 7.3.0 at `-Os -flto` returns the local frame to 15 bytes
under the AVR GCC ABI. This version saves 10 program bytes with a 64-byte
peak stack, exact PWM, and no slowdown or underruns on all 22 loads with
IRQ. The independently selectable C expression is the original weighted
sum. See the [matched build and IRQ report](../../Codecs/LPX/research/tiny-spectrum-anchors-2026-11-13/README.md).

## Parser screens

| Tiny ASM change | Program delta | Measured CPU + IRQ mean change per sample |
| --- | ---: | ---: |
| Share cache writeback and mask the assembled value after refill | −28 B | +0.332 to +1.511 cycles |
| Replace `pos+i*20` with `pos+(i?20:0)` | +16 B | +0.138 to +3.530 cycles |
| Read adjacent v9 scale5/gain3 as one byte | +2 B | −0.256 to −0.125 cycles |

These are independent screens on the same four Tiny loads as above. All
PWM comparisons are exact with zero underruns. The shared writeback lowers
minimum queue occupancy from six to five on the heavy sparse80 workload.
The observed costs rule out those three implementations as standalone changes.

On the later AVR25 v9 build, one eight-bit scale/gain read and a direct Q4
scale table together save 10 B. The Q4 table stores the exact previous
values times sixteen. The AVR-GCC 7.3.0 build retains the GNU AVR ABI and
the original selectable C implementation. All 22 active IRQ workloads
speed up with bit-exact PWM and the same stack and SRAM use.
[Paired measurements](../../Codecs/LPX/research/tiny-v9-block-header-2026-11-14/README.md).

Two later changes passed all 22 universal Tiny88 AVR25 loads with IRQ.
With the AVR GCC ABI and AVR-GCC 7.3.0 at `-Os -flto`, sharing the byte-wide
cache shift saves 30 B. Accumulating the shifted Rice quotient while
reading unary zeros saves a further 32 B and 2 B of peak stack. Both are
C++ transformations selected in the compact AVR25 ASM runtime-profile
build. They preserve the refill and error order and the eighth-zero escape.
The explicit C backend retains the original readers.
[Independent before/after measurements and reproducible commands](../../Codecs/LPX/research/tiny-parser-2026-11-13/README.md).

For reproduction, use the matched player and observers from
[the LSF compaction measurements](../../Codecs/LPX/research/lsf-compact-2026-11-10/README.md)
with an `e0939e89` baseline. Apply one source change in a fresh ignored copy.
The divider probe changes `Lpx4Math.h` in the C fallback only, and the spectrum
address probe changes the compact segments 1/2 branch in `Lpx4HybridCore.cpp`.
The screen ran against the stored baseline PWM and timing, with identical
settings and inputs. All transformations are original project work.

Measured candidate source SHA-256 values:

| Variant | Edited file | SHA-256 |
| --- | --- | --- |
| C interpolation | `Lpx4Math.h` | `f1ea047f797c86a13ce8aa83f0b32b5f2da55aea1a40f4bd053efd7f8a221554` |
| Select spectrum addresses before loop | `Lpx4HybridCore.cpp` | `3c98a27379bc86bb301deeac415ed887a7a037db4aab37ba95b42cfab4518b0e` |
| Select weighted value inside loop | `Lpx4HybridCore.cpp` | `1d8fae960844a829ee99a88723ad5cb6cd4ddceba4de5861f9bc4b3137299744` |
| Shared cache writeback | `Lpx4HybridCore.cpp` | `295ff962ec973b5e55f49a414c3213defdfbbdb46144421fb21ba1801bc22057` |
| Conditional pulse offset | `Lpx4HybridCore.cpp` | `f77e667fd7772639712f4a0196ae56f5e813eadb1ae6a0271d3b3b1e37ee6f21` |
| Block header byte | `Lpx4HybridCore.cpp` | `31f83da8701eb26e08637e55d242bdd1285a6831407eee9e09615b4133fd37ea` |
