# Integer speech output DC removal

The output stage removes constant offset and slow baseline drift without
forcing equal positive and negative waveform peaks. Natural speech cycles can
be asymmetric even when their mean is zero. The output midpoint is PWM 128.

The exact portable implementation is `codec/dc_blocker.py`. It requires two
persistent state bytes, signed 16-bit intermediate arithmetic, arithmetic
right shifts, and saturation after the state update:

```text
estimate = (state + 2^(shift-1)) >> shift
y = (PWM - 128) - estimate
state += y
PWM = clamp(y, -128, 127) + 128
```

Rounding uses ties toward positive infinity. The state integrates the
unclipped result. The tight reachable state bounds are
`[-128*2^shift + 2^(shift-1) - 1, 127*2^shift - 2^(shift-1)]`.
For supported shifts 5/6/7, every intermediate fits signed 16-bit. Clipping
can still occur at sudden baseline changes, so the encoder must evaluate
the exact postfilter and reserve headroom instead of silently wrapping.

State must persist across streaming chunks and repeated phrases. Reset only
at a new playback. After the final sample, feed signed zero/PWM 128 through
the same stage until the tail settles; jumping straight to PWM 128 can cause
a click. These test phrases already end with enough quiet samples to settle.

At 7500 Hz, shifts 5/6/7 have pole frequencies approximately 37.9/18.8/9.4 Hz.
Shift 7 is the conservative default because it preserves the accepted sound
and STOI most closely on the three approved floating-model outputs. It is
also inexpensive to implement on AVR: copy the 16-bit state, add 64, then
`lsl` the low byte and `rol` the high byte. The resulting high byte is the
signed estimate. No multiply or seven pairs of arithmetic shifts is needed.
This is an implementation suggestion, not an assembled code-size claim.

The retained `quality.json` evaluates both the approved floating model rounded
to 8-bit PWM and a fresh phase-4 integer conversion without retuning. It
compares all three shifts at full amplitude and explicit 7/8 input gain,
checks three phrase loops with 250 ms leading/trailing silence, and records
source/input hashes and package versions. The global mean and sliding 100 ms
mean are measured independently of the existing spectral objective's 70 Hz
highpass. The sliding-mean/RMS ratio is independent of playback level.

Approved floating model, full amplitude, shift 7:

| Clip | Mean PWM LSB before → after | STOI before → after | 100 ms mean RMS / signal RMS before → after |
| --- | --- | --- | --- |
| chego | -0.0372 → 0.0004 | 0.908628 → 0.907663 | 0.00834 → 0.00574 |
| otvechaesh | -0.0325 → 0.0049 | 0.851747 → 0.851026 | 0.00610 → 0.00480 |
| vinni | 0.2804 → 0.0025 | 0.854854 → 0.854999 | 0.07633 → 0.02973 |

None of these three accepted outputs clips. The unretuned integer Vinni
conversion clips one sample at full amplitude (absolute peak 128 at the
positive limit); explicit 7/8 headroom eliminates it. Integer conversion has
other quality losses, so these results do not claim a finished AVR decoder.
For final encoding, search shift 5/6/7 jointly with model coefficients under
the STOI/spectral constraints, and reject clipping candidates. The DC blocker
must be inside the scored synthesis path, not added after optimization.

Reproduce from a checkout with scientific Python dependencies and externally
stored, hash-verified canonical originals:

```text
python tools/test-speech-dc.py
python tools/probe-speech-dc.py --report ATtiny13A/Sound/research/dc-output/quality.json
```

Temporary audio is written only under ignored `build/speech-dc/`. To measure
a retuned fixed model, add `--fixed-model chego=path/to/model.json` (repeat for
the other clip IDs). Six tests cover constant-offset removal, exact scalar
16-bit arithmetic, saturation, bounded states, chunk/loop equivalence, drift
attenuation, voice-band preservation, zero tails, and retained natural
waveform asymmetry.
