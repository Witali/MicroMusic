# LPX: compose a dialogue with one decoder

Applicable to the existing AVR5 ATmega328P player at 16 MHz, GNU AVR ABI,
AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`. This is original project
composition using the existing reset-chain interface; no new arithmetic or
assembly kernel is introduced. Hardware registers remain in AVR-LibC headers.

Reset the same decoder between independent Flash streams while Timer1 and the
SPSC PWM queue continue running. This shares program and working memory across
phrases. The combined sample count may exceed the per-stream 64,000-sample
limit: each individual stream must still satisfy that bound. Do not stop the
sample timer or use busy-wait delays between phrases.

Encode pauses as ordinary LPX v5 P4 streams with scale zero and valid complete
packets. The decoder emits PWM 128 for exactly the requested sample count,
including a partial last frame. This preserves the sample clock and exercises
the same queue, EOF and reset rules at both sides of every pause. It costs
205 B per 0.5-second pause and 552 B for 1.5 seconds in this workload; a new
silence opcode or player state machine has not been measured.

Normalize public source copies before encoding, using EBU R128 integrated
loudness and constant gain. Keep the canonical originals untouched. Measure
the decoded PWM again: matching source loudness alone does not guarantee
matching loudness after a lossy codec. The builder checks both, plus independent
common C, compact C and Python model output. C is the default backend, even on
AVR; `--enable-asm` explicitly enables supported AVR assembly. Flash access and
timer setup are independent of that choice.

The following measurements describe the initial unity-output image at
`095e701a`. The current release adds [calibrated output gain](pwm-output-level.md)
and has updated complete-image receipts.

Measured with simavr 1.6 and the calibrated observer charging four hardware
entry cycles and the completed RETI: four P6 phrases and three P4 pauses
(0.5 / 1.5 / 0.5 s), 81,254 samples, 10.15675 s. Full Flash is 10,406 B
(program 4,600 B, streams 5,806 B), static SRAM 756 B. Every PWM byte matches
the independent references; all 81,254 timer events complete with zero
underruns. Observed output intervals are 1,996..2,004 cycles, complete IRQ
maximum 76 cycles, minimum observed stack margin 1,231 B. These measurements
cover this exact chain and toolchain, not physical analog output or other
profiles. There is no before/after decoder speed claim.

[Recipe, normalization results and reproduction](../../ATmega328/Sound/lpx-dialogue/README.md),
[builder](../../tools/build-nano-dialogue.py),
[path-free hashes and receipt](../../web-player/audio/lpx-dialogue/manifest.json).

## Reuse normalized source across codec choices

`tools/dialogue_source.py` now owns the common resampling and constant
pre-encoding loudness preparation. LPX and Speex use those same source copies;
the Speex version does not transcode decoded LPX. Rebuilding LPX after extraction
retains its exact HEX and PWM WAV bytes, including the sample-exact pauses.

The continuous Speex stream includes 80 ms source padding and complete 20 ms
frames. At 8/16 kHz it emits 81,920/163,840 samples, respectively, through the
existing 128-byte player queue. The frame counter is sufficient for all 512
frames; do not impose LPX's per-stream sample limit on this separate format.

On the existing AVR5 / 16 MHz / GCC 7.3.0 D3 ASM profile, NB2.15, WB3.95 and
WB9.8 complete with exact independent captured PWM and zero underruns under
active timers/IRQ in AVR8js 0.21.1. Complete Flash is 15,904 / 25,668 / 30,208 B;
packet data is 3,072 / 5,120 / 12,800 B. Minimum free SRAM is 698 / 449 / 450 B.
WB9.8 leaves 512 B below the classic Nano's conservative 30 KiB application
boundary. This extends workload admission; no new decoder assembly is added.
Existing explicitly selectable C backends and independent hardware routing
remain available. No physical-board or new full-C timing claim is made.

Only verified fitting images enter the selectable catalog. Oversized measured
profiles remain disabled choices with no public HEX or WAV. The UI groups
codec variants into one dialogue card.
[Builder](../../tools/build-speex-dialogue.py),
[source recipe and commands](../../ATmega328/Sound/lpx-dialogue/README.md),
[complete hashes and timing](../../web-player/firmware-speex-dialogue-atmega328p.json).
