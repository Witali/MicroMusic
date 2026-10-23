# HQ4 naturalness audit and continuous-phase experiment

The user described the old Vinni voice and the new bell-plus-voice example as
sounding like a distorted guitar. An independent signed-byte lattice audit
checked actual internal arithmetic before proposing a clipping fix.

## Findings before changing the decoder

`initial-audit.json` covers the frozen public Vinni, the new complete tonal-HQ4
excerpt and its separately fitted 410-byte voice stream. In all three cases:

- No lattice subtraction or state-addition overflow occurs.
- No negative-128 multiply anomaly occurs and no output reaches PWM 0 or 255.
- The largest signed output peaks are respectively 62, 53 and 41.

Thus signed-byte clipping is not the cause of the perceived distortion in
these specific retained models. This does not prove that arbitrary streams
cannot overflow: the test suite includes a deliberately overflowing model.
Fractional products are common: 197409 of Vinni's 334080 products discard a
fraction, with mean error -0.294 output units per product. This describes the
rounding arithmetic; the errors pass through a stateful lattice and cannot be
summed as an output DC prediction.

Vinni forces 110 voiced frame phase restarts. Their old countdowns differ from
their new periods by 2625 samples in total. The voice model forces 78 restarts.
Frame restarts therefore change the pulse timing even without changing pitch.
The four-sample periodic excitation and limited spectral model remain plausible
contributors to the buzzy sound. The audit alone does not separate their
perceptual contributions.

## Separate continuous-phase decoder

`codec/hq4_phase.py` independently implements and instruments the lattice. Its
legacy mode matches all three retained public streams byte for byte. Its
continuous mode initializes the pulse countdown from the first frame's period
and retains it at all subsequent frame updates. In `codec/phase-oneshot/hq4.S`
the same instruction is moved from frame parsing to startup, keeping the
decoder at **406 bytes**. No existing decoder, stream format or public catalog
was changed.

This is a continuous countdown, not an interpolated fractional oscillator.
Unvoiced frames freeze the countdown. In particular an initial period of zero
can delay the first later periodic pulse by up to 256 samples; that behavior is
explicitly covered by an independent lifecycle test. Internal pulse-event
statistics include zero-gain frames and should not be read as acoustic F0
estimates. Removing all frame resets improves pulse-clock continuity but does
not guarantee correct fundamental frequency or natural voice quality.

Two independent 5000-proposal refits use exact continuous-phase synthesis,
fixed sample counts and original stream budgets. The search jointly changes
HQ4 parameters and boundaries. It rejects intermediate overflows, large output
steps and peaks. Selection balances STOI, multiscale spectral error and a small
penalty for the difference-RMS/signal-RMS ratio relative to the reference.
This roughness measure is a diagnostic, not a listening score.

| Metric | Vinni old | Vinni refitted phase | Voice old | Voice refitted phase |
| --- | ---: | ---: | ---: | ---: |
| STOI | 0.85960 | 0.82716 | 0.78859 | 0.79723 |
| eSTOI | 0.69099 | 0.64122 | 0.44984 | 0.44759 |
| Log spectral error | 0.81288 | 0.74154 | 0.85529 | 0.80473 |
| Difference RMS / signal RMS | 0.62976 | 0.61580 | 0.89411 | 0.86576 |

The corresponding reference roughness ratios are 0.71383 and 0.93403; simply
making the output smoother moved this diagnostic farther from the reference.
Vinni's power fraction above 2500 Hz falls from 0.03486 to 0.03070, while the
reference fraction is 0.01019. Its raw output/reference RMS ratio changes only
from 0.55635 to 0.55024. Level-matched comparisons apply the same 70-Hz highpass,
individual RMS matching to the original and one shared peak cap.

**Neither phase candidate is promoted.** Vinni loses intelligibility; the new
voice does not preserve both eSTOI and the reference roughness relationship.
The results are retained as negative evidence, despite the improved average
spectral errors. Phase restarts alone do not explain or fix the complaint.

Both actual one-shot images match all expected PCM in the reference, optimized
WASM and unoptimized WASM emulators, including two whole-phrase lengths of
centered silence. Vinni is 1024 Flash bytes; the voice-only image is 818 bytes.
Neither uses EEPROM. This is emulator verification, not physical testing.

## Reproduction

The source MP3s remain external. The public Vinni source is the previously
retained exact 7500-Hz `build/hq4-preview/vinni/original.wav` in the main checkout;
the final phrase's prepared source and initial model remain in ignored
`build/new-speech/`. Input hashes and complete compressed parameters are saved
in the adjacent per-case reports.

```text
python tools/test-hq4-phase.py
python tools/probe-hq4-phase.py --case vinni --proposals 5000 --seed 23131 --output build/hq4-naturalness-audit/vinni --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
python tools/probe-hq4-phase.py --case tail-voice --proposals 5000 --seed 23132 --stream-budget 410 --output build/hq4-naturalness-audit/tail-voice --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
```

Four tests cover retained-byte equivalence, phase continuity, the zero-period
startup case and real internal overflow detection. Listening comparisons under
the ignored output folders are `original -> legacy -> refitted phase`.
Models, quality histories and verified build reports are retained here; audio,
HEX, object files and temporary outputs are not committed.
