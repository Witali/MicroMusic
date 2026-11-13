# ATtiny88 LPX bit reader

`readBits` shares one cache writeback and one byte-wide shift loop between
the cached and refill paths. Each path still masks its own source before
assembling the result. A refill calls `readByte` at the same point, with
the same bounds and sticky error behavior. The selected source and the
count of consumed bits fit in single AVR registers. The explicit loop
avoids integer promotion generating a 16-bit variable right shift on
AVR-GCC 7.3.0. This is a C++ code generation change for the compact AVR25
ASM build with runtime profile selection. The original C reader remains
selectable, including on AVR25.

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

## Reproduce

Run from the repository root in a fresh ignored output directory. Use
`--wsl Ubuntu` on Windows with the toolchain installed there.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/tiny-read-bits --target tiny --baseline 62b943e1 --wsl Ubuntu
```

Use the commit that introduces the `readBits` change as the working tree
for this comparison.
