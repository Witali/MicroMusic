# Eight selectable excitation forms within the ATtiny13A budget

The requested extension is **four existing forms plus four additional slots**.
The decoder selects one of eight forms per voiced frame. All sixteen gain
levels remain available. This is a separate `hq4-q3-pulsebook8-v1` format;
ordinary four-form files and public firmware are unchanged.

The selected complete Vinni image occupies **1012 Flash + 64 EEPROM bytes**,
including the decoder, full phrase, stop marker and alignment. Three AVR engines
reproduce its integer PCM exactly. The automatic fit improves STOI/eSTOI and the
existing whole-clip spectral objective slightly. It does **not** meet STOI 0.90
or the spectral-loss target 0.3449755536. Hardware has not been tested.

## Measurements and selection

The reference is the complete 22,272-sample, mono 7500 Hz
[`vinni.wav`](../../../../web-player/audio/originals/vinni.wav), SHA-256
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
The protected four-form starting model is
[`stronger32-start/before`](../q3-perceptual-fit/stronger32-start/before/model.json).
The duration, integer arithmetic and metric policy are held fixed: HP70 and one
whole-clip RMS match for the existing spectral objective, without time warping
or frequency adjustment. Raw DC and strict partial bounds are reported separately.

| Complete model | Flash | EEPROM | Speech stream | STOI | eSTOI | Spectral loss ↓ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Four-form starting model, short byte table | 972 | 64 | 620 | 0.849533 | 0.659937 | 0.491184 |
| Same PCM in eight-form, four-tap decoder | 996 | 64 | 620 | 0.849533 | 0.659937 | 0.491184 |
| Initial four-tap joint fit | 1010 | 64 | 635 | 0.851957 | 0.662708 | 0.490912 |
| Selected four-tap refit | **1012** | **64** | **637** | **0.852952** | **0.664348** | **0.490770** |
| Remove new forms from selected model, refit selectors/gains | 984 | 64 | 632 | 0.850864 | 0.660479 | 0.490296 |

Against the starting model, the selected STOI gain is 0.003419 and spectral
loss falls only **0.0844%**. These small gains are not evidence of natural-sounding
speech or the requested 30% spectral improvement. The selected model uses seven
forms: 0, 1, 2, 3, 5, 6, 7. Slot 4 is available but unused; no penalty forces it
to be selected. All model parameters are fitted automatically.

The ablation fixes the fitted pitches, durations, filter coefficients and first
four forms. At each of six frames using an upper selector, it evaluates every
lower selector with the current gain or gain ±1 through the full decoder. Its
72 greedy trials lower STOI/eSTOI but improve spectral loss. This supports a
limited intelligibility contribution from the extra forms in this fit, **not**
universal superiority over a separately optimized four-form encoder. The
four-form ablation is also a smaller, useful Pareto alternative.

An eight-tap search was retained as a negative result: 6000 proposals yield a
balanced finalist with STOI 0.854278 but worse spectral loss 0.494941. Its guarded
selection therefore retains the unchanged starting PCM. More taps consume EEPROM
that could otherwise store speech and reduce stream capacity from 649 to 633.
Unselected finalists have model/metric evidence, but no claim of AVR qualification.

## Stream and complete memory cost

The existing spectral byte holds the low two form bits in bits 4–5 and gain in
bits 0–3. The high form bit occupies unused bit 2 of the extended duration byte
(`0xc4..0xc7`). An upper selector forces this extended header when the pitch and
duration would otherwise allow a compact header. Its cost is counted by the
actual packer during every trial. Lower selectors retain the original bytes.

Eight four-tap forms are stored as **16 EEPROM bytes of signed nibbles**, leaving
48 EEPROM bytes for a speech prefix. The reader then switches to the Flash
suffix, transparently even inside a packet. The selected core is **422 bytes**;
589 speech bytes remain in Flash, followed by EOF. Total: 422 + 589 + 1 = 1012.
The complete stream capacity is 649 bytes and is verified with a 1024-byte image.
Both Flash and EEPROM images must be programmed together.

The third selector bit adds 12 code bytes to the four-tap nibble decoder. Its
base address lives in R13, cleared for every compact header; IRQs preserve it.
Nibble addressing also preserves the lag carry through the IRQ. Compared with
the smaller 398-byte four-form byte-table core, the complete eight-form core
costs 24 additional bytes. The same-PCM control isolates this cost from fitting.

Duplicate forms and selectors on zero-gain/unvoiced frames are canonicalized to
the cheapest equivalent lower slot. The first fit used two expensive duplicate
rows. Canonicalization reduced its stream **635 → 630 bytes**, preserving every
PCM byte and all four wrap counters, before another 3000 proposals used the
freed slots. This is an exact recoding, not an audio approximation.

## Qualification and limits

[`qualification.json`](qualification.json) records the complete test run,
source fingerprints and actual image evidence. The selected build reproduces
**66,816 samples** in reference JS, optimized WASM and unoptimized WASM: the
complete phrase followed by two phrase lengths of silence. It has zero PCM
mismatches, missed samples, lost overflows or intermediate wraps; minimum
preparation slack is **199 cycles** and maximum SRAM span including stack is
**28 bytes**. The measured controller clock is 9.6 MHz and sample rate 7500 Hz.

The tests cover selectors 0–7, all sixteen gains, every header/duration/filter
packet transition, widths 4/8/16, both physical encodings, upper-to-lower selector
clearing, IRQ carry preservation and actual maximum-size images. There are
**73,728** real lookup/gain/flag/IRQ cases across the three engines. The complete
speech suite includes the protected existing examples.
Search reports deliberately retain `avr_verified: false` from candidate export;
subsequent qualification of the selected model is recorded in its `build.json`.

The independent rescore of the final model exactly reproduces all stored quality
metrics and matches actual AVR PCM:
[`independent-rescore.json`](refit-four-tap/independent-rescore.json).
The raw mean is still **+0.078330**, versus +0.077203 before. Matched harmonic
frequency error worsens from approximately 53.00 to 57.07 cents, despite the
small improvement in the whole spectral objective. Strict per-partial 5 dB
bounds fail. DC and harmonic accuracy remain open work; this extension does not
solve them. The new format has been fitted on Vinni only, not established as a
RU/EN corpus improvement.

## Retained sources and reproduction

[`manifest.json`](manifest.json) maps duplicate finalists to one retained model
and identifies source revisions. Initial four/eight-tap runs used `1733805`;
the canonicalized refit and ablation use `230b9ca`. Their reports retain seeds,
proposal counts, guard rejections, metric policy, source and input hashes. Initial
runs were 6000 proposals each, seeds 24108/24109; the refit used 3000, seed 24110.
All three ran the exact full clip and rejected wraps, peaks above 115 and steps
of at least 48. Guarded exports preserve starting STOI, spectral loss and eSTOI.

From the repository root, using Python with NumPy, SciPy, SoundFile, Numba and
the existing speech-metric dependencies, first rebuild the same-PCM control:

```powershell
python tools/build-q3-pulsebook8.py --model ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json --output build/q3-pulsebook8/baseline --avr-bin $env:AVR_BIN --node $env:NODE
```

Reproduce the canonicalized refit with its retained starting model:

```powershell
python tools/probe-q3-pulsebook8.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-pulsebook8/initial-four-tap/guarded/model.json --core-report build/q3-pulsebook8/baseline/build.json --output build/q3-pulsebook8/refit4 --proposals 3000 --seed 24110
python tools/build-q3-pulsebook8.py --model ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/guarded/model.json --output build/q3-pulsebook8/refit4/guarded/avr --avr-bin $env:AVR_BIN --node $env:NODE
python tools/ablate-q3-pulsebook8.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q3-pulsebook8/refit-four-tap/guarded/model.json --output build/q3-pulsebook8/ablation
python tools/test-speech-quality.py
python tools/probe-q3-short-eeprom.py --model ATtiny13A/Sound/research/q3-perceptual-fit/stronger32-start/before/model.json --output build/q3-short-eeprom --avr-bin $env:AVR_BIN --node $env:NODE
node tools/render-q3-pulsebook8-comparison.mjs
```

Generated HEX/ELF/PCM/WAV files remain under ignored `build/`. The before/after
listening artifacts use actual verified paired images through the site's
unmodified WASM audio renderer, identical 9 kHz filter and default catalog gain,
with no added normalization. Their paths and hashes are recorded in
[`listening.json`](listening.json). Research models and measured results are
retained here; generated firmware binaries are reproducible from those sources.
