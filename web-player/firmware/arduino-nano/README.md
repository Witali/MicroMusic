# Arduino Nano / ATmega328P — LPX speech

The shared AVR page is `../../?collection=hq4&device=atmega328p`. The same
microcontroller selector, player, signal panel and catalog serve ATtiny13A,
ATtiny88 and Nano; there is no separate Nano HTML layout.

Both images contain the already-public 2.4-second phrase from
`web-player/audio/lpx-bread/`. They play once after reset; reset starts again.
EEPROM is unused. These are complete application HEX files without a
bootloader; they fit within the classic Nano's 30,720-byte application budget.
Keep the existing board bootloader and fuse settings when uploading.

| Profile | LPX stream | Program | Full Flash | Static SRAM |
| --- | ---: | ---: | ---: | ---: |
| Compact | 1,008 B | 4,574 B | 5,582 B | 756 B |
| Quality | 1,899 B | 4,573 B | 6,472 B | 756 B |

Target: classic Nano with ATmega328P at 16 MHz. Timer2 fast PWM uses
**D3 / PD3 / OC2B**, 62.5 kHz; Timer1 requests 8,000 samples/second.
Connect the PWM output through a suitable RC filter to an amplifier input,
with a shared ground. The [official Nano pinout](https://docs.arduino.cc/resources/pinouts/A000005-full-pinout.pdf)
documents D3/PD3. Definitions come from the existing AVR-LibC headers in
the project's pinned AVR-GCC 7.3.0 toolchain, without copied register addresses.

The browser plays the public native-decoder WAV and displays its waveform;
it does not emulate Nano. Both complete HEX files were independently run in
simavr 1.6 with Timer1 interrupts active: all 19,200 samples and output ticks,
zero underruns, exact equality to the displayed WAV. Observed sample intervals
were 1,997–2,003 CPU cycles, maximum ISR 68 cycles, minimum observed stack
margin 1,231 bytes. These results cover these two images; no physical-board
or analog-output test is claimed. Path-free receipts and SHA-256 hashes are
in `../../firmware-atmega328p.json`; private build logs remain in ignored `build/`.

Rebuild from the repository root, using installed project audio dependencies:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/build_release_observer.py build/nano-lpx/observer --include /path/to/native/usr/include/simavr --lib /path/to/native/usr/lib/x86_64-linux-gnu
python tools/build-nano-speech-catalog.py --avr-bin /path/to/avr/bin --observer build/nano-lpx/observer/sim_player --lib /path/to/native/usr/lib/x86_64-linux-gnu --enable-asm
```

On Windows add `--wsl Ubuntu` to both commands. Assembly is explicitly enabled
for these releases; omit `--enable-asm` to select the equivalent C backend,
including on AVR. The build tool requires the resulting complete image to
pass the same output/timing checks before replacing the release files.
Registers and hardware setup remain separate from arithmetic backend selection.

Codec and player sources are retained in `Codecs/LPX/01_ACTIVE_Q0_CODEC/`;
the manifest pins their hashes after normalizing text line endings to LF.
HEX checksums preserve the exact file bytes. No new codec optimization or format was
introduced for this page.
