# Spectrogram-guided complete period/noise teacher

The latest T1 firmware was still heard as squeaky and unlike the recording.
This experiment checks a more flexible PC synthesis reference before trying
to reduce it to the unchanged tiny integer decoder. It does not replace any
public firmware. Objective improvements are not a listening-quality verdict.

All parameters are fitted automatically to the complete selected reference.
No phoneme, time interval, speaker frequency or formant is hand selected.
The teacher retains 16 learned period waves, continuous phase and three learned
noise colors. The analysis comparison applies the same 70 Hz highpass and
one global RMS match to both signals. Time and frequency are never warped.

## Same-length comparison

| Speech | Previous T1 STOI | Teacher STOI | T1 spectrogram loss | Teacher spectrogram loss | Teacher native data |
| --- | ---: | ---: | ---: | ---: | ---: |
| Public Vinni, 22272 samples | 0.845 | 0.856712 | 0.565548 | 0.423555 | 1241 bytes |
| Final phrase voice, 12800 samples | 0.825 | 0.830612 | 0.617131 | 0.541237 | 834 bytes |

The spectrogram objective measures fine spectral ridges, 32 overlapping mel
envelopes, unsupported output energy and missing reference energy at two
window sizes. Its complete definition is in
[`spectrogram_objective.py`](../../codec/spectrogram_objective.py).
The teacher reduces this error by about 25% and 12%, respectively. Vinni
eSTOI is 0.696783 and legacy multiresolution log spectral error is 0.538675;
the final voice values are 0.525779 and 0.772156.

The shared-scale spectrograms show substantially clearer moving harmonic
ridges in Vinni around the middle-frequency voiced passages. The teacher is
still imperfect: it misses some envelopes and produces excessive diffuse
noise. The final voice has mean spectral flatness 0.352 versus 0.172 in its
original. Flatness is an engineering diagnostic, not a naturalness score.
The teacher's remaining problems must not be presented as a solved codec.

The reported teacher byte counts contain **data only**. They exclude executable
decoder code, constants and runtime memory. Vinni already exceeds 1024 bytes
before adding any decoder. The 834-byte final voice leaves only 190 bytes for
an executable and is not implemented by the tiny core. No teacher firmware
was assembled or hardware tested.

## Automatic projection into the existing tiny core

The projection uses the teacher's co-trained pitch trajectory and waveform
book as initialization. It trains four- and eight-wave integer dictionaries,
chooses the best complete decoded audio, then applies 1000 exact integer
search proposals with white residuals. It does not assume the PC teacher's
scores survive quantization or reducing the noise model.

| Speech | Projected STOI | Log spectral error | Measured code | Flash data | Code + data | EEPROM used |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vinni | 0.691076 | 0.945592 | 720 | 577 | 1297 | 64 |
| Final voice | 0.721825 | 0.901187 | 714 | 383 | 1097 | 64 |

Both projections lose quality and exceed Flash. They are rejected. Size comes
from the actual one-shot assembler object's `wave_data` symbol plus the exact
packed data, rather than estimating executable size from payload alone. They
were not linked as accepted firmware or verified in three AVR engines.
Separate `tiny-projection-size.json` reports record this measurement; the
training report itself explicitly excludes decoder bytes.

## Inputs and reproducibility

Vinni uses the complete canonical mono 7500 Hz reference, WAV SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
The starting teacher is the retained `period-balanced/vinni/model.json`.

The final voice is exactly the selected final excerpt after its first 6528
samples; it is 12800 samples at 7500 Hz, WAV SHA-256
`e725be54dc17ba77051002b20c3dd825560e2554f49e70c20628c89fecea0c0c`.
Its starting teacher is the retained
`new-speech-naturalness/final-voice/colored-model.json`. This study excludes
the bell; it makes no claim about a bell-plus-voice executable fit.

For each clip, first run `tools/probe-spectral-period-teacher.py` with the
corresponding reference, starting model, previous T1 decoded WAV, `--proposals
2000 --weight 2 --seed 23170`. This uses the legacy objective. Its output is
retained as `legacy-stage-model.json`. Then use that model with `--proposals
1000 --objective spectrogram --weight 2 --seed 23170`. The final `model.json`
and `quality.json` are retained here. Each stage preserves its initial STOI
floor; the latter stage uses the new time/frequency objective.

`tools/project-period-teacher-tiny.py --proposals 1000` uses the legacy-stage
teacher, the original reference and seed 23171. `initialize_model` and the
unchanged exact tiny decoder supply all integer arithmetic. Independent
packing/unpacking is checked against decoded PCM for both the teacher and
the integer projection. The entire experiment uses 8000 search proposals:
3000 per complete teacher and 1000 per integer projection.

Generated audio and plots remain in ignored
`build/new-speech/spectral-teacher/`. Each `*-detail/comparison.wav` is
original, previous T1, complete PC teacher, with identical level processing
and 0.3-second gaps. `tools/render-spectral-teacher.py` produces the three-row
spectrogram with a common dB scale. Original WAV/MP3 files and generated
firmware or audio binaries are not retained in this research directory.
