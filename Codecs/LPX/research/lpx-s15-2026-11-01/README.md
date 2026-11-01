# LPX-S15: experimental low-rate example

This is a separate research format, **version 8 / mode 15**. It is not v5,
is not accepted by the production decoder, and has no target firmware,
Flash, RAM, CPU, real-time or perceptual-quality admission. Its immediate
purpose is a third complete 8 kHz example near 1500 bit/s. It does not
change source level, sample rate, playback duration or transpose pitch.

Standard v5/P4 cannot reach that rate: 19200 samples require 4800 mandatory
pulse bits and 1800 parameter bits, even before spectra. The least expensive
legal first spectrum followed by repeats costs 81 bits. Including the
22-byte header and final padding, the lower bound is **858 bytes / 2860 bit/s**.
`test_s15.py` serializes this attainable lower-bound case.

## Container

The 22-byte little-endian header uses the existing `<4sBBHIHHHHH` geometry:
magic `L4HY`, version `8`, mode `15`, rate `8000`, output sample count,
deemphasis Q14, brightness Q14, parameter frame `320`, block `320`, and
payload bytes. Counts are 1..64000. Deemphasis is 0..16384; brightness is
0..11469. Unknown versions/modes are rejected. The payload is LSB first.

Each complete stored 320-sample frame contains:

- A v5-compatible ordered **6-bit** LSF spectrum: gap, delta or repeat,
  including the original bounded Rice escape and tie order.
- One scale (5 bits), pitch lag minus18 (7 bits), gain divided by2 (3 bits).
- Four 80-sample innovations. Each has a 6-bit position code and one sign
  bit. Position is `code + ((code + 2) >> 2)`, selecting 64 of 80 positions.
  Amplitudes are **-8 / +7**; this deliberately matches legal P6 amplitudes.

The fixed fields cost 43 bits/frame, or 1075 bit/s. All spectral fields,
header and final zero padding count toward the actual complete-file rate.
The final packet is stored completely even if its output tail is partial.
The experimental parser validates all stored fields and rejects extra bytes
and nonzero padding. It does not read extra audio to consume unused tails.

## Exact decoder bridge

Python and an independent C++ parser expand each S15 frame into ordinary
v5/P6, repeating its parameters over two160-sample halves. Each 80-sample
pulse becomes one legal P6 innovation and three zero-amplitude innovations.
Spectral values are unchanged by expansion. The expanded stream is only a
host reference; its larger size is never advertised as the S15 file size.

Existing common and v5-only native C decoders then supply the original
integer10-pole LPC, anchor interpolation, pitch feedback, saturation,
deemphasis, brightness and fixed PWM transfer. They are built with ASM off
and the original256-code history. Both complete native PCM/PWM outputs must
match the existing independent Python model. Native/Python expansion bytes
must match. No production core or math source is edited.

## Fixed example search

`encode_example.py INPUT.wav SEED_P4.lpx OUTPUT --compiler HOST_GXX` expects
the complete19200-sample mono8kHz target and its original-level v5/P4 seed.
Use a fresh ignored output directory. Required Python packages are those
already used by the active encoder; NumPy, Numba, SoundFile and metric tools.

There are exactly **nine** whole candidates: cadence4/5/6 parameter frames
crossed with deemphasis `{seed header,8192,11469}`, brightness0. Spectra hold
the original seed vector at each cadence boundary, projected by `P6=2*P4`.
There is no new initial LPC fit. Each320-frame tests only its two original
160-frame pitch lags (deduplicated), avoiding a new octave search. Gain
choices are0, maximum original seed gain,14. Scale choices are a residual
energy proposal plus/minus1 and the maximum seed scale plus2, deduplicated
and clamped. This gives at most24 parameter choices/frame.

For every parameter choice, all64 positions and both signs are rendered
through exact closed-loop synthesis for each80-sample pulse, with carried
integer state. A deterministic greedy pulse search minimizes full80-sample
PCM SSE; the resulting320-frame is compared on full320-sample SSE. Selected
frames and pulses are replayed and their work is counted. Maximum per
whole candidate:1440 parameter evaluations,768000 position/sign trials
including selected-frame replay, and6000 selected80-sample renders.

Every complete whole candidate is saved before continuing. The final rank
is full-record PCM SSE, actual bytes, candidate ordinal, among files at most
450 bytes. No cap padding is added. The winner is checked using both native
paths, reopened PWM-domain WAV, unchanged source/input hashes and full
PCM/PWM error metrics. Search/JIT/validation cost is reported; these are
offline costs, not decoder timing measurements. Numeric error/STOI results
are descriptive and do not establish audible equivalence or corpus benefit.

The separate `extend_cadence3.py` run checks exactly three new candidates at
cadence 3 and the same deemphasis settings against the saved incumbent. It
never repeats the completed nine candidates. All three occupied 443 bytes
(1,476.67 bit/s) but increased full PCM error; the final result remains the
417-byte incumbent (1,390 bit/s). The 12 candidates retain separate work
counts and source/input guards. All 19,200 PCM/PWM samples and both independent
expansion implementations were rechecked before publication. A lower bitrate
here does not imply equal intelligibility or preserved fine voice detail.

`test_s15.py --compiler HOST_GXX --output IGNORED_BUILD_DIR` runs synthetic
round-trip, tail, malformed-data, production-rejection and native/model
PCM/PWM contracts. All audio, libraries, input identities, hashes, search
rows and proof receipts remain ignored build artifacts. No MIDI is used.
