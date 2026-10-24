# Independent sinusoidal source: PC prototype

`sin_partials.py` and `tools/probe-sin-partials.py` are a separate research
source model, not AVR firmware. They automatically select the strongest three
or ten local spectral peaks per analysis frame and follow stable IDs through
birth, death, and short gaps. A global least-squares fit chooses one phase and
amplitude scale per track against the raw original. No original waveform or
uncompressed residual is retained.

Frequency is linear in Hz between knots. Phase is its continuous integral,
including across knots and silent gaps; it is never reset at an interior knot.
Positive amplitude runs are linear in dB. Zero-amplitude transitions are kept
explicitly; a silent gap cannot be filled by interpolation. Birth/death fades
can temporarily overlap old and new IDs, so three selected peaks per analysis
frame do not imply a strict three-oscillator execution limit between frames.

Adaptive knots use recursive maximum normalized frequency/level deviation.
Endpoints, positive-run boundaries and zero transitions are mandatory. A
direction or slope change is kept when its interpolation error is material.
This is a deterministic error-bounded path simplifier, not a fixed-rate sampler.
The report measures the actual reconstructed path error after quantization;
requested prequantization tolerances are not claimed as final bounds.

Two independently decodable serializations are provided:

| Format | Frequency | Level | Point time | Initial phase |
|---|---|---|---|---|
| `SP01` | 1-Hz integer delta, zigzag varint | 8-bit linear amplitude, or paired 4-bit | frame-delta varint | 8-bit per track |
| `SP02` | log-grid index, 32 entries/octave | 1-dB attenuation index, 255=silence | frame-delta varint | 8-bit per track |

`SP02` has a 25-byte header: magic, sample rate, complete sample count, hop,
analysis component count, bins/octave, level-step quarters, track count, minimum
frequency, and raw amplitude maximum. The minimum frequency is sample-rate/128;
at 7500 Hz the six-octave range has 193 indices through Nyquist. Grid rounding
alone is bounded by 18.75 cents and 0.5 dB. Final rendered peak errors also
include interpolation, phase, interference and analysis errors.

Each track stores knot count and initial phase. The first knot stores time,
absolute frequency index and level. Later knots use time delta plus paired
signed four-bit frequency/level deltas with absolute-byte escapes. Track IDs
are implicit in track order. The report accounts for every header, phase,
time, first-point, packed-delta and escape byte. After frequency quantization,
initial phases are refitted automatically while frequency and level stay fixed.

All payload sizes exclude the PC decoder, its floating-point runtime and RAM.
For a future MCU implementation, a single-octave 32×16-bit phase-increment table
would cost 64 bytes rather than a complete 193×16-bit 386-byte table; octave
shifts could extend its range. This is only a design estimate. No AVR cycles,
Flash fit, lookup placement, or combination with the existing EEPROM bell
table has been qualified.

Quality reports separate raw reconstruction residual energy and absolute
partial levels from globally RMS-matched diagnostics/listening. Every selected
original partial is checked against ±5 dB; a missing peak is a violation. A
second check adds a 50-cent bound. Good average errors do not override those
all-point checks. Three or ten sines omit substantial unvoiced and weaker speech
detail; no naturalness or mathematical-exactness claim is made.

Run `tools/test-sin-partials.py` for material turning points, phase continuity,
silent gaps, log-grid roundtrip, truncation handling, and exact byte accounting.
