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
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --out Codecs/Speex/AVR/build/pair-wb-asm
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend c --out Codecs/Speex/AVR/build/pair-wb-c
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

The optimized AVR ASM decoder uses 17,500 B Flash and 1,279 B static SRAM in
the mailbox harness. On the same 10,563 frames:

| Decoder-only measurement | Initial WB | Fused WB/QMF | Third IIR cache | NB LSP | Subframe map | Complete prefix | LSP lifetime/bounds | ASM margin/LPC | Paired LPC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mean cycles/frame | 279,128 | 265,805 | 264,889 | 261,068 | 259,073 | 257,680 | 257,477 | 256,761 | 254,853 |
| Maximum observed cycles/frame | 285,596 | 273,528 | 272,612 | 268,595 | 266,781 | 265,344 | 265,131 | 264,375 | 262,360 |
| Maximum observed time at 16 MHz | 17.850 ms | 17.096 ms | 17.038 ms | 16.787 ms | 16.674 ms | 16.584 ms | 16.571 ms | 16.523 ms | 16.398 ms |
| Peak stack | 401 B | 257 B | 257 B | 243 B | 220 B | 178 B | 178 B | 178 B | 178 B |
| Free SRAM at peak | 349 B | 492 B | 492 B | 506 B | 529 B | 571 B | 591 B | 591 B | 591 B |
| Flash | 17,504 B | 17,616 B | 17,620 B | 17,776 B | 17,314 B | 17,360 B | 17,212 B | 18,010 B | 17,500 B |

The shared NB/HB IIR now caches a third LPC word in a dead base-pointer pair.
Fixed pointer rewinds save another 916 cycles/frame without changing PCM,
static RAM or stack; Flash grows four bytes. The preceding WB-specific fusion
stage saved 1.48% mean cycles. That IIR stage left the C decoder unchanged.
Decoder-only timing excludes output/interrupts and does not establish
continuous playback.

The preceding shared NB interpolation computes one quarter-frame delta and
accumulates raw LSP state while enforcing the original sequential margin only
on its output. This outlined C helper is used by both backends. The ASM WB
mean falls another 3,820.477 cycles/frame; stack drops 14 B and Flash grows
156 B. NB cache/reset behavior and compact WB PCM remain exact. HB interpolation
and QMF arithmetic are unchanged. See `reports/lsp-quarter-wb-*.json`.

The preceding subframe map combines the NB header/indices into one bounded C
reader. WB reuses dead interpolated-angle scratch for its synchronous indices
instead of a stack-local SpeexBits cursor and four-byte array. It saves another
1,995.048 mean cycles/frame and 23 B observed stack in ASM; Flash falls 462 B.
Both backends preserve compact-profile PCM, and all current PWM images are
fresh simulations. The reader uses C regardless of the arithmetic backend.

The preceding complete prefix extracts NB LSP and gain from bytes 0..3. Exact
quarter-scale dequantization prepares the same interpolation delta before
excitation and removes the remaining stack-local SpeexBits object. Equal
cached NB frames skip an unused copy. The ASM mean falls a further 1,393.461
cycles/frame, with 42 B less observed decoder stack and 46 B more Flash.
HB/QMF equations and all output PCM remain unchanged from this compact profile.
See `reports/prefix-wb-*.json`; prefix quality tests also compare every NB
LSP code triple against untouched Xiph on both host and actual AVR instructions.

The preceding NB stage shares interpolated-angle and LPC storage, reducing
scratch 60 -> 40 B. LPC enters state before WB overwrites that slot with
callback indices. Exhaustive codebook bounds make the NB endpoint clamps
redundant; the validated C interpolation retains every interior margin and
original rounding. WB ASM mean falls another 202.305 cycles/frame, Flash
falls 148 B and static SRAM falls 20 B. Stack remains 178 B. PCM stays exact
to the existing compact WB oracle; HB and QMF equations remain unchanged.

The preceding NB codebook-margin/ASM stage reduces WB mean by another
716.368 cycles/frame and maximum by 756 cycles; Flash grows 798 B.
Only two mutually exclusive center repairs remain after exhaustive affine
proofs, and the ASM advance feeds LPC without materializing ten frequencies.
The common output stage is outlined. Static SRAM and the WB stack bound stay
unchanged; HB/QMF arithmetic and compact-profile PCM remain exact. The C
fallback is separately selectable and verified. See `reports/margin-*`.

The current paired order-ten LPC finish shares sums/differences between
symmetric coefficients. The ASM routine retains successive polynomial words
in alternating register banks and reads each needed byte once. WB mean falls
another 1,907.786 cycles/frame and maximum by
2,015; Flash falls 510 B. Static SRAM, peak WB
stack and compact-profile PCM remain unchanged. Its C helper is explicitly
selectable on AVR; HB order-eight output and QMF arithmetic are unchanged.
See `reports/pair-*` and the direct kernel test `verify_lsp_finish.mjs`.

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

The decoder state structures/arena total 1,248 B on AVR (716 B NB state,
40 B scratch, 492 B WB state). The current full PWM player uses 1,409 B
static SRAM and reaches 187 B stack, leaving **452 B free**. A Russian
404-frame demo uses 27,904 B Flash, including 10,100 B of compressed audio.

## Reproduce validation

First prepare the retained human speech with `tools/prepare_real_speech.py`,
then the 16-kHz recordings with `tests/verify_rates.py`. Build the native WB
decoder/reference above, then run:

```sh
python Codecs/Speex/AVR/tests/prepare_wb.py
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend asm --firmware Codecs/Speex/AVR/build/pair-wb-asm
node Codecs/Speex/AVR/tests/verify_wb.mjs --backend c --firmware Codecs/Speex/AVR/build/pair-wb-c
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
711,178 -> 678,242. The preceding NB-LSP stage further reduces C Flash to
18,600 B and mean/max cycles to 654,259 / 665,226, with 501 B peak stack and
248 B free SRAM in the mailbox. The packet-map stage further reduces C Flash
to 18,188 B and mean/max cycles to 652,574 / 663,347. Its conservative raw-SP
stack bound is 246 B, leaving at least 503 B free in this harness.
The complete-prefix C image uses 18,300 B; mean/max cycles fall again to
651,168 / 661,896, with a conservative raw-SP stack bound of 205 B and
544 B free. The LSP lifetime/bounds stage reduces this to 18,106 B Flash,
1,279 B static SRAM and mean/max 650,840 / 661,550 cycles; stack remains
205 B, leaving 564 B free. The current margin/LPC stage uses 18,962 B
Flash; mean/max fall again to 649,953 / 660,614 cycles with the same static
SRAM/stack bound. Paired LPC further reduces C Flash to 18,712 B
and mean/max to 648,816 / 659,414 cycles, with the same
1,279 B static SRAM and conservative 205 B stack bound. It still exceeds the real-time deadline; these timings
do not establish performance on another architecture.

Stack figures come from the lowest observed SP and can include a transient
value between the high/low SP byte writes. A supplemental 136-frame probe
of the preceding C binary reports raw 501 B versus 277 B after completed SP
writes; the subframe-map binary at 03fad82 reports 246 B by both methods. This sampled
diagnostic does not establish a 255-byte physical stack reduction. ASM is
243 -> 220 B by both methods on that sample. `tests/probe_wb_stack.py` derives
SPL/SPH addresses from the configured `avr/io.h`, checks no stack instruction
occurs between paired writes, and retains header hashes. See
`reports/subframe-stack-probe.json`; the full IRQ admission remains separate.

The complete 16-kHz PWM player is `src/wb_player.c`, using OC1A/PB1/D9 at
62.5 kHz carrier, Timer2 CTC (`OCR2A=124`, prescaler 8), a 128-byte output
ring and 80-sample callbacks. Build a demo or run all retained speech:

```sh
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --stream Codecs/Speex/AVR/build/wb-corpus/streams/ru_pushkin_a.spxraw --out Codecs/Speex/AVR/build/wb-demo
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/pair-wb-normal
python Codecs/Speex/AVR/tests/verify_wb_players.py --avr-gcc avr-gcc --node node --out Codecs/Speex/AVR/build/pair-wb-load5 --filter "^(ru_pushkin_a|en_letter_a)$" --frame-load-cycles 16000
```

The simulator uses `tests/avr_tick.mjs` for the AVR interrupt-enable delay and
four-cycle interrupt entry. Clock events continue while an IRQ is deferred.
A physical ATmega328P board and analog output have not been measured.

All 16 speech recordings pass the complete player: **6,467 frames /
2,069,440 samples, zero underruns**, minimum queue 29 samples (previously 28). Two additional
Russian/English runs reserve 16,000 extra CPU cycles/frame (5%): 808 frames,
zero underruns, minimum queue 14. This extra-load result applies to those
two streams, not to arbitrary application workloads. See
`reports/wb2-{asm,c,kernels,pwm,pwm-load5,admission-audit}.json`.
The latest evidence is `reports/pair-wb-*.json` and
`reports/pair-admission.json`: all 16 ordinary WB PWM streams and both
loaded streams are fresh simulations, preserving exact PWM. The C and ASM
decoder results each cover all 10,563 corpus frames plus 744 repeat cases.
The current player uses 1,409 B static SRAM and 187 B observed peak stack,
leaving 452 B free in both normal and loaded runs.
The older `margin-*`, `lifetime-*`, `prefix-*`, `subframe-*`, `lsp-quarter-*`, `iir-cache3-*` and `wb2-*` reports retain the previous packet-map, NB-LSP, shared-IIR
and fused-WB/QMF measurements.
The earlier `wb1-*` reports retain the previous measurements. The audit
(`tests/audit_lsp_pairs.py --rebuild --avr-gcc avr-gcc`) verifies frozen source
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
