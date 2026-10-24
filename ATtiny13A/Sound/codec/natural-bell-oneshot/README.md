# Compact T1 voice with a retained bell

This separate one-shot experiment addresses the perceived harshness of the
new bell-plus-voice example. It retains the three-oscillator event and the
entire 19328-sample excerpt. A source-fitted HQ4 voice stream is refitted for
the integer output recurrence `y = s8(x + previous - (previous >> 1))`.
The lattice and its frame-phase convention remain unchanged.

The independent output state uses r11 after the bell has finished. It is
explicitly cleared in `start_voice`; the bell bypasses the output filter.
The hot path needs five instructions by subtracting the shifted old value
directly from r11 before replacing it with y. This is bit-identical to the
six-instruction version using a temporary register.

Both retained variants use **1018 Flash bytes and 64 EEPROM bytes**:

| Part | Bytes |
| --- | ---: |
| Decoder, bell, T1 stage and one-shot control | 572 |
| Bell descriptors | 15 |
| Refitted voice stream | 430 |
| End marker | 1 |
| EEPROM sine table | 64 |

Program both Flash and EEPROM HEX files. No EEPROM is written during playback.
No public firmware is replaced by this research change.

## Controlled and balanced variants

The controlled variant preserves the earlier hybrid's first 6528 output samples
exactly, including its phases, frequencies, integer gains 3/2/2, onset and decay.
The T1 voice is louder at its raw PWM level, so this unchanged bell becomes
quieter relative to the voice. That is retained as a controlled comparison,
not hidden by independently amplifying the two parts for listening.

The balanced variant automatically searches all safe integer gain triples
1..7 with sum at most 15. It leaves oscillator steps, phases, onset, envelope,
voice data and executable code unchanged. Selection compares absolute
128/256/512-sample spectral magnitudes after scaling the source using the new
voice/source-voice RMS ratio, plus a small relative-level penalty. The selected
gains are **6/4/3**. The amplitude cap bounds the sum of the signed LUT products
well inside the signed-byte range; the real assembled image is also checked
sample by sample. Silent or duration-mismatched input is rejected.

| Metric | Earlier hybrid | Controlled T1 | Balanced T1 |
| --- | ---: | ---: | ---: |
| Voice STOI | 0.78859 | 0.82508 | 0.82508 |
| Voice eSTOI | 0.44984 | 0.51995 | 0.51995 |
| Voice log spectral error | 0.85529 | 0.80218 | 0.80218 |
| Whole-clip STOI | 0.67211 | 0.69861 | 0.69755 |
| Whole-clip eSTOI | 0.39356 | 0.43648 | 0.46271 |
| Whole-clip log spectral error | 0.80191 | 0.77184 | 0.73593 |
| Bell/voice raw RMS ratio | 1.01128 | 0.60413 | 1.15901 |

The source bell/voice RMS ratio is 1.24921. The balanced model is closer to that
relationship. These improvements do not by themselves establish naturalness;
the candidate needs level-matched listening. The underlying voice still uses
a very small pulse/noise source and an eight-stage quantized spectral model.

## Verification and reproduction

Each actual image matches **57984 samples** in the reference, optimized WASM
and unoptimized WASM engines: 19328 complete effect/voice samples followed by
38656 midpoint-silence samples. There are no missed interrupts or samples,
lattice wraps, output-filter wraps, or adjacent output steps of 48 or more.
The largest signed output is 62. Sample intervals are 1279..1281 cycles and
the tested minimum foreground slack is 326 cycles. SRAM span including the
measured stack is 30 bytes. Physical hardware has not been tested.

```text
python tools/test-natural-bell-hq4.py
python tools/build-natural-bell-hq4.py --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav --bell-model build/new-speech/bell-hybrid/result/model.json --voice-model build/new-speech/natural-timbre/tail-voice-430/model.json --output build/new-speech/natural-bell-hybrid/result --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
python tools/build-natural-bell-hq4.py --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav --bell-model build/new-speech/bell-hybrid/result/model.json --voice-model build/new-speech/natural-timbre/tail-voice-430/model.json --balance-bell --output build/new-speech/natural-bell-hybrid/balanced --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
```

Two focused tests recover a known 6/4/3 target while proving that timing,
frequency, phase and the source object remain unchanged; they also check
descriptor headroom and rejection of a silent voice. The complete AVR checks
independently cover output-state reset, the bell/voice transition and the tail.

Compressed models, quality reports and build/verification reports are saved at
`ATtiny13A/Sound/research/new-speech-naturalness/bell-hybrid-t1/{controlled,balanced}/`.
The ignored build folders contain the usable Flash/EEPROM HEX pairs and WAVs.
Each `comparison.wav` is `original -> earlier hybrid -> T1 candidate`, with a
common 70-Hz highpass, whole-track RMS matching and one shared peak cap.
