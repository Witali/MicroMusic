# Compact wideband on ATmega328P

`WB1-Q7-16` decodes mono **16 kHz / 9.8 kbit/s** Speex on ATmega328P at
16 MHz. A frame contains NB submode 3 and HB submode 1: 196 meaningful bits,
stored in 25 bytes, producing 320 signed16 samples in 20 ms. The high band
uses the original Speex folding excitation, LSP codebooks and order-eight LPC.
See the [Xiph wideband description](https://speex.org/docs/manual/speex-manual/node11.html).

The final synthesis filter is deliberately approximate: the center 16 taps
of Xiph's 64-tap QMF are normalized to unity DC and quantized to Q7. Half-sum
and half-difference histories allow signed24 accumulation with two hardware
multiplications per tap. This retains high-band data, but reduces rejection
around the band boundary and changes PCM relative to the full Xiph filter.
The ordinary NB3 profile remains bit-identical to Xiph.

Only this fixed NB3+HB1 packet combination is supported. Other WB bitrates,
DTX, enhancement, highpass, packet loss concealment, stereo and UWB/32 kHz
remain outside this AVR profile. Ogg headers/framing must be removed before
decoding; four padding bits at the end of a packet are ignored.

## Streaming interface

```c
#include "speex_wb1.h"

static void output(const int16_t *pcm, uint8_t count, void *context)
{
    /* Copy count samples to the platform's output queue/DMA buffer.
     * pcm remains valid only during this synchronous callback. */
}

void start_stream(void) { speex_wb1_init(); }
int decode_packet(const uint8_t packet[25])
{
    return speex_wb1_decode(packet, 25, output, 0);
}
```

Each successful call invokes the sink four times, with 80 samples each.
There is no heap or full 640-byte PCM frame. NB uses a 40-sample output area;
HB innovation is regenerated from the packet's NB indices instead of saving
160 samples. The high-band PCM lives in the upper half of the 80-sample QMF
output buffer, which is safely overwritten as samples are consumed. The QMF
history is 64 bytes; the HB IIR state is 48 bytes. Both original 40-sample
synthesis delays and all four LSP interpolation steps are retained.

The singleton shares state with the NB API. Initialize each independent
stream and do not interleave NB/WB calls or reenter from the output callback.
Return `-1` rejects parameters, length or mode before changing state; `-2`
rejects unusable synthesis parameters and requires a reset before continuing.

## Build and portability

Run from the worktree root with Python, Clang, AVR GCC and Node on PATH:

```sh
python Codecs/Speex/AVR/tools/build_wb.py --cc clang --reference
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --out Codecs/Speex/AVR/build/wb-speed-asm-decoder
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend c --out Codecs/Speex/AVR/build/wb-speed-c-decoder
python Codecs/Speex/AVR/tools/build_wb.py --export-c Codecs/Speex/AVR/build/wb-library
```

`SPEEX_ENABLE_WB1=1` enables the streaming integration. Arithmetic uses the
existing architecture/manufacturer header contract in `speex_platform.h`.
ASM requires a real supported AVR ABI, matching `SPEEX_NB3_ARCH`, and explicit
`SPEEX_NB3_ENABLE_ASM=1`. Default, unknown architectures and explicit disable
all select C. Harvard Flash access remains independent of arithmetic choice.
Every new ASM kernel has an equivalent C implementation, selectable on AVR.

The C implementation is portable but **does not meet the 20-ms WB deadline
on ATmega328P**. Use ASM for this MCU's WB playback. Other MCU timing requires
its own admission test. The exported C11 manifest and CMake static library
include both public APIs; the compatible CMake target remains `speex_nb3`.

The optimized AVR ASM decoder uses 17,622 B Flash and 1,299 B static SRAM in
the mailbox harness. On the same 10,563 frames, compared with the first WB
implementation:

| Decoder-only measurement | Before | After |
| --- | ---: | ---: |
| Mean cycles/frame | 279,128 | 269,804 |
| Maximum observed cycles/frame | 285,596 | 277,665 |
| Maximum observed time at 16 MHz | 17.850 ms | 17.354 ms |
| Peak stack | 401 B | 255 B |
| Free SRAM at peak | 349 B | 494 B |
| Flash | 17,504 B | 17,622 B |

This saves 3.34% mean and 2.78% maximum observed decoding cycles without
changing compact-profile PCM. Decoder-only timing excludes output/interrupts
and does not establish continuous playback.

The QMF computes two input pairs together, sharing seven history records among
four accumulators. Its oldest required record is captured before insertion
overwrites it; both high-band inputs are consumed before output writes.
Validated fixed HB1 fields are read directly from byte windows. HB angles
are multiples of 16, allowing exact quarter-step interpolation with shifts
and additions. Repeated angles reuse the last LPC, including three subframes
of a fresh stream after computing the first LPC. IIR synthesis and its
coefficient-age transition still execute on every subframe. The interpolation
helper is outlined to keep code size and stack low. C fallbacks and the
architecture/explicit-ASM selection remain available.

The decoder state structures/arena total 1,268 B on AVR (716 B NB state, 60 B scratch,
492 B WB state). The full PWM player uses 1,429 B static SRAM and reaches
264 B stack, leaving **355 B free**. A Russian 404-frame demo uses 28,008 B
Flash, including 10,100 B of compressed audio.

## Reproduce validation

First prepare the retained human speech with `tools/prepare_real_speech.py`,
then the 16-kHz recordings with `tests/verify_rates.py`. Build the native WB
decoder/reference above, then run:

```sh
python Codecs/Speex/AVR/tests/prepare_wb.py
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend asm --firmware Codecs/Speex/AVR/build/wb-speed-asm-decoder
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend c --firmware Codecs/Speex/AVR/build/wb-speed-c-decoder
python Codecs/Speex/AVR/tests/verify_wb_repeats.py
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --kernels --out Codecs/Speex/AVR/build/wb-kernels
node Codecs/Speex/AVR/tests/verify_wb_kernels.mjs
python Codecs/Speex/AVR/tests/verify_portable.py --wb --cc clang --ar llvm-ar --cmake cmake --ninja ninja
```

The independent reference retains untouched Xiph NB/HB decoding and substitutes
only its final QMF with a separate full-frame equation using raw low/high
histories. It does not use the production streaming decoder or its mirrored
half-sum state. Exact PCM means exact to this **compact profile**, not to the
original 64-tap QMF. The corpus covers 16 Russian/English recordings (6,467
frames) and every high-band LSP codebook pair (4,096 additional frames).
The cache regression adds 12,288 native frames with all 4,096 codebook pairs
repeated three times while NB data and gains change. A selected 744-frame
corpus also passes both backends on AVR ISA; run `verify_wb.mjs` with
`--streams Codecs/Speex/AVR/build/wb-speed-repeats/streams` and
`--oracle Codecs/Speex/AVR/build/wb-speed-repeats/oracle` after preparing it.

Kernel tests exercise full-scale/random QMF histories, in-place high-band
aliasing, all signed16 folding inputs with varied gains, independent original
Xiph rounding, arbitrary IIR coefficient transitions, guards and actual ASM
RET preservation of callee-saved registers/r1. New ASM and C use the same
equations. NB-only builds retain their previous binary bytes.

The complete 16-kHz PWM player is `src/wb_player.c`, using OC1A/PB1/D9 at
62.5 kHz carrier, Timer2 CTC (`OCR2A=124`, prescaler 8), a 128-byte output
ring and 80-sample callbacks. Build a demo or run all retained speech:

```sh
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --stream Codecs/Speex/AVR/build/wb-corpus/streams/ru_pushkin_a.spxraw --out Codecs/Speex/AVR/build/wb-demo
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/wb-speed-pwm
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/wb-speed-pwm-load5 --filter "^(ru_pushkin_a|en_letter_a)$" --frame-load-cycles 16000
```

The simulator uses `tests/avr_tick.mjs` for the AVR interrupt-enable delay and
four-cycle interrupt entry. Clock events continue while an IRQ is deferred.
A physical ATmega328P board and analog output have not been measured.

All 16 speech recordings pass the complete player: **6,467 frames /
2,069,440 samples, zero underruns**, minimum queue 23 samples (previously 20). Two additional
Russian/English runs reserve 16,000 extra CPU cycles/frame (5%): 808 frames,
zero underruns, minimum queue 8. This extra-load result applies to those
two streams, not to arbitrary application workloads. See
`reports/wb1-speed-{asm,c,kernels,pwm,pwm-load5,admission-audit}.json`.
The earlier `wb1-*` reports retain the original measurements. The speed audit
(`tests/audit_wb.py --speed --rebuild --avr-gcc avr-gcc`) verifies frozen source
hashes, inputs/PCM/PWM and freshly rebuilt images against the executed binaries.

## Listening comparison

```sh
python Codecs/Speex/AVR/tools/compare_wb.py
```

`build/wb-listening/index.html` contains three aligned comparisons: original
16-kHz audio, full Xiph WB and compact WB. Gain is unchanged. After removing
the 24-sample QMF delay difference, compact-vs-full waveform SNR is 31.38 dB
for `ru_pushkin_a`, 25.79 dB for `en_letter_a` and 26.43 dB for
`ru_slutskaya_a`, without clipping. These are waveform comparisons, not a
perceptual speech-quality score or recordings of the physical board.
Source credits accompany the corpus in `build/real-speech/ATTRIBUTION.md`.
