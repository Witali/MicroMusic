# LPX v9 rates with fixed hardware divisors

Applicable CPUs: ATtiny88 / AVR25 and ATmega328/328P / AVR5 at 16 MHz,
GNU AVR ABI, AVR-GCC 7.3.0. Device registers come from the compiler-selected
vendor headers. Arithmetic still requires explicit `LPX4_ENABLE_ASM=1`;
zero selects the equivalent C backend on the same CPU. This is original
project clock-selection and validation code.

The universal v9 header stores nominal sampling rate. Each AVR player is
compiled for exactly one of 8000, 12000 or 16000 Hz, with 8000 Hz the default.
Set `LPX4_SAMPLE_RATE` consistently for every translation unit, independently
of C/ASM arithmetic selection. The shared Python builder's `sample_rate`
argument and CLI `--sample-rate` option do this for the complete build.
The Nano wrapper accepts the same `sample_rate` argument.

The timer divisor is a compile-time constant. `begin()` checks the complete
16-bit file rate against that setting; the builder rejects a mismatched file
or mixed-rate segment list before compilation. A setting does not resample
or retag audio. Other stream parameters and the payload remain universal.
There is no fractional phase state or extra SRAM.

The portable PC reference defaults to `LPX4_SAMPLE_RATE=0`, accepting all
three v9 rates, and can explicitly select one rate as well. On AVR the
library default is 8000; zero remains available for a library-only reader,
but the player requires one concrete rate. Legacy formats retain their
8 kHz contract. `LPX4_EXTENDED_SAMPLE_RATES=0` still limits the C/library
compatibility path to 8 kHz; the firmware builder uses `sample_rate` instead.
No payload format change or additional field is needed. The former automatic
player is preserved at `codex/lpx-auto-sample-rate` (`66e3d934`).

| Nominal rate | Nano D3/OC2B, Timer1 /1 | Tiny OC1A, Timer0 /8 |
| --- | --- | --- |
| 8000 Hz | 2000 CPU cycles, 8000 Hz | 2000 cycles, 8000 Hz |
| 12000 Hz | 1333 cycles, 12003.000750 Hz | 1336 cycles, 11976.047904 Hz |
| 16000 Hz | 1000 cycles, 16000 Hz | 1000 cycles, 16000 Hz |

The user selected the nearest fixed divider for compactness. The nominal
12 kHz error is +0.0250% on Nano and −0.1996% on Tiny. Metadata reports
nominal and actual rates separately. The reserved-register ISR remains
35 cycles on Tiny and 35..36 on Nano, including the linked vector,
interrupt entry and RETI in simavr 1.6. Each case matches its predecessor.
These are simulator measurements with active interrupts, not physical-board
measurements. A new recording/rate is admitted only by complete IRQ playback
with exact PWM and zero underruns; an average below the deadline is insufficient.

The filled-queue body is 29 cycles on both chips. GNU linker relaxation uses
a two-cycle RJMP vector when it can reach the handler; larger Nano images
retain a three-cycle JMP vector. With four entry cycles this explains 35/36
without a change to the ISR body. All 132 final ELF vectors were inspected;
none changed vector cost relative to its matched task-start image.

## Encode source audio at the selected rate

From the repository root with the existing scientific Python dependencies:

```sh
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/speech_v9_audio.py encode input.wav build/example --profile 6 --sample-rate 16000
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/speech_v9_audio.py decode build/example/audio.lpx build/example/decoded-again.wav
```

On Windows, add `--wsl Ubuntu` to use its C++ compiler. `--cxx` or `CXX`
selects another compiler command. The default uses the existing native
batch C backend. Source audio is resampled before the unchanged P4/P6 search;
the final rate-bearing v9 PCM16/PWM is independently checked with C. Decode
writes WAV at the validated stored rate. Its nominal rate differs slightly
from fixed-divider physical 12 kHz playback as listed above.

Packet geometry remains 320 samples and pitch lags remain 18..145 samples.
Packets last 40/26.667/20 ms at 8/12/16 kHz. Higher sampling rates increase
actual bitrate and change the physical pitch range; these are not new
perceptually tuned quality presets. Reports include file/payload bitrate,
packet duration and source rate. The original 8 kHz payload/search stays exact.

## Reproduce complete playback

For example, compile a Tiny player for an already encoded 12 kHz stream:

```sh
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/build_attiny88_player.py build/example/audio.lpx build/player-12k --enable-asm --asm-isr --sample-rate 12000
```

Omit `--sample-rate` for 8 kHz. The verifier has the same option. Selecting
12/16 kHz does not by itself establish real-time support on the selected chip.

```sh
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_avr_player22.py build/lpx-three-rates --rates 8000 12000 16000 --jobs 3
```

Add `--wsl Ubuntu` on Windows. This regenerates the public 22 inputs without
scientific Python packages, enforces the 3072-byte single-stream Nano limit,
and keeps failed Tiny high-rate cases explicitly unadmitted. Higher-rate
matrix inputs change only the header rate and are labelled timing probes.
The separate `test_sample_rates.py` tests encode real resampled source audio,
preserve original 8 kHz P4/P6 output, validate compatibility/error/playlist
contracts and check rate-aware WAV decoding.

The historical three-rate measurements above describe the automatic player.
The [compile-time selection measurements](../../Codecs/LPX/research/avr-fixed-rate-2026-11-18/README.md)
record the smaller current images and matched IRQ checks separately.
