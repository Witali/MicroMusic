# LG1: grouped coefficients and logarithmic trajectories

LG1 is a complete experimental codec with its own `LG` file signature. Its
integer decoder runs on ATtiny88 and ATmega328P and uses the existing LPX
synthesis arithmetic. The host encoder consumes a current LPX analysis model.

The implementation includes:

- Adaptive contiguous coefficient groups, delta mantissas and one shared
  exponent per group. The encoder counts all group and exponent overhead.
- Independent constant, linear or literal runs for pitch and excitation level.
  Level curves use true log2 of the integer excitation step. Pitch curves use
  linear delay; they do not imply a linear change in Hertz.
- Closed-loop coefficient anchors, stability checks for every interpolated
  filter, a bounded byte reader and the original P4/P6 excitation packets.
- An explicitly selectable C implementation on each target. Existing assembly
  helpers require both the supported architecture and `LPX4_ENABLE_ASM=1`.

Filter order remains ten. Group size, mantissa width, exponent and trajectory
duration adapt independently. See [FORMAT.md](FORMAT.md) for the bitstream and
[the measured comparison](../../research/lbg1-2026-11-26/README.md) for results,
reproduction commands and limits. Production LPX files and players are unchanged.

The first comparison does **not** justify replacing current LPX: LG1 files are
larger and its complete player uses more CPU with the existing AVR assembly
backends. The experiment retains the unsuccessful measurements as well as the
working decoder.
