# Adaptive excitation storage and half-sample pitch

The new full Vinni firmware improves the previous seven-form reference while
using **four excitation forms and half-sample pitch in ten frames**. It occupies
**1022 Flash + 64 EEPROM bytes**, including decoder, full speech, stop marker and
alignment. Reference JS, optimized WASM and unoptimized WASM reproduce every
integer sample. This is research-branch firmware; hardware has not been tested.

## Results on the unchanged original

The complete canonical original is
[`vinni.wav`](../../../../web-player/audio/originals/vinni.wav): 22,272 samples at
7500 Hz, SHA-256 `749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
No samples, non-speech effects or time intervals are removed. The existing STOI,
eSTOI, HP70/global-RMS spectral and ten-component tracking policies are unchanged.
No audio normalization, pitch alignment or block splicing is added to playback.

| Model | Flash | Core | STOI ↑ | eSTOI ↑ | Spectral loss ↓ | Frequency error, cents ↓ | Level error, dB ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Previous seven-form reference, compact storage | 1010 | 422 | 0.852952 | 0.664348 | 0.490770 | 57.074 | 7.543 |
| Four-form ablation control | 984 | 398 | 0.850864 | 0.660479 | 0.490296 | 56.225 | 7.738 |
| New half-pitch fit | **1022** | **422** | **0.853087** | **0.669892** | **0.484848** | **51.421** | **6.838** |

Against the previous best reference, the full spectral loss falls **1.21%**,
weighted strong-component frequency error **9.90%**, level error **9.34%**, and
combined harmonic-track loss **10.09%** (1.000796 → 0.899778). STOI rises only
0.000135; eSTOI rises 0.005544. These are measured engineering improvements,
not a claim that listening quality improved by those percentages.

The selected model and an independent rescore of actual AVR output are retained
as [`model.json`](half-pitch/model.json) and [`quality.json`](half-pitch/quality.json).
The rescore exactly reproduces the stored STOI/eSTOI, spectral loss, raw mean and
all harmonic metrics from the fitter. The phrase PCM SHA-256 is
`6e7460448faded3cb63371b9c4729b4c81ad69c6560eef40cef7973179efa836`.

## How the decoder changed

An integer pitch P can now select alternating **P+1 and P sample periods**, with
the toggle reset at each frame. The excitation lag accounts for the extra
sample, so the first waveform tap is not accidentally duplicated. The high bit
of the extended pitch byte stores the fraction flag. Fractional frames force an
extended pitch header when necessary, and the packer counts those bytes.
Noise frames must have the flag cleared. Ordinary integer frames retain their
original pulse timing and bytes. The separate research schema is
`q3-half-pitch-probe-v1`; ordinary encoders do not silently load it.

The half-pitch extension adds **24 code bytes** to the selected 398-byte
four-form core. Two registers bits hold the fraction and current extra sample;
no additional SRAM is allocated. Four short byte-encoded forms occupy 16 EEPROM
bytes, and the first 48 speech bytes occupy the remainder. The logical stream
has 647 bytes: **422 code + 599 Flash speech + 1 EOF = 1022 Flash**. The builder
independently checks this prediction, linker limit and actual binary length.

The first qualified version used 26 extra code bytes and occupied 1024 Flash.
Extracting the pitch high bit through carry reduced the parser by one word,
retaining the exact PCM. This optimization and its IRQ/flag requirements are
saved in the [AVR cookbook](../../codec/AVR_ASSEMBLY_RECIPES.md).

## Why fewer forms can help

The packer collects only forms actually used by voiced, nonzero-gain frames.
Duplicates are recoded exactly. It puts the most expensive selectors into the
four positions that avoid forced headers, and selects byte/nibble storage,
physical width and four/eight-form ASM by complete image size. A simple sound
may store just one waveform. One zero row remains when there are no voiced forms.
The logical eight-slot model remains available on the PC.

For the previous seven-form reference this saves **1012 → 1010 Flash bytes**
without changing PCM: 14 EEPROM bytes for forms and 50 for speech. A one-form
four-tap profile can hold a 685-byte stream; seven forms hold 651. Both maximum
images execute at exactly 1024 Flash bytes and reject oversized inputs.
After the half-pitch fit, four forms suffice. More available slots do not force
the encoder to fill them.

## Automatic fitting and rejected alternatives

All changes to pitches, gains, waveform taps, coefficient reuse runs, individual
coefficients and frame boundaries are selected by scripts through the full
integer decoder. Source/manifest links preserve the development order:

1. Five thousand guarded single-coordinate evaluations found no improving
   endpoint. Three 5000-proposal joint searches, including wider forms and the
   four-form control, also retained their original guarded endpoint. Their
   exploratory results trade off intelligibility or spectrum and are not
   replacements. Reports and unique model endpoints remain in this directory.
2. The half-pitch seed fits neighbouring integer/half-integer choices over two passes. It
   changes twelve coordinates and enables ten fractional frames. Its first
   spectrum/level improvement still leaves STOI below the seven-form reference.
3. A further **4500 whole-clip coordinate evaluations** accept thirty changes
   and recover both STOI and eSTOI while further reducing spectral error. The
   finalizer limits DC, strong-component frequency/level/loss, missing energy
   and strict 5 dB violation power. It does not concatenate independent blocks.
4. The actual assembled 1024-byte image is qualified, then the same sound is
   reduced to 1022 bytes by the carry extraction optimization.

[`manifest.json`](manifest.json) identifies exact source revisions. The retained
half-pitch refinement report predates the final two-byte code optimization, so
its image prediction is 1024; the final [`build.json`](half-pitch/build.json)
is authoritative for the smaller image. The current optimizer can use those
two recovered bytes on a future pass. The first fitter's 24-byte code estimate
is not itself assembly evidence.

An additional DC-centering probe subtracts 8–12 DAC counts from the decoded
signal. It reduces raw waveform MSE but slightly worsens STOI/eSTOI and spectrum.
It was rejected; playback has no such postprocessing. The selected raw mean
only changes **+0.078330 → +0.077640**, so DC removal remains unfinished.

## Qualification and remaining limits

The complete suite passes **381 tests**. After the final two-byte optimization,
the four phase-specific tests are rerun with both decoder variants: rapid P=1
alternation beyond 128 toggles, eight forms with mixed integer/fractional/noise
frames, full Vinni, and the same full model with flags cleared. Zero flags must
match the frozen integer oracle exactly. Qualification records the full-suite
revision and the later targeted rerun separately.

The selected binary has **202 cycles** minimum preparation slack, **28 bytes**
maximum SRAM span including stack, no missed samples/lost overflows/wraps, and
66,816 exact samples: the phrase followed by two phrase lengths of silence.
See [`qualification.json`](qualification.json) and the selected build report.

The absolute goals **STOI ≥0.90** and **spectral loss ≤0.3449755536** remain unmet.
Strict per-component 5 dB bounds still fail: matched-level violation power is
0.70314 versus 0.71910 before. The frequency-error 95th percentile improves
150.56 → 141.85 cents and level percentile 17.50 → 16.76 dB, still far from tight
bounds. Extra candidate peak energy slightly worsens (0.23060 → 0.23511), despite
the lower whole-spectrum loss. Only Vinni has been fitted in the new format;
general RU/EN gains and physical PWM sound remain to be tested.

## Reproduction

Use the pinned revisions in the manifest to replay the exact historical fits.
Set `AVR_BIN` and `NODE` to the AVR toolchain and Node executable. Python needs
the project's existing NumPy/SciPy/Numba/SoundFile/speech-metric dependencies.
From this worktree root:

```powershell
python tools/probe-q3-half-pitch-fit.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-pulsebook8/ablation/model.json --output build/q3-adaptive/half-seed
python tools/refine-q3-half-pitch.py --reference web-player/audio/originals/vinni.wav --model build/q3-adaptive/half-seed/model.json --limits-report ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/report.json --output build/q3-adaptive/half-refit --evaluations 4500
python tools/build-q3-half-pitch-probe.py --model ATtiny13A/Sound/research/q3-adaptive/half-pitch/model.json --output build/q3-adaptive/half-final-avr --avr-bin $env:AVR_BIN --node $env:NODE
python tools/build-q3-pulsebook8.py --model ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/guarded/model.json --output build/q3-adaptive/control/avr --adaptive --avr-bin $env:AVR_BIN --node $env:NODE
node tools/render-q3-pulsebook8-comparison.mjs --before build/q3-adaptive/control/avr --after build/q3-adaptive/half-final-avr --before-name before-seven-forms --after-name after-half-pitch-four-forms --output build/q3-adaptive/listening
python tools/test-speech-quality.py
```

[`listening.json`](listening.json) records actual-image audio hashes. Original,
before, after and concatenated before/pause/after WAV files remain under ignored
`build/q3-adaptive/listening/`. Both firmware clips use the same unmodified site
WASM renderer, default catalog gain and 9 kHz output filter. Commit only model
sources, scripts and measured reports; HEX/ELF/WAV intermediates are reproducible.
