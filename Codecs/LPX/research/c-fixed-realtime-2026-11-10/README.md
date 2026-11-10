# Fixed C real-time and optional desktop double synthesis

The [AVR cookbook entry](../../../../docs/avr-asm-cookbook/lpx-fixed-c-realtime.md)
contains equations, compiler/ABI conditions, current IRQ measurements and
reproduction commands. The C implementation meets the tested ATmega328P
16 MHz / 8 kHz deadline without changing data or fixed-point output.

[corpus.json](corpus.json) is the complete anonymous 181-record/306-segment
baseline-v9 sparse80 run. It keeps code/tool hashes and aggregate observations,
with no media, source locations, identities or media hashes. It explicitly
records the twenty full images that exceed 6.5 KiB, and does not claim a new
Tiny88 application budget or support for arbitrary streams.

[float-validation.json](float-validation.json) records the integrated retained
double-DSP test: 680 synthetic reference decodes across seven configurations,
91 malformed cases and observable fractional history/coefficients. The largest
normalized difference from the independent convolution reference is about
2.06e-14. Four DSP/adapter/build-diagnostic tests and eight native batch/mode
tests pass. Direct double, PCM16 and PWM batch output are checked against
independent core callers. NumPy convenience-array execution was unavailable in
the Linux test environment; native ctypes output and Python API delegation
were tested. The five existing fixed batch tests also pass.

The floating option does not change the file format and is not used as the
integer AVR oracle. It intentionally omits intermediate integer rounding;
quality improvement is not asserted. Select it explicitly as described in
[FLOAT_SYNTHESIS.md](../../01_ACTIVE_Q0_CODEC/FLOAT_SYNTHESIS.md).
