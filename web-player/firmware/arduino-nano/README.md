# Arduino Nano / ATmega328P — LPX speech

The shared AVR page is `../../?collection=hq4&device=atmega328p`. The same
microcontroller selector, player, signal panel and catalog serve ATtiny13A,
ATtiny88 and Nano, including the additional combined dialogue.

Eight images contain the four already-public speech phrases, in compact and
higher-quality LPX profiles. The common order is defined by
`web-player/speech-examples.json`. They play once after reset; reset starts again.

All four recordings also offer Speex NB 2.15, WB 3.95 and WB 9.8 kbit/s in the
same codec/quality selector. The twelve Speex images, exact PWM previews and
active-IRQ receipts are in `../../firmware-speex-atmega328p.json`.

An additional [combined dialogue](../../?collection=hq4&device=atmega328p&firmware=lpx-nano-dialogue-quality) plays the four
normalized phrases in conversation order, with 0.5 / 1.5 / 0.5-second pauses.
Its [recipe and validation](../../../ATmega328/Sound/lpx-dialogue/README.md)
describe the separate 10.240 KiB image, 756 B static SRAM and exact PWM preview.
Its selector also offers three complete Speex dialogue images (15.531,
25.066 and 29.500 KiB). All fit the 30 KiB application budget and pass complete
active-IRQ playback. Measured oversized profiles remain disabled in the menu;
their HEX files are not published. Receipts are in
`../../firmware-speex-dialogue-atmega328p.json`.

EEPROM is unused. These are complete application HEX files without a
bootloader; they fit within the classic Nano's 30 KiB application budget.
Keep the existing board bootloader and fuse settings when uploading.

The original bread phrase retains these sizes; the complete eight-image
inventory and compression recipes are in [the shared documentation](../../../docs/speech-assets.md).

| Bread profile | LPX stream | Program | Full Flash | Static SRAM |
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
it does not emulate Nano. All eight complete HEX files were independently run in
simavr 1.6 with Timer1 interrupts active: every declared sample and output tick,
zero underruns, exact equality to the displayed WAV. Observed sample intervals
were 1,995–2,005 CPU cycles, maximum complete interrupt 76 cycles, minimum observed stack
margin 1,229 bytes across all eight images. The observer charges the four-cycle
AVRe hardware entry omitted by simavr 1.6 and finishes timing after RETI
retires; the previous 68-cycle figure omitted these eight cycles. All eight
images were rebuilt with calibrated producer-side output gain. Five already
full-range images retain unity and their exact bytes; three quiet images use
more of the PWM range. Their complete sizes are 4.926–6.365 KiB.
The codec state and ISR are unchanged; the complete waveform proves no added
saturation. [Arithmetic, costs and verification](../../../docs/avr-asm-cookbook/pwm-output-level.md).
These results cover the retained images; no physical-board
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
