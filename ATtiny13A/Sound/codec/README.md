# MicroMusic MiniLPC-HQ3 — verified export

A complete **export of the current tested artifacts**, not a complete automatic training pipeline.

- `index.html`: standalone player with embedded HEX, reference waveform and AVR interpreter.
- `report.csv`: measured values from the last run.
- `<clip>/firmware.S`, `firmware.hex`, `firmware.bin`: original assembler source, Intel HEX and binary extracted from the standalone player.
- `<clip>/speech.hq`: encoded parameters extracted from firmware at offset 422.
- `<clip>/hq.wav`: emulator-produced output; other WAVs are reference/older comparisons.
- `convert_audio.py`: audio-preparation script retained from HQ2. It does **not** retrain HQ3 by itself.
- `build_and_verify.py`: reproduce firmware binary with clang/llvm-objcopy and verify SHA-256 against the archived HEX.

Current verified values: **chego 0.8948378, 963 B**; **otvechaesh 0.8161853, 894 B**; **vinni 0.8551781, 1023 B**. The decoder region is 422 bytes (including vector table/init), speech data respectively 540/471/600 bytes, plus one marker. 7.5 kHz speech PWM on ATtiny13A 9.6 MHz. According to last test report 0 model/AVR differences, Timer0 misses, late audio samples; not tested on physical chip.

To verify (requires AVR-target clang and llvm-objcopy):

```bash
python build_and_verify.py
```

**Limitations**: HQ3 fitting scripts and their saved model state are not present in this export; additional training cannot be reproduced from this ZIP. The pre-existing HQ2 optimizer sources are preserved separately in prior HQ2 project archives, but do not directly reproduce HQ3. The original cartoon recordings/encoded voice are copyrighted; this ZIP is intended for private testing only.
