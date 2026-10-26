# NB11 and compact WB12.8

The optional `SPEEX_ENABLE_NB4=1` extension supports better-rate voice packets
without changing the 16 MHz / 2 KB SRAM target. Default 0 retains the minimum
NB8/WB9.8 builds. The separate ASM opt-in and real CPU/ABI checks still apply;
every new arithmetic path has a C fallback, selectable on AVR itself.

| Packet | Meaningful bits / 20 ms | Raw bytes | Output |
| --- | ---: | ---: | --- |
| NB3 | 160 | 20 | 160 samples at 8 kHz |
| NB4 | 220 | 28 | 160 samples at 8 kHz |
| NB3 + HB1 | 196 | 25 | 320 samples at 16 kHz |
| NB4 + HB1 | 256 | 32 | 320 samples at 16 kHz |

NB4 alone ignores the final four padding bits. In WB12.8 those bits instead
start HB1; the decoder reads its 36 bits at offset 220. Enabled NB modes may
change per frame within either API. Initialize before each independent stream;
NB and WB share one state and must not be interleaved. The Flash demos accept
uniform packet widths; the library API accepts either enabled width.

The implementation follows the vendored Xiph Speex 1.2.1 mode definitions and
the [NB](https://speex.org/docs/manual/speex-manual/node10.html) /
[WB](https://speex.org/docs/manual/speex-manual/node11.html) bit allocations.
NB4 keeps NB3's 18-bit LBR LSP codebooks, pitch/gain/energy quantization and
fixed-point bounds. Innovation changes from four 10-sample/5-bit vectors to
five 8-sample/7-bit vectors. Thus the existing exact LSP/cache and bounded
pitch primitives remain applicable. The original vendor files stay unchanged.

WB12.8 improves the encoded **low band**; HB1 still uses folding, with no
independent high-band innovation codebook. Final synthesis remains the same
normalized Q7 16-tap QMF approximation documented in [WIDEBAND.md](WIDEBAND.md).
Its PCM matches the independent compact-profile oracle, rather than full
64-tap Xiph synthesis. NB4 PCM matches unmodified Xiph exactly. Rates above
12.8 kbit/s WB and UWB/32 kHz have not been admitted.

## Measured CPU and memory

AVR GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, ATmega328P at 16 MHz,
avr8js 0.21.1. CPU percentages divide decoder-only cycles by 320,000 cycles
per 20-ms frame; they exclude output/ISR work. These are observed corpus
results, not a worst-case execution proof or a physical board measurement.

| Profile, ASM | Mean CPU, natural voice | Max observed CPU, voice | Bare harness Flash | Static SRAM |
| --- | ---: | ---: | ---: | ---: |
| NB8 | 30.65% | 32.36% | 10,598 B | 1,099 B |
| NB11 | 31.29% | 32.84% | 12,940 B | 1,107 B |
| WB9.8 | 74.37% | 76.69% | 17,072 B | 1,279 B |
| WB12.8 | 75.11% | 77.08% | 19,870 B | 1,287 B |

The same 16 Russian/English voice excerpts are used. New modes and WB9.8
include 6,467 frames; historical NB8 uses 6,434 because encoder padding differs.
Natural-row means are frame-weighted from per-stream rounded cycle counts.
These figures include [grouped IIR, phase-specific caches and cosine negation](IIR_GROUPS.md).
The larger adversarial corpus reaches 105,733 cycles/frame for NB11 (33.04%)
and 246,660 for WB12.8 (77.08%). WB12.8 averages 241,085.577 cycles over all
10,563 natural/coverage frames (75.34%). Its bare harness peaks at 192 B stack,
leaving 569 B SRAM; caller buffers and the output ISR require their own space.

C retains exact output: NB11 averages 69.10% CPU on voice; WB12.8 takes
203.07%, so C WB is a portable correctness fallback rather than real-time
playback on this AVR. Other architectures need their own timing test.

## Output timing and quality checks

- Both backends pass 11,587 NB11 and 10,563 WB12.8 frames, with per-stream
  reset replay. Corpus includes 16 natural clips, all short/long pitch and
  LBR gain combinations, zero/nonzero transitions and all 4,096 HB LSP pairs.
- A separate native oracle run checks the final sources, 37 legacy streams,
  and 1,024 mixed-mode frames. Invalid lengths/headers/null arguments are
  injected before every mixed frame; output/history and reset replay remain exact.
- New WB ASM PWM runs 48 independent chunks / 6,467 frames with both timers
  and interrupts active: zero underruns, minimum queue 31, 428 B SRAM free.
  Two 192-frame chunks additionally pass 16,000 extra cycles/frame (5% CPU),
  with minimum queue 16. Both WB modes additionally pass all 6,467 speech
  frames with 25,600 extra foreground cycles/frame (8% CPU), minimum queue
  6/5 for WB9.8/WB12.8 and 450/428 B free SRAM. This is a foreground-load
  experiment, not admission for arbitrary additional ISR work. NB11 passes two complete clips / 808 frames normally
  and with 40% added work: queues 74/36 and 681 B free.
- A 304,192-case AVR test independently checks every 13-bit NB4 subframe
  header and every adjacent index pair at every boundary, random packets,
  padding, all pointer low bytes, guards, input reads and ABI preservation.
- The fused WB8 kernel passes 63,360 cases / 2,534,400 samples per path against
  independent BigInt arithmetic and explicit AVR C. All indices, signed32
  gain extrema, scale boundaries and pointer page crossings are covered.
- Exported C manifest and CMake archives both decode all new/old streams and
  mixed modes through public includes. Forty-five real compiler configurations
  check architecture/feature selection; invalid feature values fail compilation.

The new WB decoder plus an entire eight-second recording does not fit in
32 KB internal Flash. PWM demos therefore use chunks of at most 192 frames,
each with its own reset oracle; the bare decoder tests retain full-recording
history. A separate RAM-input harness reuses the production timer ISR and
queue: both WB modes pass all 17 full streams / 10,563 frames each, without
chunk resets, with exact s16/PWM and 8% foreground work. Observed queues are
at least 6/5 samples and free SRAM 437/429 B for WB9.8/WB12.8 in that harness.
Applications may supply continuous packets externally through the API; the
test assumes ready packets and implements no serial/storage transport.

The initial extension kept four minimum bare decoder images and six
representative PWM images byte-identical. The subsequent paired stage and
exact cosine leaf and grouped IIR stages change ASM images; the latest gate freshly validates 198 PWM images. All four C decoder
images and 62 C player images remain byte-identical. Initial higher-profile
admission is in `reports/higher-admission.json`; current measurements and
source/report/binary hashes are in `reports/group4-admission.json`.

## Reproduce

From `Codecs/Speex/AVR`, with retained real-speech clips/corpora prepared by
the existing speech workflow, Python, Clang, AVR GCC, FFmpeg and Node on PATH:

```sh
python tests/prepare_higher_profiles.py --cc clang --ffmpeg ffmpeg
python tests/verify_higher_native.py --cc clang
python tools/build.py --avr-gcc avr-gcc --backend asm --packet-bytes 28
node tests/verify_avr.mjs --streams build/higher-corpus/nb4/streams --oracle build/higher-corpus/nb4/oracle --verify-reset
python tools/build_wb.py --avr-gcc avr-gcc --backend asm --packet-bytes 32 --out build/wb128
node tests/verify_wb.mjs --firmware build/wb128 --streams build/higher-corpus/wb128/streams --oracle build/higher-corpus/wb128/oracle
python tools/build_high_fold_test.py --avr-gcc avr-gcc
node tests/verify_high_fold.mjs
python tools/build_nb4_fields_test.py --avr-gcc avr-gcc
node tests/verify_nb4_fields.mjs
python tests/prepare_higher_players.py
python tests/verify_wb_players.py --avr-gcc avr-gcc --streams build/higher-player-corpus/streams --oracle build/higher-player-corpus/oracle --out build/wb128-pwm
python tools/build_wb.py --export-c build/wb128-library --enable-nb4
python tests/verify_portable.py --cc clang --ar llvm-ar --wb --enable-nb4 --cmake cmake --ninja ninja
python tests/audit_iir_groups.py --avr-gcc avr-gcc
```

Use `--backend c` for the same AVR correctness tests. New-width AVR builds
enable NB4 automatically; `--enable-nb4` also enables it when building an old
width or exporting C. The exported CMake target remains `speex_nb3` for source
compatibility. No `.S` file is included in the C package.

The bounded C reader loads each seven-byte NB4 window once. The short-pitch
controller shares one source template for both vector geometries. HB1 uses a
fused reconstruction/fold kernel, avoiding intermediate PCM traffic while
retaining both rounding steps. On the two-clip screening workload it saves
3,248 cycles/frame and 16 B stack versus separate passes, at a four-byte Flash
cost. That is a screening comparison; final corpus timing is tabulated above.
