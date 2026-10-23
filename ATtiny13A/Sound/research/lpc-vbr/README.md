# LPV1 bounded rate/distortion experiment

Nine adaptive encodes: original Vinni (22272 samples), the complete bell-plus-
voice tail phrase (19328 samples), and the frozen English en_sense_a center
excerpt (15360 samples). All are unchanged mono7500Hz references. Each reuses
the exact LPC2 base from the fixed-control experiment, with20ms frames,
32ms analysis and pre=.85. No input gain/DC/crop changes were made.

| Case | Block target dB | Complete bytes | Raw SNR dB | STOI | eSTOI | Failed blocks |
|---|---:|---:|---:|---:|---:|---:|
| Vinni | 20 | 10615 | 23.79 | .98303 | .96020 | 1/297 |
| Vinni | 24 | 12462 | 26.75 | .98904 | .97413 | 2/297 |
| Vinni | 28 | 14459 | 31.35 | .99486 | .98767 | 3/297 |
| Full tail | 20 | 9796 | 23.09 | .97489 | .93422 | 1/258 |
| Full tail | 24 | 12115 | 27.32 | .98912 | .96758 | 2/258 |
| Full tail | 28 | 13568 | 31.88 | .99573 | .98620 | 4/258 |
| English | 20 | 5143 | 23.57 | .87869 | .78826 | 0/205 |
| English | 24 | 6257 | 26.75 | .91204 | .85990 | 1/205 |
| English | 28 | 7345 | 29.55 | .96529 | .93729 | 11/205 |

The default floor is -60dB relative to global RMS. A strict requested target is
not met by every block; the finite scale grid and carried-state tails sometimes
need a lowest-error fallback. Failures and their actual MSE/threshold are
explicit in each `*-decisions.json`. These are not all-block quality guarantees.
All nine results have zero internal emphasized-state guard events, no output
limiter or normalization, exact full duration and exact parameter-only decode.

## Comparisons with fixed precision

Vinni fixed6 occupies17562B, rawSNR30.89dB, STOI.99512, eSTOI.99186.
LPV1 target28 occupies14459B, 17.7% less, and improves rawSNR to31.35dB.
STOI falls slightly to.99486; eSTOI falls to.98767 and spectrogram loss worsens
from.01438 to.01789. This is a size/quality tradeoff, not an exact replacement
for the fixed6-bit sound. Lossless entropy wrapping of fixed6 is a separate
experiment and is not represented by the14459B figure.

Full tail fixed6 occupies15215B, SNR28.40dB, STOI.98617, eSTOI.97305.
LPV1 target28 occupies13568B, 10.8% less, with SNR31.88dB, STOI.99573,
eSTOI.98620 and spectrogram loss.01673 versus.02000. This is a promising measured
candidate, requiring listening; its four failed local targets remain disclosed.

English demonstrates the limitation of a raw waveform MSE objective. Fixed4
occupies8128B, SNR20.04dB, STOI.97693 and eSTOI.95889. LPV1 target28 is7345B
with much better rawSNR29.55dB and spectrogram loss.01979 versus.04127, but
STOI/eSTOI fall to.96529/.93729. Different feedback/noise shaping can improve
waveform error while degrading intelligibility. Do not choose the format on
SNR alone or call this a universal speech-quality improvement. Fixed6 remains
another high-intelligibility control: English STOI.99321, eSTOI.98404.

The initial implementation using the old pre-emphasis-domain target was
replaced before freezing by full causal output-domain feedback on every sample.
The same three cases/three targets were rerun; only the final source and
results are retained. No broad parameter search or AVR port was attempted.

## Artifacts

`<case>/report.json` contains metrics for all five fixed controls and three
LPV1 profiles, source/base/reference hashes and complete container byte counts.
`<case>/base.lp2`, the three `.lpv1` containers and block decisions are retained
as reproducible parameters. Audio and native coefficient caches remain in
ignored `build/lpc-vbr/<case>/`; filenames in the report refer to that original
build directory. Fixed controls and WAVs can be regenerated with the generic
probe; their report entries do not imply that audio is committed here.

Format/API/reproduction details: `../../codec/LPC_VBR.md`.
This is a PC experiment. No decoder Flash, SRAM, cycles, AVR verification or
hardware behavior is claimed by these complete data-container sizes.
