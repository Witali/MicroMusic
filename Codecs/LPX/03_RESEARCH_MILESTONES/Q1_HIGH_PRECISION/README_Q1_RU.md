# MicroMusic — LPX4: Q1 fractional LPC experiment

Experiment dated 2026-10-23. This code remains a research prototype, not a
verified 16 MHz real-time playback firmware.

## Experimental goal and outcome

Store one additional fractional bit in the LPC prediction feedback, deemphasis
and brightness filter; output signed PCM16 directly, before PWM.

- Exact Q1 reference path uses int64_t products, **for host verification only**.
- Optimized `LPX4_FAST_SPLIT_Q1` produces identical PCM16 without 64-bit
  multiplication in the LPC tap loop: 16x16-bit products plus remainder carry.
- Compared against a Q12 fractional reference, the numerical signal/error
  ratio (amplitude of Q12 reference over error) exceeded 60 dB on both short
  samples. This is **not** analog output SNR and is **not** the fidelity to
  original human speech.
- One additional fractional bit creates real odd PCM16 sample values, not just
  a 16-bit WAV file containing multiples of two.
- The separate signal/error ratio against the original PCM16 waveform and STOI
  are in `reports/METRICS_Q1.json` and the private sample archive.
- The old fixed-point truncation sometimes matches the encoder's original
  calibration better! Without retraining, simply adding precision can reduce
  waveform fidelity by multiple dB; therefore each candidate is re-encoded.

## Build native decoders

From the `project/` subdirectory:

```bash
g++ -O3 -std=c++11 -Isrc src/Lpx4HybridCore.cpp tests/decode_s16_host.cpp -o decode_legacy
g++ -O3 -std=c++11 -DLPX4_WIDE_FRAC=1 -Isrc src/Lpx4HybridCore.cpp tests/decode_s16_host.cpp -o decode_q1_64bit
g++ -O3 -std=c++11 -DLPX4_WIDE_FRAC=1 -DLPX4_FAST_SPLIT_Q1=1 -Isrc src/Lpx4HybridCore.cpp tests/decode_s16_host.cpp -o decode_q1_fast

g++ -O3 -std=c++11 -DLPX4_WIDE_FRAC=12 -Isrc src/Lpx4HybridCore.cpp tests/decode_s16_host.cpp -o decode_q12_reference
./decode_q1_fast your_audio.l4hy output.pcm16le

PYTHONPATH=tools:tests python3 -m unittest discover -s tests -p 'test_*.py' -q
```

## Automatic Q1 retuning using source voice data

Inside the `project/` directory run the following after extracting the private
archive. A private data directory must contain `reference.wav`,
`source_lsf_co.json`, `source_coeff_trace.csv`, `source_legacy.lpx3`.

```bash
PYTHONPATH=tools:encoder_vbr/tools python3 tools/q1_autotune.py   --data-dir ../Private_AB/references/otvechaesh   --output ../retuned_otvechaesh.l4hy --selection min-size   --min-ser 30 --min-stoi 0.95
```

The program builds the native Q1 library, scans the requested `lambda` values,
invokes the REAL C++ PCM16 decoder and selects only candidates meeting both
thresholds. Expensive search is host-only. Parameter changes do not add
runtime instructions to the AVR decoder.

## AVR object smoke test

```bash
clang++ --target=avr -mmcu=atmega328p -Os -fno-exceptions -fno-rtti -std=c++11 \
  -ffunction-sections -fdata-sections -Itests/avr_stub -Isrc \
  -DLPX4_WIDE_FRAC=1 -DLPX4_FAST_SPLIT_Q1=1 -DLPX4_ENABLE_PCM16=1 \
  -c src/Lpx4HybridCore.cpp -o core_q1.o
```

No complete AVR ELF/HEX was linked in the analysis environment. Values in
`AVR_OBJECT.json` are sums of machine `.text` sections of a relocatable object,
not final linked firmware size or execution cycles. The Arduino profile example
is a measurement harness to run **on an actual 16 MHz ATmega328P**.

## Evaluation definitions

Numerical SNR = 10log10(sum(Q12_reference^2)/sum((Q12_reference - Q1)^2)).
This compares two implementations of the same quantized LPX4 stream.

Signal-to-error ratio (SER) = 10log10(sum(original_pcm16^2)/
                                         sum((original_pcm16 - decoded_pcm16)^2)).
It measures reconstruction accuracy against the original voice, not analog
noise floor. If the term SNR denotes this same reconstruction error, there is
no separate 40 dB threshold: **40 dB reconstruction SNR is not yet reached**.

STOI is computed between the reference PCM16 and output at 8 kHz. Scores on
previously optimized short utterances are NOT out-of-sample validation.

## Memory and speed boundary

Object measurements: base class 554 B SRAM, Q1 604 B (+50 B). The 16 MHz budget
at 8 kHz is 2000 CPU cycles per sample including I/O/interrupts. The object
compiled for ATmega328P, but a cycle-accurate run on hardware or simulator
has NOT been completed; no real-time guarantee is asserted.

## Profiling

`project/examples/LPX4_Q1_PCM16_PROFILE/` is a Timer1 /1 firmware diagnostic
for ATmega328P. It measures `nextS16()` cost without PWM or audio-buffer output,
and therefore does **not** guarantee continuous 8 kHz reproduction. Replace
`voice_data.h` with a `l4hy` stream converted using
`tools/gen_voice_header.py` and run on real hardware.

The reference sample files may be subject to rights restrictions; they are
excluded from this source-only ZIP and bundled only in the separate private
package provided for the user's own analysis.
