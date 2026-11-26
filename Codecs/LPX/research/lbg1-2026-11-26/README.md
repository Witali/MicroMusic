# LG1 versus current LPX: complete decoder experiment

Implemented on 2026-11-26 against production revision `24fd9416` in branch
`codex/lpx-bfp-trajectories`. [LG1](../../experimental/LBG1/README.md) stores
actual Q12 LPC anchors with adaptive groups and shared exponents, and supports
true logarithmic excitation-level trajectories. This is a new format.

**Result:** this implementation loses to current LPX in file size and optimized
AVR playback cost. Keeping the same ten-pole filter makes storage changes
separable from the earlier adaptive-order experiment. Fixed-point waveform
identity is verified by the raw-anchor control before introducing quantization.

## Corpus and quality

Four repository source recordings (`chego`, `otvechaesh`, `vinni`, `bread`), each
encoded with current P4 and P6 / calls4, give eight files. The first three
originals are 7.5 kHz and are resampled to 8 kHz with a Kaiser-5 polyphase FIR;
the scalar preparation was byte-checked against SciPy `resample_poly(16,15)`.
Bread is already 8 kHz. Comparisons use complete PCM16 inputs, with no fitted
gain or delay. Existing 44.1 kHz web playback exports are not the references.

| Storage variant | Eight files, bytes | Change versus LPX | Mean PCM STOI | PCM SSE change |
| --- | ---: | ---: | ---: | ---: |
| Current LPX | 8,587 | — | 0.747597 | — |
| LG1 raw anchors, exact control | 23,436 | +172.9% | 0.747597 | 0% |
| LG1 lossless grouped anchors | 19,835 | +131.0% | 0.747597 | 0% |
| LG1 groups + trajectories, fine | 15,589 | +81.5% | 0.747503 | −0.014% |
| LG1 groups + trajectories, compact | 13,712 | +59.7% | 0.747484 | +0.434% |

Fine and compact permit anchor errors of 8 and 32 Q12 integer units, respectively;
interpolation may add one rounding unit. They permit excitation-step deviations
of 0.05 and 0.25 dB. These are diagnostic candidates, not a claim that every
recording sounds equally good. All eight pass the existing output-level and
spectrum guards. STOI, waveform error and full-band spectral/temporal metrics
are retained for every file, including PWM output, in [results.json](results.json).
No blinded listening test was performed.

A same-bit-budget pulse-refit experiment tried 16 additional candidates and
2,159,105 bounded pulse evaluations. None passed the complete admission test
(PCM/PWM SSE, STOI, full-band metrics and output guards together), so their
output files remain identical to the initial fine/compact variants. Proposal
metrics and rejection reasons are retained; these variants do not extend the
frozen AVR matrix.

Grouping helps relative to raw LPC anchors, but storing those anchors costs much
more than current LPX's compact LSF indices. Trajectory coding saves about 410
bytes across the eight quantized files. For these recordings the level encoder
selects constants or literal runs; **no true logarithmic level command wins the
bit-cost/error test**. Pitch uses seven exact linear-lag runs. Thus the speech
results do not measure a quality or size benefit from logarithmic ramps.

A separate encoder-generated rising-level control does select one true-log-Q8
command and one linear-pitch command: 1,440 samples, 86 bytes, maximum excitation
level deviation 0.02344 dB. Its complete AVR playback is checked on both targets
with C and ASM, so the logarithmic path is exercised even though speech does
not select it.

## Complete AVR playback

These are interrupt-active simulations using the production player, FIFO of 32
samples, prefill of 24, gain Q7=128, Timer0 sample scheduling and Timer1 PWM.
Both MCUs run at 16 MHz and output 8 kHz: 2,000 cycles per sample. The ASM ISR
is used on both arithmetic backends. No physical board measurement was made.

The LG adapter snapshots production sources, substitutes the decoder and
disables the old decoder's private ROM shortcuts. Baseline uses the current
optimized player unchanged. This measures the cost of these complete
implementations; it does not isolate a single arithmetic operation.

The table uses compact LG1 and sample-weighted **matched complete files**.
ATtiny88 excludes `vinni-p6` from both CPU averages because its LG1 firmware
does not fit. ATmega328P uses all eight files. CPU share includes foreground
decode/FIFO production plus the measured ISR, excluding idle waits.
Decode/FIFO counters cover every sample call, including coefficient and packet
boundaries. Initial `begin()` and startup outside these existing measured
regions are excluded; complete playback, EOF and output timing are checked
separately. Underrun silence does not receive additional averaging weight.

| MCU / arithmetic | LPX decode cycles/sample | LG1 decode cycles/sample | LPX CPU share | LG1 CPU share | LG1 real-time files |
| --- | ---: | ---: | ---: | ---: | ---: |
| ATtiny88 / ASM | 1,366.6 | 1,549.1 | 71.1% | 81.2% | 7/8; one Flash overflow |
| ATmega328P / ASM | 626.7 | 742.2 | 34.2% | 40.9% | 8/8 |
| ATtiny88 / C | 5,095.6 | 4,951.5 | >256.9% foreground alone | >249.7% foreground alone | 0/8 |
| ATmega328P / C | 1,661.5 | 1,581.0 | 86.9% | 82.6% | 8/8 |

The Tiny C row uses all eight matching files. Its load figures include only
foreground work and exclude ISR cost, giving a lower bound on required CPU.
Values above 100% describe required CPU at the requested sample rate, not
achieved real-time utilization; the
actual complete player inserts silence on underruns. Its valid queued samples
still match the independent reference. C gives a small improvement, while the
current optimized LPX remains faster with ASM: compact LG1 costs +13.4% decoder
CPU on Tiny and +18.4% on Mega. Including FIFO production, increases are +14.4%
and +20.4%. Fine LG1 is slightly slower again.

| Resource, ASM player (compact LG1) | LPX ATtiny88 | LG1 ATtiny88 | LPX ATmega328P | LG1 ATmega328P |
| --- | ---: | ---: | ---: | ---: |
| Program Flash excluding audio | 3,578–3,579 B | 5,025–5,026 B | 3,025–3,026 B | 4,273–4,274 B |
| Static SRAM | 418 B | 420 B | 417 B | 420 B |
| Observed maximum stack | 27 B | 42 B | 24 B | 42 B |
| Remaining physical SRAM | 67 B | 50 B | 1,607 B | 1,586 B |

Flash includes the complete player, not just the decoder object. Audio also
occupies Flash: compact LG1 plus player is 5,958–7,254 B for the seven fitting
Tiny files and 5,206–7,450 B on Mega for all eight. Physical Tiny Flash is 8,192
bytes; a standard bootloader imposes a smaller application limit. Per-file
bootloader fit is recorded separately. Stack headroom is observed for these
workloads, not a universal bound for arbitrary callers or interrupts.

The core matrix contains 32 LPX and 96 LG1 requests (exact/fine/compact × both
MCUs × C/ASM). Nine LG1 Tiny images fail the physical Flash link limit and are
never run as oversized simulated devices. All 87 fitting LG1 firmware images
produce exact valid PWM sequences; 66 meet real-time admission. Current LPX
admits 24/32: all ASM and Mega C, with Tiny C too slow. All fitting ASM LG1
speech playbacks have zero underruns. Every row, failure and timing maximum is
retained in the report.

## Validation and provenance

- Independent native reference versus actual LG decoder for all 64 initial
  streams; exact and lossless-group controls reproduce current LPX PCM exactly.
- Eighteen invalid public encoder models are rejected; unknown case selection
  is rejected before writing files. The synthetic self-test also checks the
  exact control against native LPX.
- ASan/UBSan: 109 constructed valid streams, 136 explicit invalid cases, all
  3,072 log-Q8 values, 64 actual encoded streams, 384 injected reader failures,
  4,608 mutated/random inputs, reset/recovery on the affected decoder instance
  and 980,064 PWM-contract sample checks.
- Twenty-two full-player controls cover partial packets (1/41/321 samples),
  repeated reset playback, explicit generic C override with real AVR memory
  macros, and the actual encoder-generated logarithmic/pitch trajectory file.
  All valid output matches. Tiny C remains too slow on the longer controls.
- The observer extension adds Tiny valid-only output for underrun diagnosis.
  Original and extended observers run the same unchanged Tiny/Mega ELFs with
  identical complete PWM and all 45/48 original timing fields.

Host: GCC 13.3.0, C++11, `-O3 -ffp-contract=off`, portable fixed-point decode.
AVR: GCC 7.3.0, GNU++11, `-Os -flto -mcall-prologues -mrelax`, existing profile
flags and explicit ASM/C selection; simavr 1.6. Vendor device headers and the
production timer/IRQ definitions are reused. Exact representative recipes and
device hashes are retained in [build-provenance.json](../../experimental/LBG1/avr/build-provenance.json). See the
[AVR cookbook entry](../../../../docs/avr-asm-cookbook/lbg1-full-decoder.md) for
the Q4 helper constraint and measured implementation costs.

Raw build receipts, commands, firmware, media and simulator logs stay under
ignored `build/`. The retained JSON includes input/source hashes and compact
complete row results. No imported MIDI, generated audio or firmware is committed.

## Reproduce

Use Linux/WSL with Python 3.10+, G++ and the repository's AVR-GCC / simavr build
dependencies. Run from the repository root. Source preparation is standard
library Python; optional `--scipy` cross-checks the resampler.

```sh
python3 Codecs/LPX/research/lbg1-2026-11-26/prepare_sources.py
python3 Codecs/LPX/research/lbg1-2026-11-26/build_probe.py
python3 Codecs/LPX/research/lbg1-2026-11-26/prepare_baselines.py
python3 Codecs/LPX/experimental/LBG1/compare.py
python3 Codecs/LPX/experimental/LBG1/compare.py --selftest-only
python3 Codecs/LPX/experimental/LBG1/compare.py --variants fine-refit compact-refit --manifest build/lbg1-encoder/refit-manifest.json
python3 Codecs/LPX/research/lbg1-2026-11-26/validate_corpus.py
python3 Codecs/LPX/experimental/LBG1/avr/run_full.py --manifest build/lbg1-common/baselines.json --output build/lbg1-avr/baseline-v1 --jobs 2
python3 Codecs/LPX/experimental/LBG1/tests/check_observer_equivalence.py --run build/lbg1-avr/baseline-v1
python3 Codecs/LPX/experimental/LBG1/avr/run_full.py --manifest build/lbg1-encoder/manifest.json --variants exact fine compact --output build/lbg1-avr/lg-matrix-v2 --jobs 2
python3 Codecs/LPX/experimental/LBG1/tests/make_full_controls.py --output build/lbg1-avr/control-inputs-v2
python3 Codecs/LPX/experimental/LBG1/tests/run_full_controls.py --manifest build/lbg1-avr/control-inputs-v2/manifest.json --output build/lbg1-avr/controls-v2
python3 Codecs/LPX/experimental/LBG1/avr/retain_results.py --baseline build/lbg1-avr/baseline-v1 --experimental build/lbg1-avr/lg-matrix-v2 --controls build/lbg1-avr/controls-v2 --observer-proof build/lbg1-avr/baseline-v1/observer-equivalence/proof.json
python3 Codecs/LPX/research/lbg1-2026-11-26/summarize.py
```

AVR runners require fresh output directories and freeze their bytes, reference
PCM and decoder sources before building. Partial encoder runs use a separate
manifest. Existing verified audio bytes cannot be silently overwritten.
`summarize.py` creates the retained report after the matrix, controls and
observer-equivalence proof exist; paths are explicit at the top of that script.

The mechanism is implemented and reproducible. A useful next experiment would
apply grouping to a compact spectral representation, since direct LPC anchor
storage is the main size penalty measured here.
