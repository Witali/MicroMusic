# Manufacturer device definitions

Unmodified files from Microchip ATtiny_DFP **3.4.278**:

- Pack: https://packs.download.microchip.com/Microchip.ATtiny_DFP.3.4.278.atpack
- Pack SHA-256: `41f09d5825abaa764c9000f4488f8ba3fab152afe6229b359de4a5efe9a21eda`
- `include/avr/iotn88.h`: register definitions selected through the toolchain's `<avr/io.h>`.
- `atdf/ATtiny88.atdf`: original device, register and package descriptions.
- `LICENSE.txt`: pack license; the header also retains its own copyright/license notice.

The builder adds this pack's `include/` before the older toolchain device
headers. Compiler CPU, pointer and memory-model defines come from
`-mmcu=attiny88`. Project-specific clock and audio configuration lives in
`../clock.h` and `../platform.c`, outside these vendor files.

Manufacturer repository: https://packs.download.microchip.com/
Device datasheet: https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf
