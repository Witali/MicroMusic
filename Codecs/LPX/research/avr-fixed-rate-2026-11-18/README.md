# One compile-time LPX rate

Base: `66e3d93499b6df060f8a5c7cdcb133d682dc3106`, preserved and pushed as
`codex/lpx-auto-sample-rate`. The AVR player now compiles for exactly one
nominal frequency. `sample_rate=8000` / CLI `--sample-rate 8000` is the default;
12000 and 16000 are explicit choices. The builder passes
`-DLPX4_SAMPLE_RATE=<rate>` consistently to every translation unit and the
portable C comparison. A file or dialogue segment must declare that rate.
Other recording parameters remain in LPX; no audio bytes or format change.

The standalone library defaults to 8000 on AVR and 0 on hosts. Zero lets
the PC reference read all three v9 rates, including its independent floating
synthesis. The firmware player requires a concrete rate. Both arithmetic
backends remain explicitly selectable and use the same rate checks.

## Measured complete-player checks

AVR-GCC 7.3.0, GNU AVR ABI, simavr 1.6, project Tiny88 peripheral model,
16 MHz, FIFO32/prefill24, opt-in ASM arithmetic and reserved-register ISR.
These are simulator measurements, not physical-board measurements.

`measurements.json` retains 22 cases × three separately compiled frequencies
× two chips, matched with the historical automatic-player receipt. All
132 input/output hashes, underrun counts, foreground mean/peak CPU work,
static RAM and peak stack equal their predecessor. IRQ cost is equal or
lower; shrinking Nano images sometimes enables a relaxed RJMP vector.
No previous timing assertion is re-labelled as a new run.

| Target | Single-stream program, without audio | Change | Static RAM / peak stack |
| --- | ---: | ---: | ---: |
| ATtiny88 generic | 3627–3628 B | −36 B | 418 / ≤27 B |
| ATmega328P Nano | 3016–3017 B | −40 B | 417 / ≤24 B |

Nano passes all 22 cases at each rate. Tiny passes 22/22 at 8 kHz, 9/22 at
12 kHz and 2/22 at 16 kHz, exactly as before. Configuring a clock does not
admit a workload with underruns. The nearest fixed divisors remain 2000
cycles at 8 kHz, 1336/1333 at nominal 12 kHz for Tiny/Nano, and 1000 at
16 kHz. There is no runtime three-way timer selection.

The matrix's higher rates are header-retagged timing probes. `wideband.json`
separately checks eight genuinely encoded P4/P6 streams from actual
44.1/48 kHz sources at 12/16 kHz on Nano. All 143360 samples match the
unchanged encoder/C model after the same normalization, with zero IRQ
underruns. These held-out excerpts were prepared in the earlier Tiny12
experiment; they are not upsampled old WebUI recordings. No quality
improvement or broad Tiny high-rate admission is claimed.

Eight frontend tests check actual resampling, unchanged 8 kHz encoding,
selected-rate C decoding and rejection of mismatched/invalid settings.

Reproduce the interrupt matrix on Linux/WSL:

```
python3 Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr_player22.py build/fixed-rates --rates 8000 12000 16000 --jobs 3
```

Use `--wsl Ubuntu` on Windows. `source-transition.json` binds the new source
and measurements while preserving the historical automatic-player reports.

## WebUI images rebuilt at 8 kHz

All 18 public LPX images are rebuilt with the default single frequency,
including the Owl dialogue. `web-rebuild.json` binds each new HEX to its
independent ASM rebuild and the unchanged public WAV/C output. The old
publication's retained PWM hashes are identical for all 345470 samples;
every new full playback has zero IRQ underruns. All 26 LPX/audio assets
remain byte-identical. `web-transition.json` preserves the metadata/cache
transition separately from the decoder change.

| Image | Program excluding audio | Change | Largest complete image |
| --- | ---: | ---: | ---: |
| Tiny88 release | 3629–3630 B (3.544–3.545 KiB) | −36 B | 5510 B |
| Nano single stream | 3016–3017 B (2.945–2.946 KiB) | −40 B | 4898 B |
| Nano dialogue | 3295 B (3.218 KiB) | −44 B | 8844 B |

The single-stream Nano remains below 3 KiB. All Tiny images fit both the
6012-byte standard USB application region and 6.5 KiB project cap. The
catalogs record compile-time 8 kHz selection; shared WebUI cache keys and
the speech asset inventory are refreshed. No source recording or compressed
sound was regenerated.
