# LPX memory profiles

`standard` remains the default. The explicit `sram512` profile saves **96 bytes
per decoder** by sharing dead pitch-history storage with the two temporary LSF
polynomials. It requires compact-only parsing and preserves decoded PCM/PWM
and the 256-byte pitch history. The default profile supports compact v5;
the current Tiny88 builder separately enables v8/mode15 with
`--enable-sparse80`. It trades a small measured amount of speed and Flash for
RAM; it is not a faster profile.

Force-include the configuration in **every translation unit**, including the
core implementation and its callers:

```sh
avr-g++ -mmcu=attiny88 -DF_CPU=16000000UL \
  -include Codecs/LPX/01_ACTIVE_Q0_CODEC/profiles/Lpx4Sram512.h \
  -I Codecs/LPX/01_ACTIVE_Q0_CODEC/src ...
```

Alternatively, consistently define all four options:

```text
LPX4_MEMORY_PROFILE=LPX4_MEMORY_PROFILE_SRAM512
LPX4_ENABLE_SPEECH=1
LPX4_ENABLE_SPEECH_COMPACT=1
LPX4_COMPACT_ONLY=1
```

The constants are `LPX4_MEMORY_PROFILE_STANDARD=0` and
`LPX4_MEMORY_PROFILE_SRAM512=1`. Invalid numeric profiles and a noncompact
`sram512` build are rejected. Mixing profiles across translation units violates
the class layout contract. The profile header changes no processor definition,
clock, arithmetic backend or input-source selection. C remains available and
is the default. ATtiny88/AVR25 has no hardware MUL; the current
[Tiny88 player](../examples/ATTINY88_V5_PLAYER/README.md) explicitly selects
the supported AVR25 software-product assembly backend with
`LPX4_ENABLE_ASM=1`. `LPX4_ARCH=LPX4_ARCH_GENERIC` selects the equivalent C
arithmetic on the same real AVR target.

The current fixed-header ROM build also omits five bytes of private state
whose values are already pinned and checked at compile time: decoder state
is **393 bytes**, while the unpinned SRAM512 profile remains **398 bytes**.
The optional 24-byte playback FIFO saves another eight bytes against FIFO32.
See the [current player guide](../examples/ATTINY88_V5_PLAYER/README.md) for
complete active-interrupt timing, static RAM, stack and Flash limits. Speex is
excluded from this Tiny88 profile.

## Historical C-only probes

These measurements predate the integrated AVR25 assembly player. They describe
the original dynamic-header C profile and remain valid evidence for that
recipe; they do not describe the current fixed-header ROM player.

On AVR-GCC 7.3, with compact v5, linear LPC history and two LPC segments, the
ATtiny88 decoder state is **494 -> 398 bytes**. A minimal no-IRQ decode probe
uses 403 bytes of static RAM plus a measured 54-byte stack. This leaves only
55 bytes by that probe's stack convention, before adding a playback queue and
interrupt requirements. This does **not** admit a complete 512-byte player.

The two fixed 19,200-sample Tiny88 C probes require about **6,402 / 6,405 cycles
per sample**, versus 2,000 available at 16 MHz / 8 kHz. Their full Flash images,
including 1,008 / 1,899 stream bytes, occupy **5,420 / 6,310 bytes**. The second
also exceeds the stated 6,012-byte Micronucleus application region. These are
measurement images, not downloadable or supported audio firmware.
The verified program-only portions are **4,412 / 4,411 bytes**. Each stream
occurs once as `_ZL5audio` at Flash offset `0x68`; subtracting that exact array
from the complete image gives these **unpaced test-image** costs. They do not
include a complete interrupt-driven playback application.

The completed Tiny88 probes used the installed Atmel toolchain's
`avr/include/avr/iotn88.h` (Atmel revision 2225, 2011-03-02), selected through
`<avr/io.h>`, with AVR-LibC 2.0.0 (20150208). They did not use the repository's
newer ATtiny_DFP 3.4.278: the short `vendor/include` directory does not exist.
The receipt pins the actual transitive compiler headers and linked runtime
files. This provenance was inspected afterward without rebuilding the images.

The [cookbook entry](../../../../docs/avr-asm-cookbook/lpx-sram512.md) explains
the lifetime proof, complete active-IRQ AVR5 comparison and validation limits.
[Anonymous measurements](sram512-measurements.json) bind the historical source
bytes to those results. No encoded data, media fingerprints or target images are
included in that receipt.
