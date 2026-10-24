# Experimental bell prefix and HQ4 voice

The final phrase in `vhodit-i-vyhodit` contains a prominent ringing sound before
the voice. This separate candidate keeps the complete 19328-sample excerpt:
6528 prefix samples followed by 12800 samples decoded by the existing HQ4
lattice. The source's later bell/voice overlap remains in the HQ4 portion.
There is no claim that three stationary partials recreate that overlap exactly.

The assembled candidate uses **986 Flash bytes and all 64 EEPROM bytes**:

| Part | Bytes |
| --- | ---: |
| Decoder, oscillator and one-shot control | 560 |
| Three phase/step/amplitude descriptors | 15 |
| Unchanged HQ4 voice stream | 410 |
| End marker | 1 |
| EEPROM sine table | 64 |

Both `firmware.hex` and `eeprom.hex` must be programmed. An erased EEPROM is
not a valid waveform table for this image. No EEPROM writes occur during use.
The public HQ4 decoder and its selected images remain unchanged.

`../bell_model.py` defines the exact integer oscillator specification. Each
partial has a 16-bit phase and step; the upper six phase bits index a signed
64-point sine table with amplitude 31. The existing software Q4 multiply scales
each partial. Their sum is rounded with a one-unit offset and arithmetically
shifted once per selected decay interval. A leading silent interval is retained.
Descriptor RAM overlaps the voice coefficient/state RAM; voice startup clears
the filter state and initializes its first complete spectral frame. After the
complete voice, the real AVR emits centered PWM silence indefinitely.

The voice model supplies the prefix boundary. Within that prefix, onset is
detected automatically from 64-sample RMS blocks using the initial quiet noise
level. FFT peaks and a local least-squares refinement propose frequencies;
three-partial combinations, integer phases, integer gains and a common decay
interval are chosen automatically. The bell is scaled using the decoded
voice/source-voice RMS ratio, preserving their relative level before the final
listening gain adjustment. This analyzer expects a quiet interval before the
event; it is not a general semantic effect/voice classifier.

The original bell's partial frequencies move during the recording. A constant
tone optimized only for whole-waveform mean square error can therefore collapse
toward silence. The retained fit evaluates 128/256/512-sample spectral magnitudes
with a smaller waveform error term and estimates attack phase locally. It
selects approximately **646.25, 970.80 and 1162.15 Hz** here, with Q4 gains
2, 2 and 3. These frequencies were measured, not supplied as phrase-specific
constants. Fine frequency drift and weaker partials are approximated.

Compared with the complete ordinary HQ4 candidate, the bell's log spectral
error falls from 1.17986 to 0.68424, and whole-clip error falls from 0.94468 to
0.80191. The compact voice stream trades some intelligibility: voice-only STOI
is 0.78859 versus 0.80587 and eSTOI 0.44984 versus 0.48365. Whole-clip STOI is
0.67211 versus 0.75440; that measurement includes the non-speech ringing.
This candidate improves a specific effect and is retained as an alternative,
not as the best speech score. The decoded bell/voice RMS ratio is 1.0113;
the original ratio is 1.2492. Listening files use a common 70-Hz highpass and
matched whole-clip RMS with one shared peak cap.

Reproduce from the repository root with the local Python dependencies and AVR
toolchain on their configured paths:

```text
python tools/test-bell-hq4.py
python tools/encode-bell-hq4.py --reference build/new-speech/tail-input/vhodit-i-vyhodit/reference.wav --voice-model build/new-speech/bell-hybrid/voice-model.json --baseline-model build/new-speech/hq4/vhodit-i-vyhodit-final/model.json --output build/new-speech/bell-hybrid/result --avr-bin PATH_TO_AVR_BIN --node PATH_TO_NODE
```

Four tests independently check scalar phase/rounding/decay arithmetic, descriptor
endianness, timing/storage bounds and audible automatic fitting under frequency
drift. The actual assembled candidate matches all **57984** expected samples
(19328 speech/effect plus 38656 midpoint-silence samples) in the reference,
optimized WASM and unoptimized WASM engines. No samples or interrupts are lost.
Sample intervals are 1279..1281 cycles, minimum tested foreground slack is 359
cycles and measured SRAM span including stack is 30 bytes. Physical hardware
has not been tested.

Compressed model/build/quality reports are retained by the new-phrase packaging
workflow under `ATtiny13A/Sound/research/new-phrases/vhodit-i-vyhodit-final/hybrid/`.
Generated audio, binaries, EEPROM images and comparisons stay in ignored
`build/new-speech/bell-hybrid/result/`.
