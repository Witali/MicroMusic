# Speex for AVR

An adaptation of the **original Xiph Speex 1.2.1 fixed-point decoder** for
ATmega328P at 16 MHz, with a linked PWM player and reproducible host/AVR tests.
The complete player passes ISA simulation on all 31 streams: **9,100
frames / 1,456,000 samples, zero underruns, 314 bytes SRAM free at the observed
peak**. A physical board and its analog output have not been tested.

## Supported profile

- Narrowband submode 3, mono 8 kHz, CBR 8 kbit/s.
- Exactly 20 compressed bytes produce 160 signed 16-bit samples (20 ms).
- Enhancement and highpass are disabled; all four LSP interpolations and LPC
  conversions are retained. Decoded s16 PCM matches unmodified upstream.
- Input consists of raw packets, as in `reference/R4/data/*.spxraw`. Ogg/Speex
  containers, other submodes, WB, DTX, stereo, encoder and packet loss concealment
  are outside this profile. The API rejects wrong lengths and mode headers
  before changing state.

`src/speex_avr.h` exposes a static, non-reentrant decoder: reset with
`speex_avr_init()`, then call `speex_avr_decode(packet, 20, pcm)` for each packet.
The caller supplies space for 160 samples. No heap is used. The 240-byte scratch
arena is checked on the host; the 312-sample excitation history is sufficient
for the restricted lossless profile (maximum backward pitch access: 145 samples).

## PWM player

`src/player.c` reads embedded packets from Flash and sends the high eight bits
of PCM, converted to unsigned samples, to **OC1A / PB1 / Arduino D9**.
Timer1 runs 8-bit fast PWM at 62.5 kHz; Timer2 CTC advances PCM at 8 kHz.
Timer divisors assume a 16 MHz CPU clock. A 128-byte ring receives each completed
40-sample subframe, so decoding and playback overlap without a second s16 frame.
Playback starts after an 80-sample prefill and drains the final sample before
returning PWM to midpoint.

The demo stops at the end of the embedded stream. The supplied `speech_ru`
fixture is historical synthesized test speech from the handoff, not a recording
of a human speaker. The 8-bit PWM conversion is separate from the exact s16
decoder comparison.

## Build and verify

Use Python 3, Clang, AVR GCC/avr-libc and Node on PATH. On this Windows checkout,
the shared tools can be enabled from the task worktree with
`. ../../build/toolchains/env.ps1` in PowerShell. Clang's native Windows build
also needs the installed Microsoft C runtime/SDK and linker.

From the task worktree root:

```sh
python Codecs/Speex/AVR/tests/verify_pcm.py --cc clang
npm --prefix Codecs/Speex/AVR ci --ignore-scripts
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_avr.mjs
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --player Codecs/Speex/AVR/reference/R4/data/speech_ru.spxraw
node Codecs/Speex/AVR/tests/verify_player.mjs
```

For the full player matrix (rebuilds and simulates every stream):

```sh
python Codecs/Speex/AVR/tests/verify_players.py --avr-gcc avr-gcc --node node
```

Outputs are ignored under `build/`. The decoder validation firmware is
`build/profile/speex-test.{elf,hex,bin,map}`. The PWM demo is
`build/player/speex-player.{elf,hex,bin,map}`; `input.json` records its payload
hash. The matrix leaves `speech_ru` as the final demo. Player tests retain the
captured unsigned PCM as `build/player/player-pwm.u8`.

## Verified results

AVR GCC 7.3.0, `-O3 -flto -fwrapv -fno-strict-aliasing`, ATmega328P, AVR8js
0.21.1. Static SRAM includes the packet, s16 PCM, decoder state, scratch and,
for the player, PWM ring. Stack peaks are observed during actual ISR execution.

| Build | Flash | Static SRAM | Peak stack | Free SRAM at peak |
| --- | ---: | ---: | ---: | ---: |
| Optimized decoder test mailbox | 14,856 B | 1,375 B | 216 B | 457 B |
| Full PWM speech demo, including 2,940 B compressed audio | 18,014 B | 1,508 B | 226 B | 314 B |

- All 9,100 AVR-decoded frames match unmodified upstream s16 PCM.
- Complete player tests on all 31 streams match upstream PCM converted to u8,
  with zero ring underruns and no stack/static-memory collisions.
- Maximum observed decoder-only frame cost: **204,770 cycles / 12.80 ms**;
  the 20-ms budget at 16 MHz is 320,000 cycles. ISR and output costs are verified
  separately by the complete-player runs.
- Primitive tests cover 240,000 complete LSP conversions and 3,670,016 bit fields;
  stream tests insert invalid API calls and verify unchanged output/state.
- Another 458,752 signed multiply and 393,291 signed shift cases execute the
  actual AVR instructions and check exact results and the r1 zero-register ABI.
- Codebooks reside in Flash, use explicit signed `pgm_read_*` accesses, and no
  malloc/calloc/realloc/free symbols are linked.

See `reports/nb-lpc-postincrement.json`, `reports/nb-final-speech.json`,
`reports/nb-final-player.json` and `reports/nb-optimization-summary.json`.
These are corpus maxima and ISA simulation results,
not exhaustive packet timing proofs or physical board measurements.
`reports/avr-initial.json` preserves the initial 547,940-cycle port for comparison.
`reports/avr-optimized.json`, `reports/player-all.json` and the original
`reports/real-speech-{avr,player}.json` retain the earlier NB baseline.

## Further exact NB optimization

The current Xiph NB3 adaptation includes four separately measured changes:

| Step | Maximum decoder cycles on the 1,058-frame fixture corpus | Decoder Flash | Static SRAM |
| --- | ---: | ---: | ---: |
| Previous exact NB baseline | 295,334 | 14,712 B | 1,535 B |
| Fuse innovation and final excitation; remove intermediate | 289,878 | 14,620 B | 1,375 B |
| Return inline ASM products in a single 32-bit operand | 279,557 | 13,422 B | 1,375 B |
| Replace constant fixed-point shift loops with byte-aware ASM | 207,602 | 14,874 B | 1,375 B |
| Use postincrement stores in the LPC state update | 204,722 | 14,856 B | 1,375 B |

Across the combined 31-stream corpus the maximum improves from 295,386 to
204,770 cycles: **30.677% less decoder time**, with all PCM and captured PWM
hashes unchanged. Decoder timings exclude ISR; complete player tests include
Timer1, Timer2, interrupt delivery and ring-buffer backpressure. The PCM rate,
20-ms frame, all four LSP interpolations/conversions, rounding and saturation
remain unchanged. The optimization does not change the narrowband bandwidth.

Full LSP-stage unrolling was also tested on 88 frames: it was exact but grew
decoder Flash to 24,636 bytes. A peeled-loop alternative used 16,428 bytes and
a larger stack. Neither was retained; the selected arithmetic changes provide
a larger gain with a much smaller Flash cost.

To reproduce the standalone arithmetic tests:

```sh
python Codecs/Speex/AVR/tools/build_math_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_math.mjs
```

Stage reports are `reports/nb-{fused-excitation,multiply,byte-shifts,lpc-postincrement}.json`.
The reusable recipes and exact ASM sources are linked from
[`docs/avr-asm-cookbook`](../../../docs/avr-asm-cookbook/README.md).

## Human speech and PWM headroom

The expanded corpus contains 20 eight-second clips: eight human speakers
(four Russian, four English; two male and two female voices per language),
16 natural excerpts plus two attenuated by 24 dB and two with seeded white
noise at 15 dB SNR. Source pages, speaker/author credits, licenses, changes and
SHA-256 hashes are retained in `tests/real-speech-sources.json` and
`reports/real-speech-corpus.json`. Audio stays in ignored build output.

All **8,042 frames / 1,286,720 samples** match unmodified upstream s16 PCM on
the AVR ISA simulator. Every full player run, with both timers and interrupts,
also matches the expected PWM duties, with **zero underruns**. Worst observed
decoder frame is 204,770 cycles (12.798 ms). Current ring headroom and maximum
publication gaps are recorded in `reports/nb-optimization-summary.json`.
The final combined corpus retains at least **65 queued samples / 8.125 ms**
before output while decoding is active; maximum block publication gap is
114,206 cycles / 7.138 ms. The earlier human-speech run retained 31 samples.
Timer output intervals are 1,994–2,004 cycles. Full-player SRAM/stack are
1,508/226 bytes, leaving 314 bytes. These bounds describe this corpus and simulated ISA/peripherals;
hardware playback and other interrupt workloads still need measurement.

The aligned natural-speech STOI mean is 0.9016 for decoded s16 and 0.8373 for
the 8-bit PWM duties. At -24 dB it is 0.8976 / 0.5190: quiet input exposes
the separate 8-bit quantization limit. These are intelligibility estimates,
not MOS, percentages of correctly recognized words or a subjective listening
test. No gain normalization is applied. Delay is measured and removed only
for comparison; the complete AVR timing tests include all decoded samples.

To reproduce (FFmpeg with libspeex is required):

```sh
python Codecs/Speex/AVR/tools/prepare_real_speech.py
python Codecs/Speex/AVR/tests/verify_players.py --avr-gcc avr-gcc --node node --streams Codecs/Speex/AVR/build/real-speech/streams --out Codecs/Speex/AVR/build/real-speech/player
```

Decode each raw stream with `build/reference/decode` into
`build/real-speech/oracle/<stem>.pcm`, build the decoder test firmware, then:

```sh
node Codecs/Speex/AVR/tests/verify_avr.mjs --streams Codecs/Speex/AVR/build/real-speech/streams --oracle Codecs/Speex/AVR/build/real-speech/oracle --out Codecs/Speex/AVR/build/real-speech/avr --capture
python -m pip install -r Codecs/Speex/AVR/tests/requirements-quality.txt
python Codecs/Speex/AVR/tools/analyze_real_speech.py
```

`build/real-speech/index.html` provides original excerpts, 8-kHz encoder input,
AVR-decoded s16 and captured PWM side by side. WAVs represent the simulated
digital signal, without the board's analog output filter/noise. Full measurements
are in `reports/real-speech-{avr,player,quality}.json`.

## Native 16/32-kHz memory experiment

The ATmega328P player currently supports **8 kHz only**. Native Speex WB
(16 kHz) and UWB (32 kHz) are experimental PC builds; no 22.05-kHz output
profile is introduced. The separate experiment retains native high-band
information rather than resampling the narrowband result.

`tools/build_rates.py --memory` applies three changes to a disposable upstream
copy, without changing the working NB3 player:

- QMF history uses dense 32-sample rings instead of 64 slots with only odd
  slots used: **128 bytes saved per high-band layer**.
- An in-place perfect shuffle precedes causal QMF synthesis, eliminating
  the two temporary arrays: **768 bytes at 16 kHz / 1,408 bytes at 32 kHz**.
  Signed 17-bit low/high sums retain carries and exact modulo-32 arithmetic.
- The high-band excitation scratch array is allocated once per frame and
  reused across four subframes: **480 / 960 bytes of scratch growth avoided**.
  Symmetric bounded LSP half-polynomials support LPC orders 8 and 10 using
  48 bytes of local arrays, replacing upstream scratch matrices.

These savings describe individual components; they are not a measured total
SRAM footprint of a complete AVR WB/UWB player. The PC experiment still uses
upstream allocation/API and its default scratch arena. It is not linked into
the 2-KB production decoder.

All 32 native-rate natural-speech streams match untouched upstream fixed-point
PCM, including both QMF layers in UWB. Another 480,000 complete upstream LSP
comparisons exercise both orders. A separate AVR GCC machine-code benchmark
matches the original QMF on full-scale DC, opposing extrema, silence and
random frames with persistent history. Its measured costs are:

| Isolated QMF layer | Maximum cycles | Time at 16 MHz | Frame budget |
| --- | ---: | ---: | ---: |
| 8→16 kHz | 1,452,772 | 90.798 ms | 20 ms |
| 16→32 kHz | 2,909,131 | 181.821 ms | 20 ms |

This is a memory-focused implementation and not a speed limit for all possible
implementations. It currently fails the real-time requirement even before
adding CELP decoding, packet transport, output and interrupts. UWB also needs
the inner WB synthesis layer. A larger buffer cannot compensate for a sustained
production rate below consumption. Enabling either mode in the PWM player
would therefore be incorrect. Further arithmetic/assembly work or a measured
quality/speed tradeoff is required before either can become a supported profile.

Reproduce after preparing real speech:

```sh
python Codecs/Speex/AVR/tools/build_rates.py --cc clang
python Codecs/Speex/AVR/tools/build_rates.py --cc clang --memory
python Codecs/Speex/AVR/tests/verify_rates.py
python Codecs/Speex/AVR/tools/build_qmf_bench.py --cc clang --avr-gcc avr-gcc
node Codecs/Speex/AVR/tests/verify_qmf.mjs
python Codecs/Speex/AVR/tools/analyze_real_speech.py --rates
python Codecs/Speex/AVR/tools/package_comparison.py
```

The gallery and `build/real-speech/speex-listening.zip` include original,
decoded/PWM 8-kHz recordings and **PC-reference** native 16/32-kHz examples,
with source credits. See `reports/wideband-pcm.json`,
`reports/wideband-qmf-avr.json` and `reports/native-rates-quality.json`.

## Sources and provenance

`vendor/speex-1.2.1` contains unmodified release source/header files, their BSD
license, and `UPSTREAM.json` hashes. The official release tarball SHA-256 is
`4b44d4f2b38a370a2d98a78329fefc56a0cf93d1c1be70029217baae6628feea`.
Builds patch disposable copies; every build verifies vendor and handoff hashes.

`handoff/upstream` contains the previous agent's unmodified patch candidates
and tests. `reference/R4` retains the earlier custom decoder and input streams
byte for byte. It is a regression reference, distinct from this upstream port.
`handoff/import-manifest.json` records the supplied archive and imported files.
Historical notes describe their original state; the remaining historical stages
and generated files stay in the external ZIP.

The active adaptation uses exact symmetric 48-byte LSP polynomials, fused
innovation scaling, a bounded field reader and AVR assembly for pitch MACs and
LPC state updates. The latter starts from the retained R4 assembly, with its loop
unrolled in the active copy. The reference source and vendor files remain intact.
