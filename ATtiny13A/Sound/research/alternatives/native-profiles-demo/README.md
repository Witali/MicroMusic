# MicroMusic MiniLPC8 — code-only new-format demonstration

This archive contains the compact **364-byte new-only decoder** and **synthetic test sound**. It does not contain copyrighted speech or LPX3 samples.

Run `python3 build_demo.py` to generate the HEX with `clang` AVR and `llvm-objcopy`.

The new frame format is exactly six bytes: `[period, (profile << 4) | gain, k0_k1, k2_k3, k4_k5, k6_k7]`; gain in 0..15, profile 0..3 and signed LPC nibble = unsigned nibble minus 8.

Only this new format is supported in the firmware; old decoders are not embedded. The synthetic sample is not human speech.
