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
