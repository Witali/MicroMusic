# LPX fixed LPC interpolation on ATmega328P

The fixed C interpolation replaces division by `2^bits` with an arithmetic
shift. For a negative product, adding `2^bits - 1` before shifting preserves
the original truncation toward zero. For signed 16-bit anchors and the
supported LPC segments 1, 2 and 4, the product magnitude is at most 1,048,560.
The bias and sum fit the 32-bit intermediate. This uses the same signed-shift
semantics as the other fixed kernels under the supported toolchains.

| Universal C firmware, 306 paired IRQ runs | `e0939e89` | Shift with bias |
| --- | ---: | ---: |
| Program Flash, B | 4888–4889 | 4618–4619 |
| Highest segment mean including IRQ, cycles/sample | 1810.848 | 1639.715 |
| Total decoder CPU cycles | 25,964,147,140 | 23,568,531,784 |
| Minimum FIFO occupancy, samples | 15 | 23 |
| Peak stack, B | 75 | 68 |
| FIFO underruns | 0 | 0 |

Every segment took fewer decoder cycles or matched the baseline. The full
Flash images save 270 B with the same audio, and neither signed nor unsigned
32-bit division helpers are linked in the measured C images.

## Complete comparisons

- Native PCM16 and PWM matched `e0939e89` sample for sample on 181 recordings,
  306 v9 sparse80 segments and 15,188,029 samples. The desktop floating library
  was rebuilt and compared byte for byte.
- The same 306 segments were played in both ATmega328P C firmware revisions
  with IRQ active. The simulator checked full PWM against an independent
  older native decoder, output intervals, EOF, FIFO, stack and preservation
  of the MUL registers across IRQs.
- Four public and synthetic controls cover P4, P6 and sparse80, including
  changing spectra and boundary filter coefficients. The controls save
  159–173 mean cycles per sample with IRQ, with stack falling from 75 to 68 B.
- The two existing arithmetic configurations each passed 5,768,584 checks.
  The interpolation cases include extreme and random anchor pairs and shifts
  2, 3 and 4. The v9, SRAM512, compact parser and floating test suites ran
  together. Their optional local-stream fixture test was skipped.
- Four universal Mega ASM builds, 22 universal Tiny ASM builds, nine Tiny
  catalog builds, and nine Nano and dialogue builds matched their respective
  baseline binaries byte for byte.

The IRQ measurements use AVR-GCC 7.3.0, simavr 1.6, 16 MHz, 8 kHz, explicit C,
SRAM512, LPC segments 2, FIFO 32 and prefill 24. The ISR takes 64 cycles including
entry and RETI. Reported cycles per sample add that ISR to mean active decoder
CPU cycles. The Flash count includes the player, tables and startup with the
exact embedded audio subtracted. The comparison uses the one-shot AVR player.

Run the public controls from the repository root with a fresh output path.

```sh
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_atmega328p_v9.py \
    build/lpc-interpolation --current-source --wsl Ubuntu
```

Full private-corpus inputs and playback artifacts remain in local build
storage. The report retains corpus aggregates, code digests and measurements
of the public and synthetic controls. [Measurements](measurements.json).
