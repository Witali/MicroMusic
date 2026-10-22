# MicroMusic MiniLPC-HQ2 — 1 KB ATtiny13A speech experiments

MiniLPC-HQ2 is an experimental **single-format-only**, eight-stage LPC speech
synthesizer for the ATtiny13A. The aim was to approach **0.90 STOI** on three
user-provided Russian dialogue clips while keeping *all* executable code and
encoded voice under **1024 bytes of Flash per phrase**. The 0.90 goal was **not
reached**. The best fully assembled and cycle-emulated results are below.

## Verified results (October 21, 2026)

| Phrase | Original MiniLPC-HQ | **HQ2 STOI** | Executable decoder | Voice data | Full Flash |
|---|---:|---:|---:|---:|---:|
| «Чего тебе нужно?» | 0.8522 | **0.8809** | 412 B | 570 B | **983 B** |
| «Что ж ты не отвечаешь?» | 0.7756 | **0.8104** | 412 B | 500 B | **913 B** |
| «Сова! Открывай! Медведь пришёл!» | 0.8236 | **0.8533** | 412 B | 610 B | **1023 B** |

Flash includes code, the compressed voice and one end/loop marker byte. The
ATtiny13A has 1024 bytes Flash, 64 bytes SRAM and 64 bytes EEPROM. **EEPROM is
not used** in HQ2. PWM is output through PB1/OC0B at **37,500 Hz**; speech
samples are **7,500 Hz** with the CPU at **9.6 MHz**. The AVR firmware has no
legacy-format branches, no hardware multiply, and no floating point.

All scores are `pystoi.stoi(original_wav, avr_decoded_wav, fs_sig=7500,
extended=False)` with the preprepared canonical originals in
`references/<phrase>/original.wav`. These are **in-sample tests** against the
same recordings used for optimization. STOI measures intelligibility, **not**
voice identity or subjective audio quality. No result above should be
interpreted as a general speech-codec benchmark.

## Verification

Each **HEX was assembled, then executed** by `avr_emulator.js` instruction by
instruction. The resulting PCM matched the bit-exact NumPy/Numba decoder:

- «Чего тебе нужно?» — 9,216 matching audio samples
- «Что ж ты не отвечаешь?» — 7,936 matching audio samples
- «Сова! Открывай!» — 22,272 matching audio samples
- Across all three: **0 PCM mismatches**, **0 missed Timer0 overflows**, **0 late audio samples**, maximum ISR duration **28 CPU cycles**.

The ATtiny13A board itself **has not been tested**. PWM output quality will
also depend on RC filtering, the oscillator, supply voltage and amplifier.

## What was improved

The decoder and bitstream format remain compatible **only with HQ2's native
MiniLPC-HQ format**, not with earlier TinyLPC/LPC2/LPX3 streams. HQ2 trains
only the data, preserving the proven **412-byte 8-stage LPC engine**.

* Three frame durations: 64 / 128 / 256 PCM samples (8.53 / 17.07 / 34.13 ms).
* 6-, 4- or 2-byte VBR frames, chosen by which LPC coefficients need updating.
* Joint closed-loop optimization of pitch, gain, 8 quantized reflection
  coefficients and the two-bit pulse profile, including coupled changes across
  adjacent frames.
* Iterative analysis-by-synthesis with a strict Flash ceiling and a zero-new-
  click threshold (absolute consecutive-PCM change >= 48) on these examples.
* Explored multiple alternate voiced impulses and maximal-length LFSRs; those
  variants did **not** beat the established excitation in this round and were
  **not** added to firmware. Search scripts and reports are retained.

## Repeat the conversion, encoding, build and verification

Install Python 3.11+, ffmpeg, NumPy, SciPy, Numba, soundfile, pystoi, LLVM AVR
compiler tools and Node.js. The original MP3 files and canonical evaluation
WAVs are included **only in the private archive**.

```bash
python -m pip install -r requirements.txt

# Decode an MP3 to fixed-rate mono WAV; writes WAV + JSON preparation report.
python convert_audio.py --input inputs/xtuj-ntt.mp3 \
  --output prepared/chego.wav --start-samples 275 --samples 9216 --peak 0.90

# Reassemble precisely the *saved* trained.npz bitstreams, run a cycle-accurate
# AVR simulation, recompute STOI and emit WAV, HEX, report.csv/json, index.html.
python run_all.py

# Optional extra fitting against references/<phrase>/original.wav.
# This changes the saved models and may find different optima.
python refine_hq.py --voice chego --seconds 60 --passes 6
python joint_opt.py --voice chego --seconds 80 --seed 1377
python train_hq.py --voice chego --seconds 60 --attempts 100
python run_all.py
```

**Important:** `references/*/original.wav` are the canonical, historically
prepared originals used for the numbers above. The new `convert_audio.py`
provides a reproducible, documented MP3 preprocessing pipeline, but is not a
claim that the previous (partly separately normalized) reference WAVs can be
regenerated *bit-for-bit* from MP3. Keep the frozen canonical WAVs when
comparing STOI numbers across versions.

The encoder uses phrase-specific starting frames in `samples/*/trained.npz`,
plus frozen baselines under `baselines`. For a completely new phrase a new
initial phoneme/pitch/LPC analysis and a new frame-duration schedule are
required; this is a proof-of-concept, not a universal high-quality MP3-to-AVR
codec with guaranteed 0.9 STOI.

## Output files

- `index.html`: standalone A/B listener with original, earlier VBR, LPX3 and
  HQ2 AVR audio; runs locally after download.
- `samples/<phrase>/firmware.S`, `.bin`, `.hex`: compiled firmware.
- `samples/<phrase>/speech.hq`: packed speech data.
- `samples/<phrase>/avr_preview.wav`: audio actually produced by the AVR emulator.
- `report.json` / `report.csv`: measurements, sizes, SHA256.
- `convert_audio.py`: editable standalone source-to-WAV preparation script.
- `train_hq.py`, `refine_hq.py`, `joint_opt.py`: offline optimizer stages.
- `pulse_lab.py`, `noise_lab.py`: archived experiments and findings.
- `run_all.py`: reproducible assembler/validator/evaluator/page generator.

## Distribution

The **private archive** includes the user-provided copyrighted cartoon audio
and transformed derivatives exclusively for private evaluation. The **public
source-only archive** contains no copyrighted voice recordings, fitted voice
parameters or derived encoded streams. Use its synthetic example to test
compilation and emulation.
