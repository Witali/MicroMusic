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
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --out Codecs/Speex/AVR/build/lsp-quarter-wb-asm
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend c --out Codecs/Speex/AVR/build/lsp-quarter-wb-c
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

The optimized AVR ASM decoder uses 17,776 B Flash and 1,299 B static SRAM in
the mailbox harness. On the same 10,563 frames:

| Decoder-only measurement | Initial WB | Fused WB/QMF | Third IIR cache | Current NB LSP |
| --- | ---: | ---: | ---: | ---: |
| Mean cycles/frame | 279,128 | 265,805 | 264,889 | 261,068 |
| Maximum observed cycles/frame | 285,596 | 273,528 | 272,612 | 268,595 |
| Maximum observed time at 16 MHz | 17.850 ms | 17.096 ms | 17.038 ms | 16.787 ms |
| Peak stack | 401 B | 257 B | 257 B | 243 B |
| Free SRAM at peak | 349 B | 492 B | 492 B | 506 B |
| Flash | 17,504 B | 17,616 B | 17,620 B | 17,776 B |

The shared NB/HB IIR now caches a third LPC word in a dead base-pointer pair.
Fixed pointer rewinds save another 916 cycles/frame without changing PCM,
static RAM or stack; Flash grows four bytes. The preceding WB-specific fusion
stage saved 1.48% mean cycles. That IIR stage left the C decoder unchanged.
Decoder-only timing excludes output/interrupts and does not establish
continuous playback.

The current shared NB interpolation computes one quarter-frame delta and
accumulates raw LSP state while enforcing the original sequential margin only
on its output. This outlined C helper is used by both backends. The ASM WB
mean falls another 3,820.477 cycles/frame; stack drops 14 B and Flash grows
156 B. NB cache/reset behavior and compact WB PCM remain exact. HB interpolation
and QMF arithmetic are unchanged. See `reports/lsp-quarter-wb-*.json`.

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

Innovation reconstruction and folding now share one pass, keeping the
intermediate signed16 sample in registers while preserving both original
rounding stages. NB and WB use shared source macros without a per-sample
CALL; that WB-only stage left the NB-only image unchanged. QMF checks signed24 range before
alignment, avoiding the extra sign-extension byte; the exact -32768 output
still clamps to -32767. Both optimized kernels retain selectable C paths.

The decoder state structures/arena total 1,268 B on AVR (716 B NB state, 60 B scratch,
492 B WB state). The full PWM player uses 1,429 B static SRAM and reaches
252 B stack, leaving **367 B free**. A Russian 404-frame demo uses 28,162 B
Flash, including 10,100 B of compressed audio.

## Reproduce validation

First prepare the retained human speech with `tools/prepare_real_speech.py`,
then the 16-kHz recordings with `tests/verify_rates.py`. Build the native WB
decoder/reference above, then run:

```sh
python Codecs/Speex/AVR/tests/prepare_wb.py
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend asm --firmware Codecs/Speex/AVR/build/lsp-quarter-wb-asm
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend c --firmware Codecs/Speex/AVR/build/lsp-quarter-wb-c
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
equations. Those WB-kernel changes left the NB-only build unchanged.
QMF adds 92 blocks placing each phase precisely around rounding/clipping
boundaries. Fused excitation adds 5,760 blocks / 230,400 samples per backend,
all codebook indices, 12 scale boundaries and 15 gains including signed32
extrema. At that WB fusion stage the C image used 19,326 B Flash (previously 19,002 B),
with mean time 699,537 -> 666,616 cycles/frame (4.71% less) and maximum
711,178 -> 678,242. The current NB-LSP stage further reduces C Flash to
18,600 B and mean/max cycles to 654,259 / 665,226, with 501 B peak stack and
248 B free SRAM in the mailbox. It still exceeds the real-time deadline; these timings
do not establish performance on another architecture.

The complete 16-kHz PWM player is `src/wb_player.c`, using OC1A/PB1/D9 at
62.5 kHz carrier, Timer2 CTC (`OCR2A=124`, prescaler 8), a 128-byte output
ring and 80-sample callbacks. Build a demo or run all retained speech:

```sh
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --stream Codecs/Speex/AVR/build/wb-corpus/streams/ru_pushkin_a.spxraw --out Codecs/Speex/AVR/build/wb-demo
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/lsp-quarter-wb-normal
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/lsp-quarter-wb-load5 --filter "^(ru_pushkin_a|en_letter_a)$" --frame-load-cycles 16000
```

The simulator uses `tests/avr_tick.mjs` for the AVR interrupt-enable delay and
four-cycle interrupt entry. Clock events continue while an IRQ is deferred.
A physical ATmega328P board and analog output have not been measured.

All 16 speech recordings pass the complete player: **6,467 frames /
2,069,440 samples, zero underruns**, minimum queue 26 samples (previously 24). Two additional
Russian/English runs reserve 16,000 extra CPU cycles/frame (5%): 808 frames,
zero underruns, minimum queue 10. This extra-load result applies to those
two streams, not to arbitrary application workloads. See
`reports/wb2-{asm,c,kernels,pwm,pwm-load5,admission-audit}.json`.
The latest evidence is `reports/lsp-quarter-wb-*.json` and
`reports/lsp-quarter-admission.json`: all 16 ordinary WB PWM streams and both
loaded streams are fresh simulations, preserving exact PWM. The C and ASM
decoder results each cover all 10,563 corpus frames plus 744 repeat cases.
The older `iir-cache3-*` and `wb2-*` reports retain the previous shared-IIR
and fused-WB/QMF measurements.
The earlier `wb1-*` reports retain the previous measurements. The audit
(`tests/audit_lsp_quarters.py --rebuild --avr-gcc avr-gcc`) verifies frozen source
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
