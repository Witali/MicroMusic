# LPX v5: reuse dead pitch-history slots for polynomial scratch

The explicit `sram512` memory profile removes two 12-word polynomial arrays
from `Lpx4HybridCore`, saving **96 persistent bytes**. The `standard` profile
and default generated code stay unchanged. This is a measured RAM/CPU tradeoff
for 512-byte-class devices, rather than a real-time ATtiny88 player admission.

## Lifetime and correctness

Compact v5 pitch lags are 18..145 inclusive. The 256-byte ring cursor points
to the next write; only the preceding 145 slots can be read by prediction.
The following 111 slots are dead until actual excitation overwrites them.
LSF conversion runs synchronously between sample operations, with that cursor
fixed. It can therefore borrow 96 bytes without shortening the pitch history
or changing any per-sample read/store operation.

Round the workspace start up to a multiple of four, modulo 256. The alignment
lead is at most three bytes, so both 48-byte arrays occupy at most 99 of the
111 dead slots. Each four-byte word starts at an index in 0,4,...,252 and stays
inside the physical ring; array indexing wraps between words. `memcpy` loads
and stores avoid aligned `int32_t*` casts, strict-aliasing problems and invented
object lifetimes in an `int8_t` array. The original descending recurrence,
split-product floors, interpolation, clamping and arithmetic backend remain
unchanged. No workspace pointer is stored in the decoder, so ordinary copies
and resets remain valid.

This reasoning applies to the admitted **v5-only** parser. Requiring
`LPX4_COMPACT_ONLY=1` is a scope/compatibility guard; reduced support for other
formats is not inferred from their current lag expressions. A changed format,
larger lag, concurrent conversion, or conversion using a different cursor
would require a new proof. The object is not reentrant while decoding.

## Build contract

Use [the profile header and instructions](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/profiles/README.md)
consistently in the core and every caller. CPU/platform headers still select
real hardware; the profile never defines `__AVR__`, an ISA level, or an assembly
enable flag. Native C tests need no pretend CPU defines.

The measured AVR5 backend is ATmega328P, GNU ABI, AVR-GCC 7.3.0, `-Os -flto
-mcall-prologues -mrelax -fno-exceptions -fno-rtti -ffunction-sections
-fdata-sections -std=gnu++11`, 16 MHz, `LPX4_FUNCTION_TUNING=0`,
`LPX4_AVR_DOT_UNROLL=1`, `LPX3_LPC_SEGMENTS=2`, compact speech enabled, compact
only. `LPX4_ENABLE_ASM=0/1` independently selects portable C or the existing
explicit AVR5 assembly. Assembly statements and all math code are untouched.
ATtiny88 is AVR25 without MUL and uses C. Its no-IRQ probe additionally uses
`-fno-jump-tables`, matching the existing bounded measurement recipe.
Those completed probes used the installed Atmel `avr/include/avr/iotn88.h`
(revision 2225, 2011-03-02) through `<avr/io.h>`, with AVR-LibC 2.0.0 dated
20150208. The nonexistent short `vendor/include` path supplied no headers;
the repository's ATtiny_DFP 3.4.278 was not used. A read-only preprocessing
trace of the saved inputs and the completed link maps now pin all actual
transitive toolchain headers and linked runtime files in the receipt.

## Final-source measurements

Two fixed 19,200-sample streams are labelled A (P4, 1,008 bytes) and B (P6,
1,899 bytes). The table reports complete Flash including audio, diagnostic
static RAM, and average wall cycles inside each `decoder.next()` call. IRQ
cycles during a call are included. The standalone ATmega328P player has a
512-byte queue, 384-byte prefill, normal active Timer1 ISR and no added ISR
load. All eight runs terminated successfully and reproduced every PWM sample.

| Workload/backend | Full Flash standard -> sram512 | Static RAM | Mean decode cycles | Increase | Max 160-call cycles standard -> sram512 | Underruns standard -> sram512 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A / C | 5952 -> 6016 | 1039 -> 943 | 3316.536 -> 3319.868 | 0.1005% | 588546 -> 589439 | 13837 -> 13872 |
| B / C | 6842 -> 6906 | 1039 -> 943 | 3168.309 -> 3172.795 | 0.1416% | 562934 -> 564334 | 12457 -> 12492 |
| A / explicit AVR5 ASM | 5760 -> 5832 | 1039 -> 943 | 851.581 -> 858.330 | 0.7926% | 155382 -> 157453 | 0 -> 0 |
| B / explicit AVR5 ASM | 6650 -> 6722 | 1039 -> 943 | 797.073 -> 803.854 | 0.8508% | 143367 -> 145732 | 0 -> 0 |

The C rows are throughput failures despite exact decoded output. The two ASM
rows demonstrate active-IRQ output for this specific AVR5 harness, not for an
ATtiny88 or arbitrary corpus. The observer starts stack accounting at player
readiness; it does not establish a complete startup stack bound.

The actual Tiny88 C no-IRQ probes use 398 bytes of decoder state, 403 bytes of
static RAM and a 54-byte observed stack. A/B complete Flash is 5420/6310 bytes;
their verified program/data splits are **4412 + 1008 / 4411 + 1899 bytes**.
The exact stream array `_ZL5audio` occurs once at Flash offset `0x68` in each
image. These program costs describe unpaced test images, not complete playback
firmware.
Mean full-probe cycles/sample is 6401.611/6404.871, with worst inter-output gaps
44879/45588 cycles. These totals include startup/final bookkeeping. Their
existing transpiled AVR25 CPU rejects unsupported instructions; it runs the
real Tiny88 instruction set with no pretend AVR5 hardware. No IRQ or queue
was active. At 16 MHz/8 kHz, only 2000 cycles/sample are available, so this is
**not real-time 8 kHz support**, and no full queue/ISR budget in 512 bytes is
admitted. The 6310-byte image also exceeds the stated 6012-byte bootloader
application region. State-size success alone is insufficient for playback.

## Validation and provenance

The production implementation ports the project's measured dead-ring
prototype, retaining its circular byte-access arithmetic and recurrence. It
does not import external assembly. The original arrays remain under the
standard branch. Final sources were freshly measured after extracting the
repeated ring recurrence into a force-inline helper; all eight outcomes
reproduce the earlier prototype's exact measurements.

Focused native contracts compare complete PCM16 and PWM for 112 synthetic
streams plus the two fixed streams, each at one/two/four LPC segments and in
default, explicit standard, flag-selected SRAM512 and force-included SRAM512
builds. They cover partial samples, lags 18/145, wrap boundaries, changing,
repeated and clustered spectra, optional innovations, resetting and copies
midstream. Direct workspace tests preserve every one of the 145 live slots at
all 256 cursor positions. Compile guards reject invalid/noncompact profiles.
The profile removes exactly 96 bytes in every tested native layout.

The four standard complete Flash binaries (two streams x C/ASM) are identical
to the pre-change `2e482949` build. Four additional common/compact x C/ASM AVR
objects are byte-identical. These results establish unchanged defaults for the
declared recipes, not output timing for untested flags or MCUs.

[The anonymous receipt](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/profiles/sram512-measurements.json)
contains numerical rows and source-code hashes. Private exact streams, image
fingerprints and detailed local logs stay outside the committed documentation.

```sh
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests \
  -p test_sram512_profile.py -v
```

The optional fixture test reads local paths from `LPX4_SRAM512_FIXTURES` as a
JSON list; it does not require media files to be committed. The native tests
use Python's standard library and a host C++11 compiler selected by `CXX`.
