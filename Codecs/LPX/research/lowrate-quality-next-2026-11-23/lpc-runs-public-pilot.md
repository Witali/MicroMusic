# Quantized LPC-run proposals: public pilot

The bounded operator improves 10 of 24 settings on the three previously public
tuning phrases, measured against complete V3 winners from `ba02e453`. Fourteen
winners remain unchanged. This is development evidence, not a new heldout test
or a listening claim. [Anonymous numerical results](lpc-runs-public-pilot.json)
include component regressions, missing memberships, bytes and runtime.

The existing `refineLpc()` edits individual 320-sample spectra and ranks/refits
primarily by waveform error. Its complete SSE floors cannot explore every
useful spectrum/time tradeoff. At low rates, editing one frame inside a held
spectrum can also replace a cheap repeat packet with a larger update.

The new `proposeLpcRuns()` edits a whole existing run of identical quantized
spectra. It changes one coordinate by -1 or +1, retains strict ascending order
and the existing P4/P6 alphabet, and preserves the run's internal repeats.
Parameters, extra pulses, pre-emphasis, brightness, rate and headers remain
unchanged. The previous complete winner stays available to the caller.

The constants were fixed before this pilot: four runs ranked by original
sample-error energy; 20 coordinate shapes at most per run; two shortlisted
shapes; a 1280-sample local horizon; and a 160-sample pulse neighborhood. Pulse
refitting uses the existing small search neighborhood: positions within two
samples, P4 signs, or P6 amplitudes within two steps. The operator returns at
most the best raw shape and best joint shape per run, eight unguarded proposals.

Local ranking reuses `FullBandContext` magnitude and magnitude-change errors at
the actual rate. Its fixed source/trajectory crop is an approximation, including
its edge padding. Only the unchanged complete-output objective and safety rules
admit a proposal. The real ordinary/Long cap is checked before return; there is
no fitted gain, delay, denoising or new decoder state or side information.

Exact unchanged prefix states are advanced once in time order. A compact copy
of preceding-spectrum metadata reproduces coefficient interpolation through
the local window using the existing `coefficientTrace()`. Local trials synthesize
only their bounded suffix. Complete final verification includes the whole run
and the later audio suffix. Tests cover repeated runs, transitions, rates,
profiles, caps, partial packets and Long streams: 144 cases, 102 exact coefficient
and prefix slices, and 258 legal unguarded proposals passed.

One of the three 3-kbit/s settings improves from joint score 1 to
0.9923343449 at the same 887 bytes. Its balanced spectral error falls about
2.1%, temporal error 1.5–1.6%, and STOI rises about 0.0024 on PCM and PWM.
Waveform error rises about 0.35%; some voice, noise and shape components also
worsen. These are objective tradeoffs, not an audible-quality percentage.

The largest public 8-kbit/s score reduction is about 3.6%; it consumes one extra
byte within the unchanged cap. One P4-at-16-kHz result saves one byte. Other
admitted outputs keep their size. Nine accepted edits touch one-frame runs,
and only one touches a two-frame run. Thus this pilot does not establish a
special held-run advantage at 3 kbit/s despite the operator preserving repeats.

Single native runs take 0.048–0.178 seconds for proposal generation, or
0.167–0.553 seconds including complete proposal evaluation. These are host
observations, not paired performance benchmarks or MCU timing measurements.
Decoder source, arithmetic, Flash and RAM requirements are unchanged by this
host-only module. All individual media, identities, bindings, source hashes,
paths and detailed receipts remain under ignored build storage.
