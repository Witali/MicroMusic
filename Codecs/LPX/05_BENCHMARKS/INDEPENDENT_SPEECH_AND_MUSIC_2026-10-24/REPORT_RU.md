# MicroMusic: LPX3/LPX4, Opus и AAC — независимые испытания

2026-10-24. All measurements executed in this working environment, not extrapolated.

## Тестовые материалы

| Sample | Duration | Source / license disclosure |
|---|---:|---|
| English conversation, two voices, 20 s | 20 s | External bundled test sample; source recording license not separately verified. Original not redistributed. |
| Saxophone solo, 16 s | 16 s | External bundled Gradio sample; recording license not separately verified. Original not redistributed. |
| Synthetic polyphony, 12 s | 12 s | Locally generated original using included deterministic Python script. |

The environment has no outbound DNS access; the previously selected Wikimedia/SoniqTools audio could not be downloaded. The independent English dialogue and sax samples were already installed in third-party audio packages; their raw or compressed content is deliberately omitted from the redistributable bundle. The synthetic musical stimulus is included.

## Сравнение кодеков: фиксированные режимы

All files compare against **the exact same 8 kHz mono signed PCM16 reference** per sample. SER = 10 log10(sum(ref^2)/sum((ref-decoded)^2)); align only integer lag ±160ms; no optimizing signal gain. STOI is standard at 8kHz and used only for English speech.

| Sample | Codec | Mode | File B | Effective kb/s | SER dB | STOI |
|---|---|---|---:|---:|---:|---:|
| english_dialogue_20s | LPX3 original | 2-bit | 44633 | 17.85 | 11.03 | 0.90764 |
| english_dialogue_20s | LPX3 original | 3-bit | 64633 | 25.85 | 18.56 | 0.96433 |
| english_dialogue_20s | LPX3 original | 4-bit | 84633 | 33.85 | 23.91 | 0.98578 |
| english_dialogue_20s | LPX4 Q0 transcode | from LPX3 2-bit | 45833 | 18.33 | 10.98 | 0.90697 |
| english_dialogue_20s | LPX4 Q0 transcode | from LPX3 3-bit | 58683 | 23.47 | 14.82 | 0.96369 |
| english_dialogue_20s | Opus | target 16 kbps | 39992 | 16.00 | 19.66 | 0.9852 |
| english_dialogue_20s | Opus | target 24 kbps | 66957 | 26.78 | 24.16 | 0.9956 |
| english_dialogue_20s | Opus | target 32 kbps | 89347 | 35.74 | 29.77 | 0.99862 |
| english_dialogue_20s | AAC-LC | target 16 kbps | 41855 | 16.74 | 15.37 | 0.96405 |
| english_dialogue_20s | AAC-LC | target 24 kbps | 66632 | 26.65 | 19.95 | 0.98895 |
| english_dialogue_20s | AAC-LC | target 32 kbps | 85116 | 34.05 | 28.24 | 0.99739 |
| saxophone_16s | LPX3 original | 2-bit | 35857 | 17.93 | 17.09 | — |
| saxophone_16s | LPX3 original | 3-bit | 51857 | 25.93 | 25.35 | — |
| saxophone_16s | LPX3 original | 4-bit | 67857 | 33.93 | 31.52 | — |
| saxophone_16s | LPX4 Q0 transcode | from LPX3 2-bit | 35848 | 17.92 | 13.79 | — |
| saxophone_16s | LPX4 Q0 transcode | from LPX3 3-bit | 46258 | 23.13 | 15.53 | — |
| saxophone_16s | Opus | target 16 kbps | 32790 | 16.39 | 21.36 | — |
| saxophone_16s | Opus | target 24 kbps | 51025 | 25.51 | 28.91 | — |
| saxophone_16s | Opus | target 32 kbps | 67059 | 33.53 | 33.75 | — |
| saxophone_16s | AAC-LC | target 16 kbps | 33784 | 16.89 | 23.43 | — |
| saxophone_16s | AAC-LC | target 24 kbps | 50409 | 25.20 | 30.75 | — |
| saxophone_16s | AAC-LC | target 32 kbps | 70097 | 35.05 | 33.58 | — |
| synthetic_music_12s | LPX3 original | 2-bit | 26156 | 17.44 | 6.40 | — |
| synthetic_music_12s | LPX3 original | 3-bit | 38156 | 25.44 | 15.20 | — |
| synthetic_music_12s | LPX3 original | 4-bit | 50156 | 33.44 | 21.77 | — |
| synthetic_music_12s | LPX4 Q0 transcode | from LPX3 3-bit | 28057 | 18.70 | 13.04 | — |
| synthetic_music_12s | Opus | target 16 kbps | 23919 | 15.95 | 23.82 | — |
| synthetic_music_12s | Opus | target 24 kbps | 42145 | 28.10 | 23.77 | — |
| synthetic_music_12s | Opus | target 32 kbps | 54426 | 36.28 | 27.65 | — |
| synthetic_music_12s | AAC-LC | target 16 kbps | 25596 | 17.06 | 23.70 | — |
| synthetic_music_12s | AAC-LC | target 24 kbps | 37451 | 24.97 | 27.33 | — |
| synthetic_music_12s | AAC-LC | target 32 kbps | 47414 | 31.61 | 34.93 | — |

## Сравнение при близком фактическом размере файлов

These comparisons target the actual byte size of an LPX3/LPX4 stream, including AAC/Opus container. Codec target bitrate was tuned; it is not an exact 1:1 byte match.

| Sample | Reference | Target B | Codec | Actual B | Delta % | SER dB | STOI |
|---|---|---:|---|---:|---:|---:|---:|
| english_dialogue_20s | LPX3 | 64633 | Opus | 64158 | -0.73% | 23.37 | 0.99461 |
| english_dialogue_20s | LPX3 | 64633 | AAC-LC | 63514 | -1.73% | 19.68 | 0.98833 |
| english_dialogue_20s | LPX4 | 58683 | Opus | 58569 | -0.19% | 21.75 | 0.99313 |
| english_dialogue_20s | LPX4 | 58683 | AAC-LC | 60034 | +2.30% | 19.32 | 0.98602 |
| saxophone_16s | LPX3 | 51857 | Opus | 51025 | -1.60% | 28.91 | — |
| saxophone_16s | LPX3 | 51857 | AAC-LC | 52234 | +0.73% | 31.21 | — |
| saxophone_16s | LPX4 | 46258 | Opus | 47033 | +1.68% | 27.36 | — |
| saxophone_16s | LPX4 | 46258 | AAC-LC | 45273 | -2.13% | 25.05 | — |
| synthetic_music_12s | LPX3 | 38156 | Opus | 37530 | -1.64% | 21.59 | — |
| synthetic_music_12s | LPX3 | 38156 | AAC-LC | 37451 | -1.85% | 27.33 | — |
| synthetic_music_12s | LPX4 | 28057 | Opus | 24845 | -11.45% | 24.43 | — |
| synthetic_music_12s | LPX4 | 28057 | AAC-LC | 28739 | +2.43% | 20.33 | — |

## Как получены LPX-потоки

* LPX3: Universal encoder from preserved `train_encode.py --fast --no-trim` (LPC2 analysis + 2/3/4-bit closed-loop excitation); no pretrained per-speaker phrases used. This is **original LPX3**, not late AVR Rice v7.
* LPX4: The corresponding original LPX3 streams were converted to L3AV (10-bit LSF), then `lpx4.encode(... fast=True, min_snr=inf)` packaged a **lossless exact-excitation pitch/Rice** format; waveform decoded by `Lpx4HybridCore::nextS16`. No extra rate-distortion search/LSF re-training of the Q0 encoder on these new stimuli was executed. Consequently these figures are a baseline for generalization, not a bound on LPX4 quality.
* LPX4 input 4-bit mode was not benchmarked: long streams exceed the 16-bit stream-size field accepted by the current C++/AVR decoder. LPX3 4-bit mode is included using its independent desktop decoder.
* These long LPC streams cannot fit, with decoder firmware, in the ATmega328P 32KB on-chip Flash. External audio storage or segmented streaming is necessary. Neither hardware decoding cycles at 16 MHz nor underruns have been checked.
* AAC-LC and Opus are FFmpeg encodings at specified target bitrate; measured file byte sizes include container overhead. Opus -application audio -vbr on -compression_level 10.

## Выводы

* At roughly 24-26 effective kb/s, Opus and AAC usually have higher waveform SER and (on dialogue) STOI than LPX3/LPX4 baseline. LPX4 often shrinks LPX3 data but quantized/integer LPC synthesis can notably increase waveform error on previously unseen speech/music.
* One 12s synthetic-music sample does not substitute for a diverse acoustic music corpus. Copyright/source licensing needs checking before redistributing the bundled third-party recordings.
* To assess final LPX4 Q0 fairly, finish universal WAV-to-Q0 LPC/LSF analysis and per-block excitation optimization without overfitting to the training phrases.

## Воспроизведение

FFmpeg: `ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers`
Python: `3.13.5`

1. Use `run_ffmpeg_bench.py` on 8k reference WAVs to reproduce AAC/Opus. `match_size_benchmark.py` selects target kbps for byte-matched comparisons.
2. Obtain the archived LPX3 original encoder `train_encode.py`, its LPC2 HTML and Chromium; command: `python train_encode.py --fast --no-trim --input input.wav --name name --out result_dir`.
3. Use archived `encoder_vbr/tools/pack_lpx3_avr.py input_3bit.lpx3 output.l3av --coeff-bits 10 --representation lsf`, then convert via `tools/lpx4.py` and decode with `src/Lpx4HybridCore.cpp` + `tests/decode_s16_host.cpp`.
4. `finalize_benchmark.py` constructs `all_codecs.json` from source artifacts. Two sample inputs can be found in local `pyannote.audio` and `gradio` installs in this testing environment, but the recording licenses were not verified and those audio files are not copied here.

## Открытые источники для отдельной загрузки

- [Russian sayings, ~24s, PD-self](https://commons.wikimedia.org/wiki/File:Russian_sayings.ogg)
- [English LibriSpeech, CC BY 4.0](https://us.openslr.org/12/)
- [Bach Open Goldberg piano 30s, CC0](https://soniqtools.com/test-audio-files)
- [Russian Mozilla Common Voice, CC0 but dataset re-hosting is restricted](https://mozilladatacollective.com/datasets/cmu5x45pn00dao107j4o9w2yv)

Автономный загрузчик `download_open_corpus.py` получает три речевых примера с Wikimedia Commons и 30-секундное фортепиано CC0 (если доступен HTTPS), сохраняет SHA-256 и конвертирует в WAV 8кГц. В текущей среде эти загрузки не выполнены из-за отсутствия внешнего DNS.
