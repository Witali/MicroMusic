# Speex for AVR

Target: ATmega328P, 16 MHz, 2 KiB SRAM, 32 KiB Flash. Initial stream profile:
Speex narrowband submode 3, mono 8 kHz, 160 samples / 20-byte packet / 20 ms.

The active implementation adapts **Xiph Speex 1.2.1 fixed point**. The previous
custom R4 decoder is retained separately under `reference/R4` for comparisons.
Its source and test streams are unchanged from the supplied handoff archive.
R4 timing estimates do not describe the upstream port.

`handoff/upstream` contains the previous agent's patch candidates and tests,
copied without modification. The accompanying historical notes describe the
state before this repository import; they are context, not current test results.
`handoff/import-manifest.json` records the source archive and each imported
file's SHA-256. The remaining historical stages and generated files stay in
the external handoff ZIP.

The original 1.2.1 C sources and headers are retained under `vendor/speex-1.2.1`,
including their license and hashes. Builds use disposable copies under `build/`;
the vendor and R4 trees are checked against their hashes before every build.

Run from the repository root with Python 3 and Clang on PATH:

```sh
python Codecs/Speex/AVR/tests/verify_pcm.py --cc clang
```

This builds the unmodified fixed-point decoder, compact LSP variant, and compact
LSP + tight excitation variant, and compares complete signed 16-bit PCM on all
11 saved streams (1,058 frames / 169,280 samples). All three agree byte for byte
with enhancement and highpass disabled. See `reports/host-pcm.json` for the
retained oracle hashes. The test is for this restricted, lossless mode-3 profile;
it does not validate packet loss concealment or other Speex modes.

The upstream port is under development. Successful host tests or AVR object
compilation alone do not establish a working real-time ATmega328P player.

The static `src/speex_avr.h` API adapts the original decoder for the restricted
profile. It uses a 400-byte scratch arena, a tested 312-sample excitation
history, and explicit PROGMEM codebook reads. It rejects other packet sizes and
mode headers before changing state. Enhancement, highpass and packet loss
concealment are excluded; no heap allocator is linked.

Build the linked AVR GCC validation firmware and execute it on AVR8js:

```sh
python Codecs/Speex/AVR/tools/build.py --avr-gcc /path/to/avr-gcc
cd Codecs/Speex/AVR
npm ci --ignore-scripts
npm run test:avr
```

The initial linked port uses 10,312 bytes Flash, 1,671 bytes static SRAM including
the packet/PCM test mailbox. All 1,058 frames agree with the unmodified upstream
oracle when executing AVR instructions. Peak C stack is 238 bytes, leaving 139
bytes free in this harness. Maximum frame time is 547,940 cycles, exceeding the
320,000-cycle real-time budget. These are ISA simulation results without ISR
or peripheral I/O, not measurements from a physical board. The baseline report
is retained in `reports/avr-initial.json`.

The optimized decoder retains exact upstream arithmetic with symmetric 48-byte
LSP polynomials, fused innovation scaling, a bounded field reader, and AVR
assembly for LPC state updates and pitch MACs. AVR GCC `-O3` with controlled
inlining gives **14,712 B Flash / 1,535 B static SRAM / 221 B peak C stack**.
All 1,058 AVR frames remain exact, with a worst observed **295,334 cycles**
(18.46 ms at 16 MHz) and **292 B free SRAM**. See `reports/avr-optimized.json`.
This decoder-only timing excludes interrupts and is a corpus maximum, not a
proof over every possible packet. Host primitive tests also compare 240,000
complete LSP conversions to original upstream and exhaust 3,670,016 bit fields.
