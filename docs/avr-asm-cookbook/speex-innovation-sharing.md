# Share innovation loops and short-pitch geometry

Measured on ATmega328P / classic AVR5 with MUL, GNU AVR ABI, AVR GCC 7.3.0,
mixed Os/O2/O3, LTO, mcall-prologues and mrelax; avr8js 0.21.1.
Original project control-flow changes preserve Xiph Speex 1.2.1 arithmetic
and BSD provenance in the source/vendor notices. Baseline: `1da660ea`.

## One rolling loop, several entries

The forty-sample innovation entry now uses the existing rolling ten-sample
loop. A saved r9 holds the remaining vector count: four for this entry, zero
for ordinary ten/count/packed/scalar entries. Each completed vector consumes
its next already-stacked codebook index. No per-sample call or persistent RAM
is added. Save/clear/restore r9 for ordinary entries; count zero still returns
before setup. T continues selecting rolling versus packed input, so ISRs must
preserve SREG/T as before. Preserve all public callee-saved registers and r1.

The three-tap signed24 prefix bound, pitch clipping, Q14 floors, rounding,
saturation, input-read order and codebook Flash accesses are unchanged.
The complete image saves **304 B**. Forty-sample calls cost 54 extra cycles
but remain 428 cycles faster than four separate ten-sample calls. Other
positive-count calls cost eight extra cycles; zero count remains six cycles.

## One controller, two geometries

The shared ASM-side C controller accepts a table pointer and packed geometry:
84 means four rows of ten; 69 means five rows of eight. Width is `geometry>>3`
and row count is `geometry&7`. Thin wrappers retain existing private signatures.
Keep noinline/noclone here: constant specialization would duplicate the body.
This saves another **580 B** in the complete all-feature image.

The shared controller requires both the existing supported-architecture /
explicit-ASM selector and NB4. Other configurations retain the outer template,
including explicitly selected C on AVR. Remove unreachable inner C branches
only inside this already ASM-only controller. Memory access and arithmetic
backend selection stay independent. See [the implementation](../../Codecs/Speex/AVR/src/short_pitch.h).

## Measured boundary and evidence

The combined frozen image is 22940 -> **22056 B**. Five bounded screens use
192 raw and 192 active-IRQ frames per graph; exact PCM/reset/PWM and zero
underruns hold at the established 3%/8% additional loads. Mean frame costs
change by -4/0/+233/+291.094/+168.688 cycles for WB3.95/5.75/7.75/9.8/12.8.
Static SRAM is unchanged; this isolated controller graph raises whole raw
peak stack 166 -> 168 B and retains at least 420 B loaded free SRAM.
Final combined results belong to the separate full admission.

Independent BigInt and isolated forced-C/ASM probes cover 72960 forty-sample
cases, 67328 long/packed/count/scalar blocks, 49152 short-pitch blocks and
18432 additional mode2/3/4 geometry cases per relevant implementation.
They check guards, Flash range, read-only scales, all saved registers and r1.
The complete C controls are byte-identical, compile/link only.

[Observed receipt](../../Codecs/Speex/AVR/reports/innovation-controller-size-screen.json)
and [cleanup identity](../../Codecs/Speex/AVR/reports/innovation-controller-cleanup.json)
retain the original source/fixture/oracle/image hashes. Fifteen images rebuilt
identically after removing unreachable branches; this reuses observations,
without relabelling them as new runs. The historical receipt used CRLF bytes;
the final auditor explicitly reconstructs that representation if Git uses LF.

The [current observer binding](../../Codecs/Speex/AVR/reports/innovation-controller-current-compat.json)
records fresh 49152-case default/shared-controller primitive runs and 17032 WB
kernel blocks. Observe public RET by entry SP, including tail entries returning
from another symbol; preserve incoming ABI arguments during register-pattern
injection. Optional `tools/build_short_pitch_test.py --enable-nb4` exercises
the shared controller using NB3 geometry. The separate historical geometry
proof above covers NB4 output. This isolated-test builder update is recorded
separately from the production graph used in completed decoder observations.

The [portable image reproducer](../../Codecs/Speex/AVR/tests/innovation-size/reproduce_images.py)
requires `--avr-gcc`, `--before-src`, `--candidate-src` and a fresh `--out`;
optional `--node` plus `--data` runs the retained five-profile ASM screens.
Place `--out` under the codec's ignored `build/` so Node resolves its pinned
avr8js dependency. Use pinned baseline dependencies and frozen candidate snapshots. Full original
probes, logs and source snapshots remain under ignored `build/innovation-size-next/`.
No complete C decoder, physical board, analog output or SPI latency was tested.
