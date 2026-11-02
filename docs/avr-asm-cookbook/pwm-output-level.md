# Calibrate speech output without changing the ISR

Original project implementation for AVR25 ATtiny88 (no MUL, 512 B SRAM) and
AVR5 ATmega328P, 16 MHz, GNU AVR ABI, AVR-GCC 7.3.0. LPX uses 8 kHz; Speex
uses 8/16 kHz. Arithmetic is portable C; existing decoder C/opt-in ASM selection
and vendor-header hardware access are independent of this output stage.

Measure the complete decoded PWM8 recording before building its player. Choose
one constant Q7 numerator N in 128..255 and apply it before queue publication:

```text
output = clamp(floor((input * N + 64) / 128) + 128 - N, 0, 255)
```

This is exactly nearest rounding of `(input-128)*N/128`, with positive ties.
PWM 128 remains 128, including all pauses. One gain for a reset-chain dialogue
preserves the relative level of its normalized phrases. Do not scale the
predictor, excitation or decoder history; doing so changes codec behavior.

The source uses unsigned shift/add terms selected at preprocessing time:
`255*255+64 = 65089` fits uint16_t. It avoids negative shifts and does not
require an AVR25 software multiplication loop or a 256-byte Flash lookup table.
Unity is the default and compiles out. The independent C, Python and JavaScript
implementations agree for all 32,768 input/gain pairs, including saturation.

For amplified recordings, choose the greatest numerator leaving PWM codes
2..254. Record the input/output hashes and extrema and prove no sample
saturates. Releases already reaching a rail keep unity: output gain cannot
repair existing decoder clipping. This preserves dynamics; there is no AGC,
compression, limiter or time change. It expands existing PWM8 values rather
than recovering quantization precision lost earlier.

Measured before/after examples from the public retained recordings:

| Recording | Before PWM | After PWM | Gain |
| --- | ---: | ---: | ---: |
| LPX Vinni P4, Nano and Tiny88 | 43..201 | 2..236 | +3.43 dB |
| LPX Vinni P6, Nano and Tiny88 | 49..218 | 18..254 | +2.91 dB |
| Speex Vinni NB2.15, Nano | 59..200 | 7..254 | +4.86 dB |
| Seven-segment Nano dialogue | 47..223 | 20..254 | +2.46 dB |

All 27 complete public LPX/Speex images were executed with timers and IRQ
active, with exact reference PWM and zero underruns: eight Nano LPX, nine
Tiny88 LPX, nine Nano Speex and one dialogue. LPX uses calibrated simavr 1.6;
Speex uses AVR8js 0.21.1. No physical analog-output measurement is claimed.
Static SRAM is unchanged. Added program Flash for amplified images is
78..126 B; exact costs and stack/queue margins are in the catalogs. ISR source
is unchanged; processing belongs to the producer. These are admission results
for these complete recordings, not a claim that foreground gain is free or
that every other workload has the same timing margin. ATtiny13A releases are
outside this LPX/Speex output stage.

[Portable C](../../Codecs/common/pwm_gain.h),
[Python calibration](../../tools/pwm_output_level.py),
[exhaustive C check](../../tools/test-pwm-output-level.py),
[public media/receipt check](../../web-player/tests/speech-output-level.test.mjs).
Rebuild with the existing public catalog tools: `build-nano-speech-catalog.py`,
`build-tiny88-speech-catalog.py`, `build-speex-nano-catalog.py` and
`build-nano-dialogue.py`. They calibrate from fresh decoder output, so repeated
builds do not amplify an already amplified WAV. Compressed streams and
canonical input recordings are unchanged. The catalog keeps exact HEX/WAV
bindings, and WebUI versions changed downloads and previews by content hash.
