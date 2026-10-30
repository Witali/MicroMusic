# QMF quality budget after exact acceleration

This is an offline **linear filter response** screen, not a listening test,
speech quality score, compiled alternative or timing admission. The production
profile remains Q7/16 taps. The exact optimization changes no PCM.

`tools/analyze_qmf_budget.py` reads the unmodified vendored Xiph 1.2.1 `h0`
coefficients and reproduces the production 16-tap coefficients exactly. It
also evaluates centered 20/24/32-tap alternatives, scaled before Q7 rounding.
Responses use a 2-Hz grid at 16 kHz, referred to ideal DC. The full Xiph
coefficient response is a reference, with its original BSD provenance retained.

| Linear filter | Response range, 0–3 kHz | Largest response, 5–8 kHz | Mirrored half-history |
| --- | ---: | ---: | ---: |
| Current 16 taps, Q7 | -0.097 to +1.077 dB | -23.520 dB | 64 B |
| 20 taps, Q7 | -0.641 to +0.115 dB | -25.191 dB | 80 B |
| 24 taps, Q7 | -0.110 to +0.370 dB | -27.768 dB | 96 B |
| 32 taps, Q7 | -0.067 to +0.236 dB | -31.551 dB | 128 B |
| Full Xiph 64 taps | -0.002 to +0.002 dB | -79.527 dB | 256 B in this mirrored design |

The 20-tap candidate has more attenuation within the chosen passband than
the 24-tap candidate; adding taps is not a complete quality decision. HB1
folding remains another limit on high-band reconstruction regardless of QMF.
The full Xiph row describes coefficients, not the actual memory allocation
of its different original implementation.

## Constraints before implementing a candidate

- All four Q7 tap sets fit signed8 coefficients and signed24 accumulation.
  Per-phase absolute sums are 236, 228, 245, 250; each satisfies
  `sumAbs*32768+32 < 2^23`. Recompute the proof after any coefficient change.
- A 40-pair call returns a 16- or 20-tap history cursor to zero. With 24 or
  32 taps it does not: persist the cursor (and its reset), or measure a
  history rotation. Do not silently restart the ring at each subframe.
- The current mirrored `STD Y+displacement` pattern needs displacement
  `2*taps+3`. At 32 taps this is 67, beyond the ISA's 63 limit; a different
  addressing scheme is necessary.
- Nonzero coefficient products/frame are 2560, 3200, 3840 and 4480 for
  16/20/24/32 taps. Those counts are not cycle predictions. More history,
  coefficient loads, alias lifetimes and the callback deadline also matter.

The present worst observed bare decoder frames leave 77148 / 75900 cycles
of a 320000-cycle frame in WB9.8/WB12.8, **before** output/ISR/transport.
With the tested 25600-cycle extra foreground load, the arithmetic remainder
is 51548 / 50300, still before output/ISR. It is not an admitted budget for
more taps. Active-IRQ queue minima are only 7 / 6 samples and depend on
when work occurs within the frame, not just its mean.

## Next bounded experiment

Start with a separately named 24-tap Q7 profile and equivalent C reference.
Its linear response improves this screen at +32 B history, plus cursor
storage or rotation. Compare against full Xiph synthesis with delay aligned
Russian/English speech, quiet speech and non-speech. Retain original levels
and measure clipping, waveform/spectral error and listening examples.
Admit it only after actual AVR cycle/memory and continuous PWM tests, first
normally and then with the selected foreground load. Keep the existing exact
16-tap profile available if the tradeoff is unfavorable.

Generate the retained screen with:

```sh
python Codecs/Speex/AVR/tools/analyze_qmf_budget.py --out Codecs/Speex/AVR/reports/wb-qmf-budget.json
```

`reports/wb-qmf-budget.json` includes coefficients, bounds, resource counts,
frequency samples and source hashes. It carries no decoder support claim.
