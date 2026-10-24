# Three independently controlled partials: bounded PC proof

This separate prototype tests the requested source representation: automatic
stable partial IDs, adaptive frequency/loudness knots, linear-Hz frequency,
linear-dB positive amplitude, explicit births/deaths/silent gaps, and phase
continuous through every knot. It also tests logarithmic frequency indices and
actual delta/nibble source serialization. No AVR implementation is claimed.

The reference is the complete **12800-sample, 1.706667-second** tail voice at
7500 Hz, starting at sample 6528 (0.8704 seconds) of the 19328-sample final
bell-plus-voice excerpt. No new cropping or time compression occurs. Input
provenance links the external original and prior preparation report.

## Counts and actual storage

Three strongest peaks per analysis frame become 44 stable IDs and 527 dense
trajectory points over the utterance. Birth/death fades can overlap: the maximum
active fading-track count is six, not a certified three-oscillator MCU limit.
The ten-component control has 116 IDs, 1667 dense points and up to 17 overlapping
fading tracks.

| Serialized source | 3-component bytes | 10-component bytes |
|---|---:|---:|
| Dense linear-Hz, 8-bit amplitude | 1518 | 4774 |
| Tight adaptive log grid | 1207 | 3713 |
| Medium adaptive log grid | 1157 | 3518 |
| Loose adaptive log grid | 1034 | 3105 |

These are complete source payloads **excluding decoder code and runtime memory**.
Even the 1034-byte three-component payload exceeds all of ATtiny13A Flash before
adding playback code. The result supports moving toward small corrections to
the existing Q3 voice rather than treating these trajectories as a compact
standalone replacement.

The log format uses 32 indices per octave, 193 frequency indices over six
octaves, one-dB levels, eight-bit initial phase per ID, and signed nibble deltas
with absolute-byte escapes. Grid rounding alone is at most 18.75 cents and
0.5 dB. Interpolation and rendered-peak errors are measured separately.

For the 1034-byte source (348 adaptive knots), the exact layout is 25 header
bytes, 44 initial phase bytes, 44 knot-count bytes, 348 time-varint bytes, 44
first-frequency indices, 44 first levels, 304 packed delta bytes and 181 escape
bytes. IDs are implicit in track order. Header parameters and all birth/gap
points are included. There is no hidden waveform or uncompressed residual.

## Fidelity and strict original-peak bounds

The unquantized three-component model closely controls the strongest selected
partials: mean absolute frequency error 4.46 cents / 1.24 Hz, mean absolute raw
level error 0.912 dB, and 96.34% selected-reference-power coverage. Nevertheless
the all-point ±5 dB check fails **81 of 303 peaks**: 56 missing plus 25 matched
level violations, representing 5.07% of selected original power. Good mean
error does not make that strict requirement pass.

The tight 1207-byte log model has mean raw errors 10.32 cents and 0.956 dB; it
still fails 84/303 selected peaks, with 59 missing and 5.72% violating power.
The loose 1034-byte model fails 91/303, with 65 missing and 7.16% violating power.
All tested variants fail the requested all-point ±5 dB bound. A separate stricter
frequency-plus-level check also remains in the report.

Raw least-squares reconstruction explains 45.40% of original squared signal
energy for three components and 52.63% for ten. The rest is measured as residual,
not copied into the format. Whole-voice STOI is only 0.426/0.530, compared with
about 0.837 for the existing 430-byte Q3 voice. Three dominant sinusoids omit
weaker formants and aperiodic consonant detail; increasing to ten does not solve
the complete speech problem.

Quantized frequency curves change integrated phase. Automatically refitting
one initial phase per ID helps, but does not recover the omitted signal. The
tight log models explain 33.41%/37.83% by raw residual energy and have STOI
0.419/0.534. The source's frequency parameters are independent controls; finite
window peaks in their summed output are still affected by chirps, overlap,
interference, and quantization. Neither numerical exactness nor naturalness is
asserted.

The report separates raw absolute-level checks from global RMS-matched listening
and diagnostic checks. For example, the tight three-component output has raw
RMS 0.6644 times the original; global RMS matching raises its selected-partial
mean level error from 0.956 to 3.190 dB. That normalization is not used to conceal
the raw errors or claim a bound.

## Retained material and reproduction

`tail-voice/` contains the complete research report, raw parameter models, and
actual independently decodable `SP01`/`SP02` payloads. Six retained log payloads
were independently decoded and their PCM hashes checked. Generated audio stays
in ignored `build/sin-partials/final-tail-voice/`. `listen-3-vs-10.wav` is original
→ unquantized three → tight-log three → tight-log ten, with a shared listening
filter/RMS/peak process. It is an explanation of capacity limits, not a proposed
replacement for the current site firmware.

```powershell
python tools/probe-sin-partials.py --reference build/new-speech/bell-hybrid/voice-reference.wav --output build/sin-partials/reproduce --components 3 10
python tools/test-sin-partials.py
```

Four tests verify material turning points, nested looser simplification,
continuous phase at a chirp reversal, silent-gap preservation, actual log-grid
roundtrip, truncation rejection, and exact byte accounting. Firmware Flash,
EEPROM placement, execution cycles and hardware playback remain unqualified.
