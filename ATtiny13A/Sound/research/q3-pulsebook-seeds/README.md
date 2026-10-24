# Vinni pulsebook initialization: bounded negative results

The requested target is STOI >= .90 and at least a 30% reduction from the
latest rounded spectrogram loss .492822219, hence loss <= .344975554. Both
conditions must hold together within the complete 1024-byte Flash/64-byte
EEPROM device budget. These seed screens did **not** reach the target and
do not replace any published model.

All measurements use complete current `web-player/audio/originals/vinni.wav`,
SHA-256 `749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`,
22272 samples at 7500 Hz. Input level, DC and timing are unchanged. The score
is the existing 70 Hz highpass/global-RMS spectrogram objective, with raw output
mean/RMS reported separately. No waveform alignment is applied for comparison.

## Methods and timing

The isolated helper proposes four signed 16-sample pulse templates plus normal
Q3 frames. The 64 templates fit EEPROM; no original waveform, spectrum, phase
trace or floating point parameters are needed at decode. Details and commands
are in [Q3_PULSEBOOK_SEEDS.md](../../codec/Q3_PULSEBOOK_SEEDS.md).

The inverse screen compares the verified float inverse lattice and an exact
modular integer inverse for floor/nearest products. Template/gain/mode fitting
uses actual fixed-lag windows: first voiced sample lag1, lag0 at period-1,
first frame change at duration0-1, final sample N-1 back at frame0/lag1. No
closure peak is moved and no period is stretched to 16 samples. Five focused
tests now cover these boundaries, excitation recovery, independent parameter
decoding and phase-insensitive reconstruction.

Four packet prototypes initialize bounded discrete least squares. Optional
nearby/autocorrelation pitch candidates preserve the incumbent voicing mask.
Actual stream size limits pitch changes. The screen tests both exact-zero-sum
and unrestricted tables. It evaluates 64 cold fits with four gain scales,
then 48 small legacy/learned preservation blends with incumbent selectors and
gains retained. There is no annealing.

The optional follow-up evaluates exactly 24 minimum-phase seeds. It clusters
four normalized residual log-magnitude spectra, projects their real cepstra
to a causal 16-tap response, then tests zero-sum variants, source-cluster or
incumbent selectors and three legacy blends. Clustering uses all log-magnitude
bins; the short cepstral projection smooths only the reconstructed response.
No original phase or shifted target is used.

## Controls and results

The floor incumbent's 602-byte stream already fits the pulsebook profile cap
of 615. The rounded 637-byte stream needs explicit coefficient-half reuse to
611 bytes under its 613-byte cap. That storage tradeoff is measured separately
in [controls.json](controls.json), avoiding attribution of all degradation to
the table learner.

| Candidate/control | STOI | Spectrogram loss |
| --- | ---: | ---: |
| Floor legacy, 602 B | .838396 | .504357 |
| Rounded legacy after rate fit, 611 B | .827666 | .494527 |
| Best inverse/preservation STOI | .818304 | .518314 |
| Inverse/preservation minimum spectral loss | .802208 | .495149 |
| Best minimum-phase STOI | .808431 | .502793 |
| Minimum-phase minimum spectral loss | .774087 | .490554 |
| Required target | >= .900000 | <= .344976 |

Of the inverse/preservation 112 candidates, 94 pass the exact size, wrap,
peak and step checks. Of the minimum-phase 24 candidates, 23 pass them.
None passes the joint quality target. Cold inverse fits alone top out at
STOI .560145; small preservation blends avoid that large collapse but still
lose to the controls. The minimum-phase spectral endpoint makes a small
spectral gain at a substantial intelligibility cost and is rejected.

These results show that residual MSE and phase-insensitive envelope fitting
are insufficient initializers here. They do not establish a lower bound for
all possible pulsebooks, formats, coefficient fits or larger-core decoders.
In particular, a correct inverse does not make four fixed short templates an
exact reconstruction of its sample-dependent excitation. The required output
targets, rather than residual fitting error, remain the acceptance criterion.

## Retained and generated evidence

[report.json](report.json) retains every inverse/preservation score and
physical rejection, all 16 fitting configurations, coefficient-sharing edits,
source hashes and ranked seed IDs. Only five representative source models and
their measurements are retained, rather than every intermediate model.
The [minimum-phase report](../q3-pulsebook-minphase/report.json) retains all 24
scores with a few representative models, including its spectral endpoint.

The measured inverse source is commit `98fe474`; the minimum-phase extension
is `869b202`. Each report records its actual normalized-LF source fingerprints.
The extension adds a separate method and does not change the earlier inverse
implementation. These are numerical seed qualifications, **not assembled AVR
image claims**. No candidate was sent to hardware or promoted. The separately
measured 408/410-byte pulsebook core sizes supplied the 615/613-byte data caps;
an eventual selected firmware still needs its own actual full-image build and
three-engine check.

Ignored generated models, packed streams, EEPROM bytes and WAVs remain under
`build/q3-pulsebook-seeds/inverse/` and `build/q3-pulsebook-seeds/minphase/`.
No audio, firmware binaries or original source recording is committed.
