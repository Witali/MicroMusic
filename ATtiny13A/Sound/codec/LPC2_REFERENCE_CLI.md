# Unmodified LPC2 Improved reference codec without a browser

`tools/lpc2-reference-cli.mjs` executes the codec functions from
`ATmega328/Sound/reference/lpx3/lpc2_v2_reference.html` in a Node VM. The
original HTML and `lpx3_decoder.js` are unchanged. This is a quality reference
and a bridge to LPX3 residual experiments; it is not an AVR implementation.
There is no claim that its decoder or speech data fit an ATtiny13A.

Run with the repository Node runtime, for example:

```powershell
C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe tools/lpc2-reference-cli.mjs --input request.json --output build/lpc2-reference/example
C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe tools/lpc2-reference-cli.mjs --base build/lpc2-reference/example/base.lp2 --output build/lpc2-reference/independent
```

The input JSON contains `sampleRate` and a nonempty mono `samples` number
array. An optional `config` object accepts only the fields shown here:

```json
{
  "sampleRate": 7500,
  "samples": [0.0, 0.1, -0.1],
  "config": {
    "frameMs": 20, "windowMs": 32, "pre": 0.85,
    "voicing": 0.38, "pitchSmooth": 0.65, "repeat": 0.05,
    "pitchMin": 65, "pitchMax": 850, "postfilter": 0.35
  }
}
```

These values are the adapter defaults. Use already prepared 7500 Hz audio for
comparisons. Input accepts integer sample rates 4000 through 65535 Hz because
the native container stores the rate in a 16-bit field. Finite samples up to
absolute 16 are accepted, allowing floating-point WAV headroom. Input is cast
to Float32, as in the browser's normalization-disabled path. The adapter does
not resample, normalize gain, remove DC, crop, or choose settings by phrase.
External pitch guides are rejected. The original pitch estimator and its
source-derived smoothing remain in use.

## Files and independent decoding

The outputs are:

- `base.lp2`: the complete native LPC2 v2 byte stream, including its 36-byte
  header. This is the only information required for subsequent base decoding.
- `decoded-post-0.f32`, `decoded-post-0.1.f32`, and
  `decoded-post-0.35.f32`: raw little-endian Float32 output from the original
  `synthLPC2`. A custom configured strength is also exported.
- `decoded.f32`: the configured postfilter output, default 0.35. It has exactly
  the header's sample count.
- `coefficients.f64le`: sample-major little-endian Float64 predictor
  coefficients, shape `[samples, 10]`, containing `a[1]` through `a[10]`.
- `meta.json`: decoded header, frames, frame gains/F0/LSFs, coefficient
  convention, output hashes, source provenance, and clipping audit.

`--base` uses no source PCM, analysis output, or configuration JSON. Its
coefficient trajectory is the existing **LPX3 v1** convention: eight
subframes per LPC2 frame, interpolation in stabilized LSF space at each
subframe midpoint. These coefficients support the original closed-loop
LPX3 residual decoder. Native LPC2 synthesis also has a transient fast-attack
rule; consequently this exported trajectory is explicitly labeled LPX3,
not a claim that it captures every native LPC2 excitation detail.

Each decode independently compares the native HTML descriptor unpacking
and coefficient trajectory with the existing pure `lpx3_decoder.js`.
Tests additionally construct a complete LPX3 container and reproduce that
decoder's Float32 PCM exactly using only the exported samplewise coefficients.
This checks the interpolation and history sequencing against an independent
consumer.

## Amplitude and fidelity boundaries

The adapter preserves native synthesized floating-point values, including
values outside `[-1, 1]`. It does not perform the browser page's separate
output brightness, high-pass, DC, or limiter processing. Comparisons to the
page must therefore specify those options; raw codec comparisons use the
same processing on both sides. Writing these outputs to integer PCM with
automatic saturation would change the signal and must not be done silently.

For each synthesized postfilter strength, the audit counts original
protective clamp arguments outside `[-8, 8]` and records their maximum
absolute value. The observation is enabled only during synthesis. Original
codec source and clamp return values remain identical: a same-value VM
`Math.min` observer reads calls from the original lexical clamp. Tests compare
all output samples with observation disabled and enabled, then force a valid
high-energy descriptor to exercise an actual protective clamp.

Raw output statistics include min/max/mean, samples outside `[-1, 1]`, exact
`+8/-8` samples, zero samples, and adjacent equal-value runs. Output above one
does not itself prove that the native protective clamp fired; these are
reported separately. These statistics also do not by themselves establish
audible clipping or naturalness.

## Source integrity and malformed input

The VM runs the exact normalized-LF codec region from `const LPC_CHIRP=` up
to `function splitForBlocks(`, plus the original clamp/tick declaration.
Only no-op progress/status callbacks and the timer are supplied by the host.
Metadata records the raw and normalized HTML hashes, extracted line range
and hash, pure decoder hash, and adapter hash. Decoder analysis does not
consult the original waveform.

The wrapper checks canonical header values, byte lengths, frame count,
padding, consumed payload bits, and exact native v2 repacking. It rejects
truncated or structurally inconsistent streams. LPC2 has no checksum:
a modified payload that is still a valid stream cannot generally be detected
as corruption.

Validation:

```powershell
C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe --test tools/test-lpc2-reference-cli.mjs
```

Five tests cover deterministic encoding/provenance, independent LPX3 PCM,
structural corruption, same-value clamp auditing, and parameter-only CLI
decoding with exact raw PCM and coefficients.
