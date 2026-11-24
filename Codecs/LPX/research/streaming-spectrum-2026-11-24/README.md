# Preventing false LPX source-spectrum rejection

Baseline: `0b02d12dd7d18bf37897e9e0c8675d2f46503c8b`.
The wire format, decoder and shared integer synthesis arithmetic are unchanged.
Private recordings, paths, fingerprints and per-recording measurements are
excluded; retained regressions use generated sources only.

## Cause and correction

The source-spectrum recovery trigger used unwindowed RMS eligibility but
compared Hann-windowed spectra. An attack near an FFT window edge could make
raw energy exceed the64-count floor while its Hann-weighted energy was almost
zero. Normalizing that near-silence then rejected every model and exhausted
the32-fit recovery budget with required-seed error `-7`.

Eligibility now uses `sum((source*Hann)^2) / sum(Hann^2) > 64^2`.
The existing shape/off-band thresholds remain unchanged. The portable
contract tests edge attacks, significant unrelated energy, polarity and the
correct denominator immediately above the floor. It distinguishes both the
old raw-energy bug and a mistakenly unweighted denominator.

Actual-Q12 and rendered level/clipping safety remain mandatory. Target-compliant
models retain priority. If the local spectral target is unattainable after the
bounded search, the required lossy seed retains the least actual PCM/PWM
magnitude/temporal-error model among all hard-safe attempts, including ordinary
analysis. Perceptual target failure alone no longer invalidates every legal
reconstruction. Refinement admission still applies the spectrum guard.

An explicit original-seed status additionally lets streaming discard an unsafe
optional refinement while retaining its complete independent control. Generic
kernel/CUDA/argument/verification failures still propagate. No waveform/state
splicing, output truncation or source-specific frequency rule is introduced.

## Validation

The existing LPX suite completed176 tests:162 passed,14 optional helper checks
skipped, zero failures. Native CPU/CUDA and scalar/SIMD artifacts match all
recorded source inputs. The84-source-case comparison against the baseline has
unchanged aggregate bytes, spectral error and envelope error, with no
substantial regression. This is not a throughput or transparency claim.

The new anonymous burst source reproduces baseline `-7` in whole and streamed
encoding. A20528-sample version crosses a20480-sample boundary; an independently
failing8321-sample prefix bounds refined-search test cost. P3/P4/P6/P8,
8/12/16 kHz, calls0/4 and whole/stream transport form48 quality cases.
Assertions cover complete sample count/EOF, spectrum, envelope, energy and
significant partials. Existing bell/attack/tail thresholds are unchanged.
All48 cases pass, and both fixture/floor contracts pass separately. In the
24 fast cases every output retains all four significant partials; the worst
spectral error is.1586 and envelope error.1107, with energy ratios.5813–.9352.
These are generated-source measurements, not guarantees for arbitrary audio.

Full private-recording checks also completed locally through the actual shared
FIR and continuous encoding, with complete independent sample/EOF verification.
The previous failing contexts now admit the ordinary reconstruction unchanged.
Private media and individual recording results are not distributed.

## Automatic regression checks

[LPX quality regression](../../../../.github/workflows/lpx-quality.yml) runs on
relevant pushes and pull requests. A portable native job builds the shared
production source composition and spectrum/ownership contracts. Three independent
Node22.22.3 jobs check the maintained quality matrix, one sample rate per process.
Actions are pinned to verified official v6 commits, credentials are not persisted,
permissions are read-only, and no recording or test media is uploaded.
These checks report regressions; repository branch protection is not changed.

```powershell
node web-player/scripts/build-lpx-unification-tests.mjs --emsdk C:/path/to/emsdk
$env:LPX_UNIFICATION_SELFTEST='1'
node --test --test-name-pattern='spectral safety|burst sources' web-player/tests/lpx-continuation-safety.test.mjs
node --test --test-name-pattern='/8000/' web-player/tests/lpx-continuation-safety.test.mjs
node web-player/scripts/benchmark-lpx-timbre.mjs --baseline 0b02d12dd7d18bf37897e9e0c8675d2f46503c8b
```

Production builds use the existing pinned Emscripten6.0.12/Clang24 with
`-ffp-contract=off`, portable C++11 wasm32 and C++17 native CPU/optional CUDA.
No handwritten assembly or MCU timing support is claimed.
