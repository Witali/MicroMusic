# V9 Long host-only extension: default AVR objects remain exact

The Web/PC converter now writes one continuous stream, using uint32 header
lengths when needed. `LPX4_ENABLE_WIDE_V9` defaults to zero and is rejected on
AVR. See the [format/API specification](../../01_ACTIVE_Q0_CODEC/LPX9_LONG_FORMAT.md).

`source-transition.json` binds the original 8a2d2c7d core/header to the extended
source. The reproducible check compares entire compiled object bytes for
ATtiny88 (AVR25, no MUL) and ATmega328P (AVR5), standard and SRAM512 memory,
C and explicit ASM, and 8/12/16 kHz: all 24 before/after pairs are identical.
Compiler: AVR-GCC 7.3.0; flags are retained in the report. The toolchain's pinned
provenance is in `tools/toolchains-windows-x64.json`.

```powershell
node web-player/scripts/verify-lpx-long-defaults.mjs --avr-root C:/path/to/avr-7.3.0
```

This is default object equivalence, not a fresh linked-firmware or IRQ run.
Historical admission reports stay historical; no new AVR format, rate or timing
support is claimed. Web tests separately validate V9 Long with native C and
WASM, strict EOF, preserved short-file bytes and continuous old-limit crossings.
