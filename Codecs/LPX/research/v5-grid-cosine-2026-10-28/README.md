# Exact v5 cosine grid, 2026-10-28

V5-only centered 5/6-bit LSFs and polynomial anchor segments 1/2 reach only even
nodes of the original 257-node Q13 cosine table. Fractional interpolation is
zero at every reachable conversion. The decoder now reads one of 65 exact
half-wave even nodes and reflects the sign. Common-format builds and segments 4
retain the original full-domain helper; original model/oracle tables are intact.
No bitstream, coefficient, PCM/PWM or arithmetic-backend contract changes.

ATmega328P/enhanced AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0, 16 MHz/8 kHz,
queue 512/prefill 384, segments 2, explicit ASM, unroll 1/tuning 0,
`-Os -flto -mcall-prologues -mrelax`. Hardware access remains AVR-LibC
`pgm_read_word`, independent of the arithmetic backend. Default C remains
selectable on AVR; this change introduces no handwritten assembly.

The bounded screen compared the same current selected audio in four complete
linked images: a 64000-sample single-segment clip and a 281632-sample five-segment
clip, profiles 4/6. The 80-byte checkpoint/unsigned-difference table saves 34 B
Flash; the selected 130-byte direct table saves 56 B. The smaller table loses
because its reconstruction routine costs more code. Its exact rejected patch
is retained as a measured alternative, not production code.

Six baseline/selected pairs add a 64060-sample two-segment partial-tail clip.
Full Flash falls by 56 B in every pair; static SRAM stays 1085 B (single) or 1086 B
(chains). Available decode wall-cycle totals improve 2.286–2.521%. These
statistics cover 64000 samples per image; the complete longer PWM output is
still checked. Observed after-ready stack margin falls by one byte,
887→886 (single) or 882→881 (chains), without claiming worst-case/startup stack.
All 12 normal images and four selected +100 IRQ-cycle controls produce exact
complete model PWM with zero underruns/errors. Final formatted production
sources produce byte-identical ELF/binary to all six tested selected snapshots.

Validation preserves the generic 4096-cosine-input regression contract and the
existing 34816-arbitrary-anchor frozen LPC fingerprint. Eighteen baseline/diff/
direct oracle builds cover common/v5-only layouts and segments 1/2/4. Each
exhausts all 5120 profile-specific scalar previous/current pairs at its allowed
anchors and hashes 4096 legal ten-LSF vector pairs. Twenty-three focused native
tests pass, including compact-only parser, partial tails, malformed inputs,
restart/copy and selectable reference state paths. A separate table check uses
`q0_model.table`, asserts 257 original entries and verifies the 65 retained values.

See[measurements.json](measurements.json) for exact counts, flags, hashes and
per-image data. This is simulator admission for the measured inputs/settings;
physical-board output and universal performance are not established. All
techniques/code are original project work derived from the retained exact table.

Per-recording ELF/binary/PWM fingerprints stay in ignored local receipts; the public measurements retain source/toolchain fingerprints and anonymous numeric evidence.
