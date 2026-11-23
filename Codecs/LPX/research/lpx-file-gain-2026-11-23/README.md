# Constant V9 output gain: validation

The optional [gain word](../../01_ACTIVE_Q0_CODEC/LPX9_GAIN_FORMAT.md) is applied
after synthesis and postfilter history updates. Enabling Web normalization
measures the complete decoded recording, then stores one Q4.12 coefficient.
The original P4/P6 payload is retained. Strict 3/8 kbit/s presets reserve two
bytes before selecting candidates and check the final complete-file ceiling.

## AVR workload and limits

The public `web-player/audio/lpx-bread/original.wav` was converted to mono 8 kHz
PCM16 and divided by four to exercise positive gain. This is a gain/playback
test, not an encoding-quality comparison. Each preset encoded 19200 samples
with target -18 LUFS and maximum boost +12 dB: 3 kbit/s produced 863 bytes and
gain 10439/4096; 8 kbit/s produced 1979 bytes and gain 9851/4096.

Four linked images used AVR-GCC 7.3.0, GNU AVR ABI, simavr 1.6, 16 MHz CPU,
8 kHz output, explicit ASM arithmetic and ISR, runtime headers, FIFO32/prefill24,
two LPC segments, multiplication unroll2 and neutral player gain128. Tiny flags
were `-fno-gcse -fno-code-hoisting -fno-move-loop-invariants -morder2
-fno-tree-loop-im -fno-tree-ccp`. The existing verifier compared every PWM sample
with separately compiled portable C, checked EOF/draining, active IRQ entry and
completed RETI. All four images passed, totaling 76800 samples and zero
underruns. [Numeric results](avr-validation.json) record linked Flash, SRAM,
peak stack, stack margin and output spacing. Both Tiny images fit the 6012-byte
application region used by the standard bootloader; the 8 kbit/s case uses
5864 bytes and reaches minimum FIFO occupancy1.

These are simulator results for one fixed phrase and these build options.
The [source receipt](source-transition.json) retains old measurements against
the archived pre-extension source; their size/timing claims do not apply to
the new gain-enabled decoder. The new four-image measurements stand separately.
They do not establish arbitrary-file real-time support, a worst-case timing
bound, other sample rates, Long playback on AVR, or physical-board behavior.
All existing hardware/arithmetic selectors and the C fallback remain available.
`LPX4_ENABLE_FILE_GAIN=0` rejects marked files and removes the new decoder field
and arithmetic; use the same setting in every translation unit.

## Multiply optimization

On AVR25 without hardware MUL, a direct signed32 product sign-extends negative
Q14 samples before the software multiplication loop. Expressing the same
bounded product as unsigned16 magnitudes, then restoring its sign, reduced
active foreground producer work on the Tiny 8 kbit/s workload from
1720.728202 to 1602.397163 cycles/sample. It added 28 Flash bytes versus that
first gain-enabled implementation. The first implementation had 128 underruns;
the selected form had zero. Increasing its queue alone did not fix the first
implementation. These figures concern the new multiply implementation, not
the old decoder without file gain.

The reusable C functions are in `src/Lpx4FileGain.h`. The default selects the
unsigned expression only for `__AVR__ && !__AVR_HAVE_MUL__`; explicitly define
`LPX4_FILE_GAIN_UNSIGNED_MULTIPLY=0` to retain the direct C expression even on
that target. No new assembly or hardware access is introduced. Both expressions
use signed32 rounding after sign restoration and saturate to Q14 rails.
A standalone WASM probe compares 720904 boundary/dense cases, covering every
stored gain against seven samples and every Q14 sample against eight gains.

## Host and browser checks

`web-player/tests/lpx-file-gain.test.mjs` checks complete PCM against independent
post-decode scaling for P4/P6, actual Sparse80, Long and public speech, including
minimum/maximum gain, saturation and error recovery. It also checks scalar/SIMD
equality, native C equality when configured, unchanged ordinary payloads,
target/max-boost controls and final 3/8 caps. Native CLI and real worker tests
exercise the new controls. Historical unmarked output remains covered by the
existing native/WASM regression suite. Older published readers reject the new
flag. New readers continue accepting unmarked files.

The integrated LUFS meter retains its independently checked libebur128 reference
tests. The -1 dBFS ceiling is a decoded **sample** peak limit, not a true-peak
claim. Below-gate and shorter-than-400ms recordings retain unity. Metric values
and gain changes are not evidence of improved coding quality.
