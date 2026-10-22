# MiniLPC HQ3 — Code size experiment (lossless)

Target: ATtiny13A, Flash 1024 bytes, 9.6 MHz CPU, 37.5 kHz PWM, 7.5 kHz samples.

The *actual* HQ3 baseline code region was 422 bytes (includes AVR vectors/setup), not 412 bytes. The revised decoder code region is **410 bytes**, a reduction of **12 bytes** with identical PCM output.

Changes:
1. Output `READY` flag is set by `INC r8`, instead of `LDI r16,1` + `MOV r8,r16` (2 bytes saved).
2. Remove redundant `CLR r29` in the per-sample filter setup (2 bytes saved); YH is initialized in reset and stays zero.
3. Drop initial `LDI r16,1` and `MOV r2,r16` (4 bytes saved), because `read_frame` assigns `r2` before playback.
4. Replace eight ASR/ROR operations in the signed 16-to-8 bit `>>4` calculation with `MOV/SWAP/ANDI/SWAP/ANDI/OR` (4 bytes saved).

Verified with instruction-and-cycle AVR emulator against the original HQ3 output for all 39424 audio samples:
- **0 PCM sample mismatches**;
- **0 Timer0 missed overflows**;
- exactly the **same PWM update/IRQ counts** for each phrase (46080/39680/111360);
- max ISR duration 28 cycles (unchanged).

| Phrase | Original Flash | Optimized Flash | Code | Available Flash after optimization |
|---|---:|---:|---:|---:|
| Chego tebe nuzhno | 963 | 951 | 410 | 73 |
| Chto zh ty ne otvechaesh | 894 | 882 | 410 | 142 |
| Sova, otkryvay! Medved prishel | 1023 | 1011 | 410 | 13 |

This modification is *lossless* compared with HQ3, so previously measured STOI metrics **do not change**: 0.89484, 0.81619, 0.85518. It is not a new speech-quality improvement.

Rebuild and run verification (requires clang with AVR target, llvm-objcopy, Node.js):
```
python3 build_and_verify.py
```
`verify_samples.js` includes the minimal cycle-counting AVR interpreter; baseline binaries are included to allow byte-for-byte PCM comparison.

`firmware.hex` includes encoded voices derived from media clips: keep these demonstration files private unless you have the necessary redistribution rights. Source itself may be reused for your own recordings and synthetic voices.
