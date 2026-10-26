# Relative level policy and quiet LPX speech

The shared host default is **-30 dB relative to the RMS power of the complete
recording**. It is a soft distortion denominator, not a silence gate or a
request to amplify the output. The floor is `max(1, mean(PCM16**2) * 0.001)`;
the one-unit minimum only prevents division by zero at integer precision.
WAV, rate/distortion, joint, global-budget and reference/fast VBR allocation
use the same definition. Segmented WAV conversion retains the whole-recording
reference. The explicit low-rate entry point accepts one segment up to 8 s.

## Cause and correction

The old Russian male example selected 663 zero-width excitation blocks out
of 800. Independent integer-model and native C++ output agreed: the gaps were
already encoded in the stream. Increasing the PWM queue would not repair them.
Absolute level floors, a coarse scalar rate search and joint search starting
only from that damaged winner made low-level speech particularly vulnerable.

The low-rate encoder now retains bounded, diverse oversized seeds for the
joint pitch/sparse search. It also proposes integer-headroom analysis and
restores scale using existing fields. No gain field, decoder operation or MCU
buffer is added. Scaling fixed-point excitation is **not** exact waveform
scaling: rounding, filter state and clipping require actual original-level
native decoding and comparison with the independent model.

At the original level, balanced and recording-weighted searches are evaluated
through the full decoder. An unvalidated scale proposal must not establish an
STOI acceptance floor: a large level/DC error can coexist with a good STOI.
Validated baseline protection remains the default in the general budget tool.

The final joint/perceptual path rejects three consecutive muted 10 ms windows.
Input windows are active above the same recording-relative floor; output
power below 0.001 times that input window is considered muted. Candidates must
also have squared PCM error no greater than a silent reconstruction. These
checks evaluate samples and never modify them. A finite search can return
`no_fit`; this is not a lower bound of the format. The byte cap is never raised
automatically. `target` remains an explicit preliminary scalar stage.

## Same-budget Russian regression

Both streams use the exact same 64,000 PCM16 samples at 8 kHz, with a complete
file cap of 8,020 bytes (maximum 8 kbit/s payload). Baseline revision:
`5427bea20c8e110208b4802c8b2588fd1f30d764`.

| Measure | Before | Corrected |
|---|---:|---:|
| File bytes | 4,583 | 8,001 |
| Actual payload kbit/s | 4.563 | 7.981 |
| PCM16 SER, dB | 0.6464 | 11.9133 |
| STOI | 0.12884 | 0.73825 |

The improvement uses more of the already allowed budget. It is not an
equal-achieved-bitrate comparison. SER uses original PCM, without gain fitting
or alignment. STOI estimates intelligibility; it is not a listening score.

The full level matrix, hashes, acceptance results and AVR observations are in
[`results.json`](results.json). Three public-source voices are tested at
0, -12 and -24 dB input gain, preserving that actual output level. Quality is
not uniformly better at a fixed small cap: preserving quiet details can spend
bits otherwise assigned to stronger speech. Rejected level-error experiments
are not admitted merely because they avoid zero-output runs.

## Measured level matrix

All accepted streams below pass the activity and original-level waveform checks,
native/model equality and complete active-IRQ ASM PWM equality with zero underruns.
Each input contains 64,000 samples at 8 kHz. Caps are payload budgets; rates are
actual payload rates. Very quiet English uses an explicitly larger budget.

| Voice | Input gain, dB | Cap / actual kbit/s | SER, dB | STOI | Output RMS change, dB |
|---|---:|---:|---:|---:|---:|
| RU male | 0 | 9.8 / 9.640 | 13.69 | 0.774 | -0.18 |
| RU male | -12 | 9.8 / 9.782 | 14.77 | 0.767 | -0.10 |
| RU male | -24 | 9.8 / 9.729 | 11.67 | 0.747 | -0.21 |
| RU female | 0 | 9.8 / 8.842 | 7.01 | 0.878 | -1.23 |
| RU female | -12 | 9.8 / 8.860 | 6.99 | 0.878 | -1.48 |
| RU female | -24 | 9.8 / 8.865 | 5.52 | 0.879 | -0.73 |
| EN male | 0 | 9.8 / 9.552 | 6.32 | 0.860 | -1.26 |
| EN male | -12 | 9.8 / 9.470 | 10.78 | 0.880 | -0.36 |
| EN male | -24 | 16.0 / 15.950 | 15.16 | 0.915 | -0.06 |

At the 9.8 kbit/s cap, the -24 dB English search has no observed candidate
passing both guards. A previously scaled proposal had SER -8.80 dB and RMS
gain +9.06 dB and is rejected. The 16 kbit/s-cap result is not evidence that
9.8 kbit/s is impossible in the format or with a better search.

136 host tests pass in 80.453 s, including independent arithmetic/format checks,
byte-cap constraints, sparse/partial-tail gain proposals and rejection of a
large level error even without a mute. Source hashes are captured per run.
Unchanged earlier streams retain full-run evidence, with the final selection
policy replayed against archived candidates and actual PCM rechecked; the two
corrected -24 dB cases have fresh full encodings. Per-case source hashes and
validation scope remain explicit in the JSON. No rejected experiment is
packaged as an accepted listening sample.

## AVR timing scope

For the corrected male 8 kbit/s-cap stream, simavr 1.6 executes the full
ATmega328P 16 MHz / 8 kHz PWM player with active timer interrupts: 64,000 useful
PWM samples equal the native reference, **zero underruns**. Queue = 512 bytes,
prefill = 384, AVR-GCC 7.3.0 `-Os`, dot unroll = 9, v3 features = 24.
Total Flash including the stream = 15,526 bytes, static SRAM = 1,102 bytes;
observed stack margin = 823 bytes. Mean instrumented decode wall interval =
847.31 cycles/sample; it includes IRQ and profiling stores and is not a pure
decoder CPU percentage. No physical board or analog audio measurement is made.

Listening WAVs retain signed PCM16. The PWM admission compares the expected
8-bit sequence; that timing/correctness check does not establish the audible
resolution of very quiet details at a physical 8-bit PWM output.

The explicitly selected C backend produces the same useful PWM sequence but
has 20,632 underruns on this workload (mean wall interval 2,561.08 cycles).
It remains a portable correctness fallback, not an admitted real-time AVR
profile. MCU arithmetic, architecture/backend selection and source are
unchanged by this encoder work. Timing is measured per generated stream;
do not infer universal admission from compressed bitrate alone.

## Reproduction

From `Codecs/LPX/01_ACTIVE_Q0_CODEC`, with the existing requirements installed:

```sh
python tools/encode_lowrate.py input8k.wav output --audio-kbps 8 --level-floor-db -30
python tools/encode_lowrate.py quiet8k.wav quiet-output --audio-kbps 16 --level-floor-db -30
python -m unittest discover -s tests -p 'test_*.py' -q
python tools/profile_avr.py output/audio.l4hy avr-output --avr-bin /path/to/avr/bin --sim-runner /path/to/sim_profile --wsl Ubuntu --enable-asm --queue 512 --prefill 384 --dot-unroll 9 --v3-features 24
```

`--no-gain-search` explicitly disables the headroom proposal. Existing
`LPX4_ENABLE_ASM=1` selects ASM only on a supported architecture; omitting it
retains C. Host sound/stream files and large temporary logs stay outside Git.
The retained JSON contains technical measurements and hashes only.

## Source credits

Each source supplies the same first eight seconds of the previously retained
excerpt, resampled once to mono PCM16/8 kHz. Quiet variants apply exactly
-12/-24 dB before rounding to PCM16. There is no output normalization or
denoising. Audio derivatives retain their applicable source attribution/license.

- Russian male, speaker Шантопик: [Л. Пушкину](https://commons.wikimedia.org/wiki/File:Ru-%D0%9B_%D0%9F%D1%83%D1%88%D0%BA%D0%B8%D0%BD%D1%83.ogg), source offset 2 s, CC BY-SA 4.0.
- Russian female, speaker Elena Krizhanovsky: [Вера Слуцкая](https://commons.wikimedia.org/wiki/File:Ru-Slutskaya_Vera.ogg), offset 20 s, recording public domain; article text attribution as specified on that source page.
- English male, speaker Persent101: [The letter A](https://commons.wikimedia.org/wiki/File:En-A-article.ogg), offset 15 s, CC BY-SA 3.0.
