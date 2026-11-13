# ATtiny88 LPX bit reader and compact Rice

`readBits` shares one cache writeback and one byte-wide shift loop between
the cached and refill paths. Each path still masks its own source before
assembling the result. A refill calls `readByte` at the same point, with
the same bounds and sticky error behavior. The selected source and the
count of consumed bits fit in single AVR registers. The explicit loop
avoids integer promotion generating a 16-bit variable right shift on
AVR-GCC 7.3.0. This is a C++ code generation change for the compact AVR25
ASM build with runtime profile selection. The original C reader remains
selectable, including on AVR25.

`readSpeechRice` adds `1 << k` for each unary zero. For zero through seven
zeros this is the same `high << k` the reference computes after the loop.
Compact LSF uses `k=0..2`, so the largest accumulated value is 32, reached
only on escape. The eighth zero immediately selects the raw value of
`width` bits. The terminator, suffix reads, and error checks remain in
their original order. This change uses the same AVR25 build selection as
`readBits`.

## IRQ playback

Both builds use ATtiny88 at 16 MHz and 8 kHz, the SRAM512 profile, LPC2,
MUL16 unroll 2, a 32-byte queue with prefill 24, AVR-GCC 7.3.0 with
`-Os -flto`, and simavr 1.6. The reported mean combines active decoder CPU
time with the full 38-cycle Timer1 IRQ. The playback observer also checks
completion, output spacing and queue underruns. The nine fixed-header ROM
images were rebuilt at the catalog gains and compared byte for byte.

Against `62b943e1`, the `readBits` change saves 30 program bytes in every
image. All 308,339 PWM samples match across the 22 loads and against the
retained native C reference. The mean with IRQ falls by 0.12–0.72 cycles
per sample. Peak stack is 64 bytes, the queue retains at least seven
samples and there are zero underruns. [Per-load measurements](read-bits.json).

Against the `readBits` commit `5a7c7faa`, the compact Rice change saves a
further 32 program bytes and 2 bytes of peak stack. All 308,339 PWM samples
match, with zero underruns and a decrease in mean cycles with IRQ of
0.12–2.36 per sample. Both changes together save 62 bytes, leaving
5,484–5,485 bytes of program Flash. The slowest load averages 1760.15 cycles
per sample with IRQ, with at least eight samples in the queue.
[Per-load measurements](rice.json).

A differential native build enabled the two optimized expressions and used
UBSan to compare against the original methods. For each of the pointer and
indexed ROM modes, 8,241,408 calls per method checked return values, the
cache, input position, callback count, read counters, and sticky errors.
The inputs exercised all valid single-byte cache states, all first refill
bytes, empty and short ROMs, callback failures and Rice escape.

## Reproduce

Run from the repository root in a fresh ignored output directory. Use
`--wsl Ubuntu` on Windows with the toolchain installed there.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-read-bits --target tiny --baseline 62b943e1 --wsl Ubuntu
```

Use the commit that introduces the `readBits` change as the working tree
for this comparison. To measure Rice separately, use the commit introducing
the Rice change and run:

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-compact-rice --target tiny --baseline 5a7c7faa --wsl Ubuntu
```
