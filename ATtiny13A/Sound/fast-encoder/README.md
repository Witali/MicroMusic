# MicroMusic Fast Encoder C — MiniLPC-HQ3 for ATtiny13A

This project makes the **offline encoder** faster. The ATtiny13A firmware still contains the existing compact **406-byte AVR speech decoder**: no C runtime or floating-point code is put onto the chip.

## Changes

- The **exact 8-bit LPC synthesis model** is in `fast_core.c`.
- The **STOI intelligibility estimator and spectrogram error** are calculated in native C using FFTW3, with the Python implementation kept as an independent check.
- Parameter search (`mlpc_optimize`) is native C: F0, gain, excitation profile and eight four-bit lattice coefficients are optimized under the **1024-byte Flash ceiling**.
- For new recordings, C can also estimate initial pitch/LPC parameters with `mlpc_analyze`. It is a simple initializer, not a replacement for iterative quality optimization.
- Variable-length HQ3 bitstream is unchanged. The AVR **does not need legacy compatibility code**.
- Python only handles audio I/O, conversion, validation, AVR assembly and reports.

### Performance, measured on the provided first phrase

The repeated **STOI + spectrogram** computation took about **4.14 ms in Python** versus **0.93 ms in C** on this container (~**4.47×**). This is a steady-state warmed measurement, not an end-to-end wall-clock startup comparison. Initialization of SciPy/NumPy and C compilation take additional time.

Both numeric evaluators agreed to ~1e-6 or better on all three examples; the C decoder's PCM matched the known 8-bit synthesis implementation on all 39,424 samples. Newly built firmware was run in the cycle-counting AVR emulator and matched its C-produced PCM on every sample, with no Timer0 misses.

### Install and build (Linux)

Requirements: Python with `numpy`, `scipy`, `soundfile`, `pystoi`; `cc`/GCC; FFTW3 runtime and development linker; `clang` with AVR target, `llvm-objcopy`, `llvm-objdump`; Node.js for AVR emulation; `ffmpeg` for MP3 input.

```sh
./build_native.sh
python make_demo.py
python test_regression.py --voices demo
python fast_train.py --voice demo --evals 1000
node verify_avr.js outputs demo
python benchmark.py --voice demo --reps 100
```

`build_native.sh` links the installed Linux `libfftw3.so.3`. On a different platform change the last compiler flag to `-lfftw3` and install FFTW3 and a C compiler. Compile the encoder on the **host PC**, not for AVR. `libmicrolpc.so` is for Linux x86_64; do not copy it to ATtiny13A.

### Encode your own recording

Put a 7500 Hz, mono WAV whose length is a multiple of 64 samples in `examples/myclip/original.wav` (or use the converter), then run:

```sh
python convert_audio.py --input myclip.mp3 --output examples/myclip/original.wav
python fast_train.py --voice myclip --from-wav --evals 6000
node verify_avr.js outputs myclip
```

`--from-wav` runs initial LPC/F0 analysis in C. It is a **basic initializer**. More advanced encoding can start with an already optimized bitstream:

```sh
python fast_train.py --voice myclip --input-stream outputs/myclip/speech.hq --evals 12000
```

The script outputs `speech.hq`, `decoded.wav`, `expected_pcm.raw`, `firmware.bin`, `firmware.hex`, `firmware.S` and `result.json`. It uses `decoder_template.S` unless `--asm-template` is specified.

For higher STOI at possible expense of timbre, use `--spec-weight 0`. The default `--spec-weight 0.015` balances STOI and spectral error. In both cases the Python STOI checker rejects an iteration if it loses more than 0.00015 compared to the starting candidate, and generated firmware is rejected if it exceeds 1024 bytes Flash.

### Quality and limitations

- Training scores are calculated on the **same clips used for optimization**; they are not held-out generalization measurements.
- STOI is an objective intelligibility proxy, not an exact measurement of human perceived voice identity.
- The Flash budget includes AVR instructions, speech and the end-of-stream marker; EEPROM is unused.
- The browser and the AVR cycle emulator are software checks, not validation on physical ATtiny13A hardware.
- The original speech excerpts in the **private example bundle** are copyrighted media. Do not publish them or derivatives without permission. Use the separate code-only archive for a public repository.

### Files

`fast_core.c` contains the native optimizer, C synthesis and metrics. `fast_train.py` is the driver/packer and produces HEX. `make_demo.py` synthesizes a fully copyright-free example. `benchmark.py`, `test_regression.py`, `quality_reference.py` and `verify_avr.js` validate the implementation. `convert_audio.py` prepares source recordings.
