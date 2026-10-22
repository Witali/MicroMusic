# Handoff: Dual CRC-16 / Intel 8080, 22 October 2026

The user is building a ROM-only (no RAM, no writable stack) Intel 8080 hardware tester (historically 3.5 MHz clock). The program checks all 65536 bytes, including its code, with CRC polynomials 0x0025 and 0x0047. The four final bytes encode the product CRC polynomial 0x1006209BB, so the two independent 16-bit residues become zero. This is intentionally not a standard CRC32C algorithm.

This directory contains independently tested v5 optimization trials:
- **Best same-size improvement:** 75 bytes, 18,882,115 T across the full 64 KiB, 288.118 T/byte. Uses ADD A where A already mirrors the pre-shift HL low byte, saving one T for each byte in pass two.
- **Best new speed/size compromise:** 82 bytes, 18,292,291 T, 279.118 T/byte. Replaces CRC47 DAD shifts by 8-bit rotations and parity folding. Compared to the old 120-byte two-byte-unrolled variant it is 38 bytes shorter with exactly the same measured T-state count.
- **RESET-only:** 74/81 bytes by dropping DI (requires genuine hardware RESET; no jump from running code).
- The old smaller 72/73-byte variants are preserved; they run at 307 T/byte.

Research future directions: (1) Explore instruction-sequence superoptimization while preserving both 16-bit polynomials and zero-result footer. (2) Compare alternate 8080 register allocations, especially avoiding repeated MVI H,0; keep all memory strictly read-only. (3) Explore controlled nibble tables as *optional separate* size/speed tradeoff, but baseline has no tables. (4) Carefully verify any replacement of 16-bit shift with 8-bit ADD/RLC/RAR includes every carry bit into the high CRC byte. (5) Keep accurate emulated T-state benchmarks and full-ROM mutation tests. Physical hardware not yet verified.

Run tests per README_START_HERE_RU.md. The independent C 8080 executor supports the actual subset of opcodes used, and independently recomputes CRCs. The test firmware uses DI/EI+HLT to indicate result via INTE.
