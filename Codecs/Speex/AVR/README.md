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

The upstream port is under development. Successful host tests or AVR object
compilation alone do not establish a working real-time ATmega328P player.
