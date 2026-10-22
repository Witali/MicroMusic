# MicroMusic · 3 × 3 ATtiny13A Codec Lab

Nine ATtiny13A firmware variants: Keyframe LPC-8, Adaptive LPC-8 and experimental MiniLPC-8 Full for three speech phrases.

All nine firmwares are checked to fit in 1024 bytes Flash and were decoded by `mini_emulator.js` with the Timer0 interrupt model, 9.6 MHz CPU and 7.5 kHz PCM output. All tests completed without missed Timer0 overflows or audio underruns. Four earlier short-phrase firmwares were independently re-emulated and matched their original stored unsigned PCM byte-for-byte.

Open `index.html` offline; it embeds the nine verified firmware images and their PCM output. The **Verify HEX** button re-executes the actual instruction streams in the browser and compares every sample to the stored reference result.

`firmware/<phrase>/<codec>/` contains assembly, HEX, BIN, speech data and AVR-generated PCM. `build_mini.py` and `build_matrix.py` use Clang AVR and llvm-objcopy in the same folder as source datasets; see scripts for required base paths. Other prior training scripts are not included, so the repository is a reproducible firmware/demo package, not a standalone fresh-training pipeline.

The original speech samples are short excerpts supplied for private research, not cleared for public redistribution. The private ZIP includes these audio samples and packed speech streams for individual experimentation. For a public repository remove recordings and their encoded derivatives unless permission is obtained.

Hardware pin PB1 / OC0B -> RC low-pass filter -> amplifier (do not drive the speaker directly). MCU must run at 9.6 MHz. Fuses: adjust CKDIV8/clock only after verifying chip and programmer settings; do not disable RESET or SPIEN. Actual hardware playback has not been tested.
