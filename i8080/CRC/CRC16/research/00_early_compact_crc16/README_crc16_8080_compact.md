# Intel 8080: compact CRC-16 POST (64-KiB ROM, no RAM)

This package has three versions of the self-test. All start at address 0000h,
read every one of the 65536 ROM bytes, and report success through the INTE
signal (`EI; HLT`) and failure by directly executing `HLT` (with INTE still
disabled after hardware RESET).

| File | Size | Polynomial | Characterization |
|------|------|------------|------------------|
| crc16_8080_33bytes.asm | 33 bytes | 0x002D | irreducible, primitive (period 65535), recommended |
| crc16_8080_32bytes.asm | 32 bytes | 0x0065 | reducible; uses `DAA` as 1-byte mask transform |
| crc16_8080_31bytes.asm | 31 bytes | 0x00FF | reducible; no explicit mask instruction |

- Preset = 0x0000, MSB-first input, no reflection, no final XOR.
- ROM bytes at FFFEh and FFFFh store the computed CRC in high-byte, low-byte order.
- All bytes including those two are checked; a correct ROM produces residue 0.
- Unlike an earlier 36-/38-byte version, this program does **not** use preset FFFFh.
- The polynomials are deliberately nonstandard. Do not confuse any with CRC-16/CCITT (0x1021).
- INTE's failure state relies on hardware RESET disabling interrupts; if jumping to the checker
  from an already-running system, execute DI first (adds 1 byte).
- No method can verify all physical 64 KiB if address line A15 isn't wired to ROM.
- Bit flips in the executable code itself may prevent the checker from executing correctly:
  the CRC self-check is not a substitute for hardware or a protected bootloader.

To create a full image from the assembled code:

```sh
python patch_crc16_8080_compact.py crc16_8080_33bytes.bin output_64k.bin --poly 0x002D
```

The three `*.bin` files are exactly the short machine programs. `*_demo_64k.bin`
are full 65536-byte example images, filled with 0xFF and ending in valid checksums.

Tested with a lightweight 8080-instruction model: every variant reaches HLT with
INTE=1 when ROM CRC residue is zero, and INTE=0 after a single test bit is toggled.
