# UM88 platform: shared interpolation and bootloader entry

Applies to ATtiny88 / AVR25 without MUL, AVR-GCC 7.3.0, ordinary AVR-GCC ABI,
`-Os -fno-jump-tables -ffunction-sections -fdata-sections` and
`-Wl,--gc-sections`. The arithmetic below is portable C99 and adds no ISA
requirement. Hardware access remains in `ATtiny88/Music/universal/platform.c`;
C versus explicitly enabled AVR assembly remains an independent engine choice.
This is an original project technique; no external implementation was copied.

## Share four quarter points between channels

The former stereo producer repeated four interpolation expressions and four
mono/stereo branches. A `noinline` C helper now writes one channel with a byte
stride of 1 or 2. For 8-bit endpoints `p` and `t`, the same four samples are:

```c
uint16_t accumulator = (uint16_t)p * 4;
int16_t delta = (int16_t)t - p;
for (uint8_t n = 0; n < 4; ++n) {
    accumulator += delta;
    output[n] = accumulator >> 2;
}
```

The accumulator stays in 0..1020. The first three points are
`floor((3*p+t)/4)`, `floor((p+t)/2)` and `floor((p+3*t)/4)`; the fourth is `t`.
They equal the former nested midpoint averages, including decreasing ramps and
all rounding. This reasoning requires unsigned 8-bit endpoints and an integer
accumulator wide enough for 1020. The actual helper writes the shared byte ring
and wraps its cursor; it does not assume power-of-two ring length.

Intermediate size measurement on the common stereo-capable 8 MHz engine, before
integration of the new 9-bit score decoder:

| Arithmetic backend | Repeated stereo producer | Shared C interpolation | Change |
| --- | ---: | ---: | ---: |
| Explicit C fallback | 3226 B | 3010 B | -216 B |
| Explicit AVR ASM | 3088 B | 2872 B | -216 B |

The workload was the same compiled engine with the Greensleeves score and the
192-byte PWM ring. Song data was outside the measured engine prefix. The
current decoder adds independent code, so current total sizes differ from this
comparison. `tools/test-universal-boards.py` exhaustively checks all 65,536
endpoint pairs. The complete-song auditor independently checks every generated
PWM byte with IRQs active. This is a Flash-size result, not a speedup claim.
The C stereo fallback is arithmetically equivalent but currently misses the
real-time deadline at both 8 and 16 MHz; it must not be presented as a qualified
real-time profile.

## Restore peripheral power before loader cleanup

Micronucleus jumps through the application reset vector without guaranteeing
hardware-reset peripheral state. The board-only `.init3` C hook disables the
watchdog before BSS clearing, after the CRT has initialized SP and GCC's zero
register. Restore `PRR=0` before writing timer/ADC/SPI/TWI cleanup registers:
power-gated register state can be inaccessible, and restoring power resumes the
previous peripheral state. The ATtiny48/88 datasheet 8008H, section 7.4.3,
[defines that ordering constraint](https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf#page=40).

Register names come from the unmodified Microchip ATtiny_DFP 3.4.278 header;
license and pack provenance remain in the universal engine's `vendor/` folder.
`web-player/tests/universal-board-startup.test.mjs` executes the real linked
CRT/hook with inherited watchdog, stack and PRR state, and checks instruction
ordering using addresses parsed from that official header. The emulator does
not model every power-gating side effect, so the explicit ordering assertion
is required in addition to the complete-song audio audit. No physical-board
measurement is implied by those emulator checks.

## Experimental contiguous output variants

A mono producer starts on a four-byte boundary, advances by four bytes, and has
capacity divisible by four. Its four samples can therefore be stored through
one contiguous pointer with one wrap check after the block. For stereo the
same argument applies to eight-byte blocks when capacity is divisible by eight;
other legal capacities need the original per-store wrapping loop.

Scratch measurements with the same AVR-GCC/options and compact 9-bit decoder:

| Output producer | 8 MHz / 128-byte ring code | 16 MHz / 192-byte ring code | Children 16 MHz Flash |
| --- | ---: | ---: | ---: |
| Current shared ramp | 3018 B | 3078 B | 5947 B |
| Mono contiguous fastpath, stereo unchanged | 3082 B | 3142 B | 6011 B |
| Shared unrolled channel helper | 3046 B | 3106 B | 5979 B |

Across 1024 samples of eight held mono voices at 8 MHz, active CPU cycles from
`um_render` return to FIFO publication were 169, 99 and 133 respectively. The
shared unrolled helper also reduced the 16 MHz Lumiere stereo median from 348 to
270 cycles. IRQ time was excluded, clocks before `um_render` were excluded, and
all measured runs had zero underruns over that observation interval. This does
not establish full real-time admission: all output-only variants still failed
the dense-eight-voice workload and the 128-byte polyphony restart because the
25,134-cycle control burst exhausted the FIFO. Decoder optimization remains
necessary. None of these candidates was applied to the retained firmware.

The capacity/alignment proof is essential: dropping per-store wrap checks for
a stereo capacity such as 12 or 20 bytes corrupts the ring. Do not use this
optimization solely because a ring happens to be a power of two in one build.
The portable helper and C arithmetic backend remain independently selectable;
this experiment introduces no handwritten assembly or new ISA assumptions.
