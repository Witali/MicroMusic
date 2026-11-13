# ATtiny88 spectral anchor selection

The compact fixed-point AVR25 ASM build selects both LSF sources before the
ten-coefficient loop. LPC segments 1/2 use only `t=0, 8, 16`. For `u=t/8`,
`prev*(2-u) + cur*u - 1` is respectively `prev+prev-1`, `prev+cur-1`, or
`cur+cur-1`. The selected operands are elements of the original arrays.
P4 still doubles the centered sum. The valid nodes stay in 1–127 for P6/P15
and 2–126 for P4. The polynomial and lookup arithmetic use the same inputs.

Testing the grid flag directly at use avoids keeping a separate flag live
across the polynomial loop. With AVR-GCC 7.3.0 and the AVR GCC ABI, the local
frame of `convertLsfAt` is 15 bytes in the baseline and the final build.
The first two-pointer prototype reserved 16 bytes. The code uses C++
expressions and adds no handwritten assembly. It is selected only for the
explicit AVR25 ASM backend with compact runtime profiles and LPC segments
1/2. The fixed-header ROM path and selectable C backend keep the original
expression.

## Measurement setup

The baseline is `de98d64162368cf3b6104907076a7e1c3d3f3f17`. Both revisions
were built with AVR-GCC 7.3.0 at `-Os -flto`, using the ATtiny88 DFP 3.4.278
header. simavr 1.6 ran the resulting AVR25 firmware at 16 MHz and 8 kHz with
the complete Timer1 ISR and audited register reservations. Both builds use
LPC2 and MUL16 unroll 2. The universal firmware uses a 38-cycle IRQ and a
32-byte queue with prefill 24. The fixed-header catalog firmware uses a
44-cycle IRQ, a 24-byte queue with prefill 18, and each recording's published
gain.

The cycle metric is the active decoder CPU mean plus the longest complete
interrupt, excluding foreground queue bookkeeping. Playback completion,
output gaps and queue underruns are measured with the full player running.
Every PWM byte was compared with the baseline and with a native fixed-point
C decoder using standard-memory polynomial storage. The catalog builds
were also checked against the published WAVs at their catalog gains.
The measurements were made in simulation.

## Results

All 22 universal loads reproduced 308,339 PWM samples exactly. The complete
program, excluding only the embedded LPX audio, decreased from 5,556–5,557
to 5,546–5,547 bytes. Each full image shrank by the same 10 bytes. The peak
stack was 64 bytes with at least 14 bytes of margin. The minimum observed
queue depth increased from six to seven samples, with zero underruns.

The decoder with IRQ ran faster on 21 loads and tied on the all-pairs
control. The greatest reduction was 3.45 cycles per sample. The slowest
load went from 1765.77 to 1762.47 cycles per sample, 88.12% of the 2000-cycle
budget with this accounting. It remains above the 1500-cycle target.

The nine fixed-header catalog images rebuilt byte for byte. They produced
141,708 exact PWM samples with no underruns and the same timings and stack
use as their respective baselines.

An independent UBSan polynomial test also checked the new C++ expression
with its selection enabled in a private native build. All 184,320 LPC1/2
conversions matched the original cosine and convolution oracle across the
three profiles and every ring cursor position.

## Reproduce the universal comparison

From the repository root, use a fresh ignored output directory. On Windows
with the AVR and simulator toolchain in Ubuntu WSL, run:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-spectrum-anchors --target tiny --baseline de98d641 --wsl Ubuntu
```

On Linux omit `--wsl Ubuntu`. The paired binary and PWM hashes, timings,
stack measurements and build flags are recorded in [measurements.json](measurements.json).
The source and evidence binding is in [source-transition.json](source-transition.json).
