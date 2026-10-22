# MicroMusic MiniLPC-HQ3 — compact + faster mul_q4

ATtiny13A 9.6 MHz, 1 KB Flash, 37.5 kHz PWM carrier, 7.5 kHz PCM output. Eight-stage LPC synthesis. Single new-format VBR stream; no old-format support.

## Verified change

`mul_q4` now uses r21 directly as the multiplicand and r16 directly as the high accumulator. The intermediate copies of r21 and the high result were eliminated. This is not a new multiplication algorithm: it still repeats signed 16-bit addition |k| times, so for the small coefficients in MiniLPC-HQ3 it is faster and shorter than a 4-iteration shift-and-add tested in `benchmark.json`.

* Old `mul_q4`: 42 bytes.
* New `mul_q4`: **38 bytes**.
* Entire decoding code region: 410 -> **406 bytes**.
* On exhaustive 4096 (256 sample x 16 coefficient) operand pairs, all output byte values agree exactly.
* Mean subroutine cycles across all operand pairs: 40.25 -> **38.3125 cycles**, including RET.
* On all 3 actual voice streams: 39424/39424 PWM sample values identical, no missed Timer0 overflows, no ISR issues. STOI and timbre unchanged.

| Phrase | Old Flash bytes | New Flash bytes | Number samples |
| --- | ---: | ---: | ---: |
| Chego tebe nuzhno | 951 | **947** | 9216 |
| Chto zh ty ne otvechaesh | 882 | **878** | 7936 |
| Sova, otkryvay | 1011 | **1007** | 22272 |

## How to reproduce

Requires `clang` with AVR target, `llvm-objcopy`, `llvm-objdump`, Node.js, Python 3.

```bash
python3 build_and_verify.py
```

`bench_mul.js` compares the old/new actual AVR routines for all 4096 sample/coefficient inputs and measures AVR cycles. `verify_samples.js` runs the three binaries in the cycle-counting AVR emulator and checks every PCM output byte. `index.html` is the self-contained browser A/B player; its AVR-verify button executes the new HEX from start.

The original signed-8-bit `NEG` behavior for x=-128 is preserved exactly, including the existing corner-case semantics. A mathematically different correction should be evaluated separately; this version is bit-compatible with HQ3.

The comparison for music quality is only a software emulation; physical ATtiny13A hardware testing has not been performed. Original movie audio and voice parameters are included for personal experimentation only, not for redistribution without appropriate rights.
