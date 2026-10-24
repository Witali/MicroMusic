# Frozen HQ4 corpus: clipping and quantization audit

The 20 current 2.048-second corpus models were inspected without changing any
model or decoder. This is an exact PC arithmetic/file audit, not AVR or hardware
qualification. Inputs and per-model source hashes are retained in `audit.json`.

| Check, across 307200 decoded samples | Result |
|---|---:|
| Lattice subtraction wraps | 0 |
| Lattice state-addition wraps | 0 |
| Negative-128 multiplication cases | 0 |
| Output DAC endpoints, 0 or 255 | 0 |
| FLOAT WAVs sample-exact to the frozen byte decoder | 20 / 20 |
| Unique decoded amplitude levels per clip | 33–99 |
| Absolute decoded peaks | 0.1953125–0.5703125 |
| Longest equal-sample run at observed global minimum/maximum | 1 / 1 for every clip |
| Local positive/negative plateaus, at least two equal samples | 19248 |
| Fractional Q4 products | 3059729 / 4608000 = 66.4004% |

There is no evidence of saturating amplitude limiting, internal modulo overflow
or clipping/rescaling during FLOAT-WAV conversion in these particular outputs.
The independent `hq4_phase.render(..., False)` output matches the frozen
`model.decode(..., 0)` oracle, the packed stream and `expected.raw` exactly.
Every decoded WAV is mono IEEE float, and every sample equals
`(exact_unsigned_byte - 128) / 128`.

The visible flat steps are real, but they are not a shared flat ceiling: global
extrema are isolated samples. Many local peaks occupy a repeated amplitude
code below the DAC limits. Output quantization is 1/128, the models use only
33–99 distinct codes, and the lattice discards fractional product bits. Mean
rounding error per multiplication is -0.405 to -0.251 in signed lattice sample
units. These measurements establish coarse quantization; they do not isolate
how much of the perceived creak comes from rounding, excitation shape, pitch
tracking, filter envelope, frame transitions or their interaction.

The shared four-sample voiced pulse and exclusive pulse/noise source can make
different voices sound similar. The architecture gives a plausible explanation,
not proof that replacing the pulse alone will improve quality. Earlier source
shape experiments failed perceptual guards after joint refitting.

There is a separate level-fidelity defect: the two quiet references have output
RMS/reference RMS ratios of 20.7547 and 67.5771. This is recorded in the original
benchmark and retained here. The prepared quiet inputs were not normalized;
the relative-gain encoder initializer amplifies them. Fix gain fidelity as an
encoder constraint and report raw levels alongside any optional listening gain.

The original `ru_russia_b` float reference still has its one resampling overshoot
sample at 1.0130626. The audit does not convert it to clipped PCM16.

## Reproduce

```powershell
python tools/audit-speech-clipping.py `
  --manifest build/speech-corpus/manifest.json `
  --references build/speech-corpus `
  --models build/speech-corpus-benchmark/short/models `
  --output build/speech-clipping/audit.json
python tools/test-speech-clipping.py
```

Four focused tests distinguish local/observed-extrema plateaus from DAC limits,
monotonic quantized steps from local peaks, unchanged FLOAT conversion from
rescaling, and genuine internal wraps from an otherwise valid output WAV.
The existing frozen `hq4_phase` implementation and its arithmetic tests are
reused unchanged. WAV-byte hashes identify this capture; the benchmark writer
can include timestamp metadata when regenerating WAVs, so stable PCM/stream
hashes and exact sample equality are also recorded separately.
