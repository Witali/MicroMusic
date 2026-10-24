# Vinni: bounded soft-LPC2 suggestions within 1 KB Flash and 64 B EEPROM

This experiment returns to the hard device budget. It uses the exact current
`web-player/audio/originals/vinni.wav` (SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`),
22272 samples at 7500 Hz, with no input normalization, DC removal, crop,
resampling or time compression. The incumbent is the explicitly identified
public Q3/T1 model, not the weaker generic Tiny initializer.

The LPC2 encoder supplies offline suggestions. Its own 537-byte parameter file
is analysis scaffolding and is not stored in the Q3 firmware. The output format
and original floor-Q3 arithmetic are unchanged. The separate EEPROM-prefix
reader stores the first 64 speech-stream bytes in EEPROM, leaving more Flash
space for spectral updates. See
[Q3_SOFT_LPC2_PRIOR.md](../../codec/Q3_SOFT_LPC2_PRIOR.md) for the source/API and
the exact command.

## Whole transfer was rejected

The reproducible [48-control screen](vinni/seed-screen.json) retains the earlier
602-byte cap: four reflection blends, four pitch/voicing policies and three
gain scales. Twenty-four candidates pass physical/byte checks. Only the exact
incumbent passes all quality guards; no transferred control improves it.

For example, a .25 reflection blend with old pitch/unity gain occupies 600
stream bytes but lowers STOI from .83840 to .78784. Merely reducing incumbent
gain to .75 gives a lower aggregate difference score while lowering STOI to
.80930 and worsening the four spectral components. Both are rejected. LPC2
F0/voicing is therefore not treated as an oracle or a mandatory voice mask.

## Soft local search

The single configuration uses 2000 proposals, seed 23261 and a 639-byte total
stream cap. Half use the existing proposal function. Half suggest one-step
reflection/F0/calibrated-gain moves or a separately identified voicing change.
Original PCM remains the target. Working states may cross inferior regions;
only elites meeting every frozen incumbent guard can be exported.

The selected result is a **small numerical improvement**. It does not establish
an audible improvement in naturalness, nor show that LPC2 guidance outperforms
the existing proposer: no matched-budget proposer ablation was run. Proposal
kinds and accepted-elite history are retained in [quality.json](vinni/quality.json).

| Measurement | Public Q3/T1 incumbent | Selected candidate |
| --- | ---: | ---: |
| STOI | .83839644 | .83863685 |
| eSTOI | .64461051 | .64513135 |
| Fine spectral error | .48844392 | .48825920 |
| Envelope error | .60081406 | .60025314 |
| Unsupported energy | .20068080 | .20038142 |
| Missing energy | .20033717 | .19928015 |
| Spectrogram loss | .50435714 | .50394870 |
| Harmonic-track loss | .92763589 | .90292872 |
| Target-power-weighted matched frequency error, cents | 48.64127 | 46.14021 |
| Matched level error, dB | 7.38236 | 7.30550 |
| Matched frequency error p95, cents | 111.27548 | 112.97165 |
| Matched level error p95, dB | 17.59277 | 17.59799 |
| Target-power-weighted match rate | .82717587 | .83063415 |
| Continuity-break rate | .35305606 | .30625360 |
| Stream bytes, before storage split | 602 | 629 |

The strict all-selected-partials 5 dB target is still unmet. The matched mean
alone remains above 5 dB, and missing partials remain present. Neither a better
weighted loss nor higher coverage is described as satisfying that stricter
bound. No Chego/Otvechaesh model is replaced by this isolated Vinni experiment;
no corpus or speaker-generalization claim follows from it.

The two p95 errors rise slightly even while means and the frozen combined
track loss improve. Those individual quantiles are diagnostics rather than
frozen export guards. Raw-level inspection also matters: the incumbent already
has positive DC (mean .07399531 versus original -.00005890), and the candidate
slightly increases it to .07423173. Output RMS changes from .11090972 to
.11111602 versus original .12985254; both peaks are .6484375. The objectives'
highpass/global level matching does not repair that raw signal. This experiment
does not fix the existing DC bias and does not justify automatic public
replacement. Raw statistics and their exact input hashes are retained in the
[signal audit](vinni/signal-audit.json). Raw MSE also rises slightly from
.03043188 to .03048701 (raw SNR -2.56428 to -2.57214 dB). Strict 5 dB audits
fail for both incumbent/candidate, with and without global RMS matching.

## Actual storage and verification

The incumbent's qualified Flash-only image is 1024 bytes: 420 code, 602 speech,
one EOF and one linker-padding byte, with no EEPROM data. The candidate uses
the independently qualified 448-byte floor-Q3 EEPROM reader, 629 total speech
bytes and one EOF. The stream is split into 64 EEPROM bytes and 565 Flash
bytes. Actual assembly and three-engine verification are retained in
[build.json](vinni/build.json); the Flash image is 1014 bytes and EEPROM use is
64 bytes. These counts include decoder, all speech data, EOF and linker
padding. Hardware testing and human-listening verification are still false.

The original compiler launch failed under the restricted Windows launcher;
the final build runs with the working authorized toolchain. The same fixed-seed
configuration was replayed after CLI-only persistence/console fixes, and its
selected model, stream and integer PCM were checked against the first result.
This replay is reproducibility verification, not another parameter sweep.

Eight focused tests cover full-polynomial step-down, changed frame-boundary
mapping, bounded and sharing-preserving moves, pitch/voicing separation,
EEPROM-sized streams, 48-control serialization, nonfinite/guard fallback and
completed-run summary handling. All passed. Current normalized-LF source
fingerprints, original/model/stream/PCM hashes and the exact build measurements
are retained with the result.

Ignored generated outputs are under `build/hq4-q3-lpc2-prior/vinni/`:
`decoded.wav` is raw integer-decoder output; `comparison.wav` presents original,
incumbent and candidate with explicitly labeled common highpass/global RMS
matching/shared peak scaling. `avr/firmware.hex` and `avr/eeprom.hex` belong to
the same build and must be used together. Audio, generated binaries and HEX
files are not committed; only reports and the selected source model are kept.
