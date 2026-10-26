# Lumiere stereo USB upload — October 25, 2026

Result: **PASS** for uploading, reading back, and starting the retained UM88
Lumiere stereo application on the connected MH-ET LIVE ATtiny88 board.

The user pressed RESET while the upload process waited for the USB bootloader.
The sibling MicroNucleus project's original `tools/micronucleus.exe` performed
the application upload. Its Micronucleus+ host library and existing libusb0
driver supplied device identification and readback.

| Property | Observed value |
| --- | --- |
| Device signature | `0x1E9311` (ATtiny88) |
| USB identity | `16D0:0753`, version `0x0208` (Micronucleus+ 2.8) |
| Application capacity | 6844 bytes, 64-byte Flash pages |
| Firmware | `../../songs-micronucleus/lumiere-stereo/synth.hex` |
| Nominal build clock | 16 MHz |
| Firmware size | 4652 bytes |
| Firmware BIN SHA-256 | `501f675bbe40d479d99573600d3b425623efa55c990b87af39189533da957eb3` |
| Patched RESET instruction | `0xCD5F`, branching to the existing loader at `0x1AC0` |
| Audio outputs configured by the firmware | L: D9 / PB1 / OC1A; R: D10 / PB2 / OC1B |

Before writing, the Intel HEX checksums, contiguous addresses, BIN contents,
size limit, and hashes in the retained build and simulation reports were
validated. The device's existing application and all 64 EEPROM bytes were
read twice, compared, and saved locally under the ignored
`build/flash-lumiere-20261025/` directory.

The official uploader returned exit code 0. After uploading without `--run`,
all 6844 application bytes were read back and matched the expected firmware,
bootloader-patched RESET, and erased padding. All 64 EEPROM bytes matched the
pre-upload backup. The application start request was then accepted. No fuse,
EEPROM write, or bootloader replacement operation was issued.

The [uploader log](upload.log) and [structured result](result.json) record the
USB operations. Raw memory backups remain local and are not committed.

This verifies storage and acceptance of the start command. Audible playback,
physical PWM timing, real-device buffer underruns, and persistence after a
subsequent power cycle have not been observed in this test. The retained
simulation audit remains a separate result; its `hardwareTested` field is
unchanged. Connect the outputs through the existing audio filter and amplifier
with a common GND to listen.
