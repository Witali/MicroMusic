# Independent local-noise experiment tests

Run from the repository root in Linux/WSL with the installed g++ toolchain:

```sh
python3 -m unittest discover \
  -s Codecs/LPX/experimental/local-noise/tests -p test_local_noise.py -v
```

The standard-library Python harness reads the production host build composition,
adds the experimental scorer and independent test driver, and records compiler,
source hashes and results under ignored `build/local-noise-independent-tests/`.
Before/after hashes reject source changes during compilation. No production
encoder, decoder, wire format, WASM or hardware configuration is edited.

Four test groups cover:

- An independent direct DFT of the defining 512-point Hann transform, source
  magnitudes and squared positive interharmonic excess; fixed source descriptors
  across candidate evaluations; harmonic versus interharmonic errors at similar
  SSE, and a prospective local SSE/noise preference reversal.
- Quiet, unvoiced, transient and unsupported-window fallback at 8/12/16 kHz;
  deletion of real source energy remains costly. PCM does not compute a PWM
  path; the two-path PWM score is checked against an independent integer PWM
  transfer and the same source masks. Invalid inputs/targets are rejected.
- Fixed actual packet size, every non-pulse field and continuation history,
  legal P4/P6 symbols, untouched out-of-play tail symbols, actual native decode,
  deterministic results/counters and the fixed region/pair/evaluation bounds.
- Separately admitted noise and active-SSE bundles against the same baseline,
  including actual admitted changes. The test independently checks active SSE,
  STOI, old noise, full-band, clipping, stability, level and spectrum floors.
  A real 1280-sample prefix is assembled with each refined continuation and
  checked sample by sample by the native decoder through EOF. Played malformed
  P4 zero amplitudes and unstable quantized predictors are rejected before search.

The active-SSE control uses the shared candidate pool, including its noise-ranked
first-pulse finalist; this is a paired ranking ablation, not a wholly noise-free
encoder. The new metric ranks proposals locally and is not an additional global
admission floor. These are synthetic correctness checks, not evidence of a
corpus quality gain, audible preference, physical-board behavior or AVR CPU cost.
