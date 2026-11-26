# Local excitation selection with a source-frozen noise score

The fixed experiment found **no admitted quality or size improvement** over the
current LPX encoder. Every final LPX file, decoded PCM and model is identical to
its own baseline in 16 speech cases and four held-out synthetic cases. Keep the
current production encoder. This result applies to the bounded search and score
below; it does not rule out other excitation searches or perceptual criteria.

This is an optional standalone host experiment. No production encoder, decoder,
wire format, WASM, Web UI, firmware or build composition is changed. It starts
with a completed `encodeAccuracy(..., calls=4)` stream from pinned revision
`644e19d0fd8db47fcae7d6ad64787d6c89ead28d` and changes only existing main pulse
positions and amplitudes. Coefficients, pitch, scale, extra pulses, headers and
continuation state stay fixed. All proposals preserve the exact complete byte
count. Consequently this experiment tests quality at fixed size; it cannot
demonstrate a bitrate saving by construction.

## PCM and PWM comparison

Four complete public clips at 8 kHz, each at accuracy levels P4 and P6, give eight
files per quality target. Every PCM case has a freshly encoded PCM baseline;
every PWM case has a freshly encoded PWM baseline. All eight PWM baseline LPX
and decoded PCM hashes match the retained current-LPX controls. There is no
source-specific gain fitting, delay fitting or loudness normalization.

| Quality target | Current LPX total | Final noise selection | Mean active-path STOI, current → final | Changed files |
| --- | ---: | ---: | ---: | ---: |
| PCM | 8,867 B | 8,867 B (0%) | 0.747592 → 0.747592 | 0/8 |
| PWM | 8,587 B | 8,587 B (0%) | 0.746626 → 0.746626 | 0/8 |

PCM STOI is reported on the PCM path; PWM STOI is reported on the static PWM
path. PWM admission checks both PCM and PWM paths. Post-hoc PWM measurements in
PCM cases do not participate in PCM selection. Different PCM/PWM baseline sizes
come from target-specific existing encoding decisions, before this experiment.

| Clip | Accuracy | Current = final, PCM | Current = final, PWM |
| --- | --- | ---: | ---: |
| chego | P4 | 522 B | 522 B |
| chego | P6 | 937 B | 937 B |
| otvechaesh | P4 | 545 B | 545 B |
| otvechaesh | P6 | 671 B | 671 B |
| vinni | P4 | 1,485 B | 1,200 B |
| vinni | P6 | 2,234 B | 2,239 B |
| bread | P4 | 994 B | 994 B |
| bread | P6 | 1,479 B | 1,479 B |

The best generated changed noise bundle from each case was also retained
**before admission**, including bundles worse than the baseline. These raw
proposals are useful for diagnosing the tradeoff, not accepted improvements:

| Target | Mean new score, baseline → raw | Score change | Aggregate active SSE change | Mean active-path STOI, baseline → raw |
| --- | ---: | ---: | ---: | ---: |
| PCM | 0.136836 → 0.134623 | −1.62% | +0.364% PCM | 0.747592 → 0.745498 |
| PWM | 0.139682 → 0.137857 | −1.31% | +0.781% PCM + PWM | 0.746626 → 0.743957 |

The score percentages compare means across eight files; SSE percentages compare
sums of sample errors. The score combines magnitude mismatch and interharmonic
excess. A lower score is not a measured percentage reduction in audible noise.
No human listening preference or physical PWM-board improvement is established.

Of 125 complete generated bundles across both ranking branches, 97 first failed
the active SSE/STOI floor and 28 first failed the full-band guard. None reached
final admission. These are first-failure categories, not mutually independent
quality diagnoses. All native decode, byte count, stability, level and spectrum
checks passed. The independently admitted active-SSE control also returned all
eight original files in each target.

## Fixed score and bounded search

All constants and held-out signals were defined before the two-case pilot.
Pilot, matrix and held-out runs use identical code hashes and the same compiled
binary. No constants or acceptance thresholds were adjusted from the results.

The source is analyzed once with a 512-sample Hann FFT, hop 256, at the native
8/12/16 kHz rate. An 80 ms source-only period estimate defines harmonic
neighborhoods, with half-width `min(1.5 FFT bins, F0/4)`. An interharmonic penalty
is enabled only when the entire source analysis window is available, source RMS
is at least 64 in PCM16 units, fractional-lag correlation is at least 0.75,
four 20 ms slice energies have a max/min ratio at most 4, and at least 70% of
source AC power lies in the harmonic neighborhoods. Quiet, unvoiced, transient
and unsupported windows retain the ordinary magnitude term with a zero
interharmonic mask. DC is never marked interharmonic.

For each window and active output path, let `R[k]` be the frozen source magnitude,
`C[k]` the candidate magnitude, and `w[k]` the real-FFT power weight (one at
DC/Nyquist, two elsewhere). The source-only normalization is
`N = max(sum(w R²), 512 * sum(Hann²) * 64²)`:

```text
M = sum(w[k] * (C[k] - R[k])²) / N
E = sum(off_harmonic[k] * w[k] * max(C[k] - R[k], 0)²) / N
J = mean_over_windows_and_active_paths(M + 2 * E)
```

Candidates cannot change the source F0, mask, magnitude or normalization. Missing
real source energy still costs magnitude error. PCM evaluates one output path;
PWM evaluates PCM and the existing integer `pwm()` transfer, using the same
source analysis. This PWM model has centered 8-bit quantization and gain 130;
it does not model carrier timing, analog reconstruction or hardware capture.

The search selects at most four disjoint regions, four main-pulse pairs per
region, and three FFT scoring windows per region. A trial synthesizes at most
808 future samples after alignment to a pulse-pair boundary. Original baseline
prefix states are recovered exactly; another region's unadmitted edits never
enter a trial's starting state. Legal P4/P6 first pulses are enumerated and
shortlisted by active-path SSE, retaining the incumbent and PCM-SSE finalist.
At most four first choices, including a noise-ranked finalist, receive a second
pulse search. The top eight active-SSE candidates plus the incumbent and PCM
finalist receive the new score. Each ranking forms up to four distinct bundles:
all, half, quarter and one of its beneficial patches.

The active-SSE control selects from the **same shared candidate pool**, including
the noise-ranked first-pulse finalist and noise-based region selection. It is a
paired ranking ablation, not a wholly noise-free SSE-only encoder. Noise and SSE
bundles are admitted independently against the same completed LPX baseline; an
SSE-only win cannot silently become the noise result.

Final admission requires exact size, native/model decode identity, stable LPC,
safe synthesis level/spectrum, explicit non-regression of active-path SSE and
STOI, existing full-band acceptance, no worsening of the existing noise metric,
and the existing complete quality selector, including pitch/clipping guards.
The new score ranks local proposals; it is not an extra whole-output admission
floor. A final output need not minimize that diagnostic. Search selection
objective counters left at zero when no bundle reaches the complete selector
are not measured zero-error quality; use `outputs` for actual measurements.

Source voiced masks were active in 14/40 windows for chego, 5/35 for otvechaesh,
3/94 for vinni, and 0/76 for bread, identically across targets and accuracies.
The sparse voiced coverage limits conclusions for general speech; bread's
proposals are driven by the magnitude term. Two deterministic one-second P6
controls at 12/16 kHz exercise harmonic, noisy, high-band and transient content;
their voiced masks cover 39/48 and 51/64 windows. All four held-out finals and
controls also equal their own baselines (PCM total 2,525 B; PWM 2,344 B).
Of their 32 bundles, 26 first failed SSE/STOI and six first failed full-band.
Synthetic STOI values are diagnostics, not speech intelligibility evidence.

## Cost and validation

On this host with g++ 13.3.0, `-O3 -std=c++11 -ffp-contract=off -DNDEBUG`, summed
baseline wall time was 29.648 s for PCM and 42.695 s for PWM. The additional
refinement took 1.878 s (+6.34%) and 2.898 s (+6.79%). This includes shared search,
raw bundle rendering and both independent final admissions. These single-run
host measurements are not a production encoder overhead estimate for a version
with only one branch. `synthesized_samples` counts local candidate forward
renders, excluding prefix walks and complete renders; `full_evaluations` counts
explicit admission pre-screens, excluding the common selector's internal work.

The decoder code and final bitstreams are unchanged. The experimental criterion
runs only on the encoding host. There is no additional decoding work for these
outputs on ATtiny88 or ATmega328P. No new AVR timing, interrupt/underrun, memory
or hardware support measurement was made; equal byte count alone would not
prove identical cycles for a changed pulse stream.

Four independent test groups pass: a direct-DFT numerical oracle and source-mask
immutability; fallback/target contracts at 8/12/16 kHz; bounded fixed-byte legal
search and native decode; and whole-output admission with real prefix/suffix
continuation. Synthetic admission tests include actual accepted edits, so the
zero corpus acceptance is not caused by a permanently disabled selector.
Played malformed P4 zero amplitudes and unstable predictors reject before
search. See [tests/README.md](tests/README.md).

[validation.json](validation.json) records 330 verified artifact hashes across
22 cases (pilot repeats two primary cases), identical frozen build inputs,
62 production inputs pinned to the baseline, and six source-descriptor sets.
The report files retain each source/LPX/PCM/model hash, all five variants, source
masks, PCM/PWM metrics, timing and rejection counters:
[pilot](results-pilot.json), [speech matrix](results-matrix.json),
[held-out controls](results-heldout.json). Generated media and binaries stay in
ignored `build/local-noise/`.

## Reproduce

Run from the worktree root in Linux/WSL with Python 3 and g++ installed. These
commands use standard-library Python and existing repository sources:

```sh
python3 Codecs/LPX/experimental/local-noise/prepare_sources.py
python3 -m unittest discover -s Codecs/LPX/experimental/local-noise/tests -p test_local_noise.py -v
python3 Codecs/LPX/experimental/local-noise/compare.py --phase pilot
python3 Codecs/LPX/experimental/local-noise/compare.py --phase matrix
python3 Codecs/LPX/experimental/local-noise/compare.py --phase heldout
python3 Codecs/LPX/experimental/local-noise/verify_results.py
python3 Codecs/LPX/experimental/local-noise/make_listening.py
```

The default `frozen-v1` artifact directory refuses a replacement with different
bytes. For a separate run, select `--run NAME` and an explicit `--output` JSON
under this experimental directory. A partial `--case` run is not the full
matrix. Reproduction updates the requested report's timing/build provenance;
keep the committed frozen reports when comparing reruns. `verify_results.py`
checks the complete frozen three-phase reports and matching local test receipt.
Listening WAVs preserve level and use the target's output path; `raw-noise.wav`
is explicitly unadmitted. Baseline and final WAVs are identical in this run.
