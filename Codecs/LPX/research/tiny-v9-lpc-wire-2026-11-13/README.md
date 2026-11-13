# Encoder-side LPC anchors on ATtiny88

This experiment uses a separate wire marker on copies of LPX v9 streams.
It transmits the exact fixed-point LPC anchors from the existing two-segment
C decoder. The initial frame sends its absolute endpoint. A dynamic frame
sends the midpoint relative to the previous endpoint and the new endpoint
relative to twice the midpoint minus the previous endpoint. A repeat skips both
vectors. Each vector's ten 16-bit modular differences use zigzag and bounded
Rice coding. The encoder chooses the Rice parameter per vector and uses a
16-bit escape after four zero bits. The synthesis interpolation, excitation
and recording metadata are unchanged. The prototype uses the 20 bytes freed
by the old and new LSF vectors to stage the second anchor.

## Complete audio data

| Inputs | Segments | Samples | LPX v9 | Prototype | Increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sparse80, all 181 retained recordings | 306 | 15,188,029 | 400,876 B | 1,255,542 B | 213.2% |
| P6, retained comparison segments | 303 | 15,098,277 | 1,120,855 B | 1,969,977 B | 75.8% |

All segments grew. Fixed-point C with assembly disabled produced identical
PCM16 and PWM8 in every segment and consumed the complete packets. The P6
controls were losslessly repacked from the saved v5 input before comparison.
Floating-point synthesis was outside the test scope.

On Sparse80 the original spectral packets use 1,155,700 bits in total
(about 26.7 bits per dynamic frame when the initial and repeat packets are
also charged to that frame count). The first-difference midpoint residuals
have an empirical zero-order cost of 106.2 bits per dynamic vector when
grouped by coefficient. Second differences lower the endpoint's corresponding
cost from 106.1 to 72.2 bits. These are model estimates for the tested
predictors and distributions. A model with additional context could change
the costs.

## Timer IRQ playback

Matched to `3ff5dc0f` on simavr 1.6 with GNU AVR ABI, AVR-GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, SRAM512, two LPC segments,
MUL16 unroll 2, FIFO32/prefill24, 16 MHz CPU and 8 kHz sampling.
The test uses the pinned ATtiny88 definitions and the 38-cycle sample IRQ
with entry and RETI included. The mean cycle metric adds one IRQ to the
active decoder CPU mean. The timing observer also tracks the peak decode
call and the timer and PWM output cadence.

All 308,339 PWM samples across the 22 P4/P6/Sparse80 loads match both the
baseline AVR output and the independent C reference. Timers and queue
drain complete with zero underruns. The program excluding audio drops
from 5190–5191 B to 3994–3995 B. All cases improve by 0.48–53.68
cycles/sample, and the largest mean falls from 1655.78 to 1615.37 cycles/sample.
The peak decoder CPU call decreases by 2133–7639 cycles in every load.
Static SRAM is 433 B and the peak observed stack drops from 54 B to 51 B.
The complete image shrinks on 17 loads and grows by up to 444 B on the other
five. The measurements are simulator results.

The data-size gate failed. LPX v9 remains the format used by the encoder,
the C reference and the published players.
[Per-load measurements and aggregate corpus counts](measurements.json).
