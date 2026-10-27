# Tiny Period ideas in LPX: isolated host pilot

**A learned period dictionary is feasible as a separate hybrid mode, but this
bounded pilot does not justify replacing the current LPX decoder.** No learned
period candidate improved quality within the already achieved v5 byte counts.
Production firmware, formats, defaults and arithmetic backends are unchanged.

## What was tried

Tiny Period stores a clip-specific dictionary of complete output-wave periods.
LPX instead applies an LPC filter to excitation. Feeding a complete Tiny speech
waveform through that filter again would repeat spectral shaping. This prototype
therefore learns **inverse-filtered excitation periods**, preserving the actual
quantized LPX spectra, LPC interpolation, scale fields and postfilters.

The isolated LPWB v1 host format stores 32 signed-nibble nodes per period,
continuous 16-bit phase, quantized pitch, gain and differentiated deterministic
noise. A 160-sample block chooses dictionary excitation or the existing LPX
pitch/pulse mode. Actual mixed excitation updates the prediction history;
consecutive dictionary blocks crossfade for 16 samples. The receiver needs only
the serialized stream, not source audio, analysis arrays or fitted phase tracks.

The encoder uses existing Tiny pitch/phase/harmonic analysis at an explicit
8 kHz, then bounded closed-loop integer block search. Dictionaries are trained
on each encoded segment, quantized, made exactly zero-mean, and pruned to active
entries. All headers, dictionaries, phase/mode bits, fallback fields and padding
count toward complete-file size. Eight full entries cost 128 bytes before any
frame data. EEPROM placement would not eliminate this information cost.

Current LPX already exploits periodicity through delayed excitation and pitch
gain: it has an adaptive waveform history without a transmitted static book.
An additional static dictionary must earn its overhead.

This is a project prototype inspired by the general approach in
[Gottesman and Gersho, Enhanced Waveform Interpolative Coding at Low Bit-Rate
(2001)](https://scl.ece.ucsb.edu/sites/default/files/publications/e01_9_0.pdf)
and [Kleijn, Yang and Deprettere, Waveform Interpolation Coding with Pitch-Spaced
Subbands (1998)](https://www.isca-archive.org/icslp_1998/kleijn98_icslp.pdf).
The papers motivate periodic/nonperiodic handling, phase and analysis by
synthesis; their reported quality or bitrate is not a result for LPX.
No paper code or book examples were copied.

## Pilot and controls

Baseline commit: `3680f86c`. Twelve anonymous speech cases, 16 contiguous
segments, 105.067 seconds, six Russian/six English cases, with natural, quiet,
noisy and prepared material. This is a small selected pilot, not the whole
181-case corpus or a held-out evaluation of a shared dictionary.

Both 4/6 profiles used the strongest retained selected v5 stream. Thirty-two
baseline segments were verified against the current native decoder, independent
integer model and saved PCM/PWM. Candidate models used K=4/8, two rate weights
0/.05, and K=0 **zero/noise-only ablation**. The final run fitted 192 streams,
representing 144 joined case/profile/parameter candidates, with 2,823,970
objective evaluations. Original segment joins, levels and full lengths were
preserved; gain fitting and delay fitting were not used.

Quality floors require no increase in full-reference PCM/PWM SSE and no decrease
in available PCM/PWM STOI (absolute numerical tolerance 1e-10). Actual existing
bytes and configured per-segment caps are separate scenarios. Baseline v5
remains eligible; raw metric tradeoffs are recorded even when not adopted.

## Result

- Under achieved stream sizes, selection retained v5 in 23/24 case/profiles.
  The remaining result is reproducible by K=0 alone. Its 1084 to 1000 byte
  reduction uses 20 silent blocks and **zero active learned periods**.
- Under configured caps, selection retained v5 in 22/24, chose that same
  ablation once, and chose K4 once.
- The distinct learned-period result activates only two blocks. It improves
  PCM SSE by about 0.1025% and slightly improves both STOIs, but grows the
  existing stream from **23262 to 25272 bytes** (+2010, +8.64%). This is a tiny
  metric improvement with a data cost, not a firmware-size improvement.
- Rate penalties can reduce bytes, with quality losses on other candidates.
  Of 144 raw candidates, 26 passed all quality floors, three also fitted
  achieved bytes (the same silence-equivalent output), and 21 fitted configured
  caps, including baseline-equivalent results with extra data.

Totals below cover all twelve cases. SSE is in billions; STOI is a case mean,
not a listening score.

| Profile | Variant | Complete bytes | PCM SSE | PCM STOI |
| --- | --- | ---: | ---: | ---: |
| 4 | Existing v5 | 47876 | 1170.305 | .719741 |
| 4 | K4, weight0 | 52530 | 1194.375 | .693852 |
| 4 | K8, weight0 | 52046 | 1223.889 | .671065 |
| 6 | Existing v5 | 68427 | 793.519 | .763628 |
| 6 | K4, weight0 | 72133 | 796.511 | .732133 |
| 6 | K8, weight0 | 71651 | 795.244 | .724727 |

[summary.json](summary.json) retains source/dependency hashes, protocol,
aggregates and decisions. [case-results.csv](case-results.csv) preserves all
168 baseline/candidate rows, including spectral/PWM metrics, byte accounting and
active-period counts. Fitted dictionaries, source paths, audio, payloads and
raw private manifests stay in ignored local build folders.

## Status and next design choices

Thirteen synthetic test groups pass: native legacy parity, independent
phase/noise/mixed arithmetic, strict container validation, partial/max tails,
roundtrip, deterministic fitting, stale-analysis rejection and validation even
when analysis is reused. The active LPX source tree is unchanged.

LPWB is **host research only** and is not accepted by the active firmware.
No AVR Flash/SRAM/cycles or active-IRQ admission is claimed for this new format.
The pilot does not establish a useful data advantage that would yet justify
paying for a second firmware parser/generator. Its file-byte results cannot be
substituted for total firmware measurements.

This first fitter freezes LPC spectra and uses a greedy 20 ms horizon with
limited phase/gain proposals. Broader joint phase/dictionary/spectrum search
could change the result. Direct Tiny output periods with a separate LPC bypass
are another untested design: switching, filter state and consonants must be
designed together. Naturalness requires listening alongside numeric metrics;
no human ratings were collected here.

## Reproduce

Use the existing LPX Python requirements and a native C++ compiler. Put active
LPX tools/tests plus this study's prototype/tests on the import path through:

```text
python Codecs/LPX/research/period-excitation-2026-10-27/run.py test
python Codecs/LPX/research/period-excitation-2026-10-27/run.py benchmark PRIVATE_MANIFEST build/period-pilot --limit-cases 1
```

Remove `--limit-cases` for the complete private pilot. The input schema is
`lpx-period-pilot-private-v1`; original references/caches are required and are
not distributed here. The benchmark restricts generated artifacts to ignored
repository build storage and writes anonymous reports. No optimization replaces
a baseline automatically. The numerical and native environment is fingerprinted
with each run.
