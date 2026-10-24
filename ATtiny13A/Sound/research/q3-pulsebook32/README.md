# 32-tap source: bounded Vinni study

This study did **not** reach STOI≥0.90 and spectrogram loss≤0.344975554.
It retains three exact candidates and a useful negative attribution result.
The complete source phrase is unchanged:22272 samples at7500Hz, SHA256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
There is no waveform normalization, time warp, manual frequency selection,
manual timestamp selection or output gain/DC correction.

| Candidate | STOI | eSTOI | Spectrogram loss | Stream | Complete Flash | EEPROM |
|---|---:|---:|---:|---:|---:|---:|
| Balanced |0.849533|0.659937|0.491184|620B|1024B|64B|
| Best STOI |0.849584|0.659632|0.492098|620B|1024B|64B|
| Best spectrum |0.833251|0.634396|0.477674|616B|1020B|64B|

All three use the402-byte floor decoder and T1. Each actual assembled image
matches the PC phrase and subsequent silence in all three existing AVR
engines:66816 verified output samples, zero mismatches, zero missed samples
and zero lost overflows. Minimum measured foreground slack is326,326 and
324 cycles respectively, including EEPROM waits and interrupts. These are
emulator measurements; no hardware test is claimed. All four arithmetic
wrap counters are zero. Complete Flash includes decoder, stream, EOF and
linker padding; the64-byte EEPROM contains the whole packed book.

The balanced and best-STOI books retain **zero coefficients at lags16..31**.
Their changes come from frame fitting. Trimming their books to16 taps gives
identical full PCM, all four counters and stream bytes with the old oracle;
`base16-equality.json` records that proof. They are useful seeds for the
smaller16-tap decoder, rather than evidence that32 taps improve intelligibility.

The spectrum endpoint does use three new coefficients, chosen by the search.
Zeroing only its lags16..31 while keeping every frame/gain/period unchanged
changes STOI0.833251→0.838647 and spectrogram loss0.477674→0.488048.
Thus its extra taps improve this spectrum metric while reducing STOI. Both
measurements use the same byte stream and preserve reference timing.
`tail-ablation.json` contains the paired control. Its spectrum reduction is
only3.07% against the rounded0.492822219 baseline, short of the requested30%.

The raw DC bias remains about+0.077 for all endpoints and raw RMS about0.117–
0.119. Every strict5dB top10-partial audit fails. Spectral and tracking metrics
apply their documented high-pass/global-RMS policy, so they do not establish
that raw DC or level is correct. `report.json` includes both raw-level and
matched-level partial diagnostics, STOI/eSTOI, full spectral errors and counts.
Search-stage `avr_qualified=false` flags refer to that stage only; the later
actual proofs are in each `avr-build.json` and summarized in `summary.json`.
Public firmware is unchanged.

The automatic search used6000 proposals, seed320231, and four pre-existing
initializers. It changed frame coefficients, periods, gains and source row,
plus individual or adjacent32-tap book coefficients. Actual stream budgets
were621 floor and619 nearest. Pareto selection retained both quality ends;
it did not average them into a claimed success. The dedicated pole schema is
explicitly converted to ordinary Q3 when imported and rescored; this input
happened to contain no pole nibbles. Initializer paths/hashes and conversion
counts are retained in `summary.json`. No candidate audio or binaries are
committed.

Reproduce with the repository codec Python dependencies and the same source
reference (retained initializer JSON is semantically identical to the original
build copies):

```powershell
python tools/probe-q3-pulsebook32.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json --model ATtiny13A/Sound/research/q3-rounded-eeprom/qualified/model.json --model ATtiny13A/Sound/research/q3-core-data-cycles/vinni/cycle-01/after/model.json --model ATtiny13A/Sound/research/q3-core-data-cycles/vinni/cycle-02/after/model.json --output build/q3-pulsebook32/vinni/reproduce --proposals 6000 --seed 320231
```

The output contains three endpoints, listening WAVs, exact stream/EEPROM bytes,
the complete PC report and intermediate Pareto models. Recreate a single
retained endpoint without searching by supplying that model with
`--proposals 0`, then run `tools/build-q3-pulsebook32.py` with its generated
`speech.hq`, `eeprom.bin`, `--samples 22272` and the AVR/Node toolchain paths.
The builder independently creates and verifies the complete images.

The fixed tests are `tools/test-q3-pulsebook32.py` (5) and
`tools/test-probe-q3-pulsebook32.py` (4). Source and result commits are separate.
