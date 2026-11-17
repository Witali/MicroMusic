# LPX v9 rates with fixed hardware divisors

Applicable CPUs: ATtiny88 / AVR25 and ATmega328/328P / AVR5 at 16 MHz,
GNU AVR ABI, AVR-GCC 7.3.0. Device registers come from the compiler-selected
vendor headers. Arithmetic still requires explicit `LPX4_ENABLE_ASM=1`;
zero selects the equivalent C backend on the same CPU. This is original
project clock-selection and validation code.

The universal v9 header stores nominal sampling rate. The C reference and
shared AVR player accept 8000, 12000 and 16000 Hz. Legacy formats retain
their 8 kHz contract. No payload format change or additional field is needed.
`LPX4_EXTENDED_SAMPLE_RATES=0` selects an 8 kHz-only compatibility decoder;
the player must also use `LPX25_HEADER_SAMPLE_RATE=0`. The Python builder's
`extended_sample_rates=False` selects both compatibility settings.

Validate the complete 16-bit rate in `begin()`. Only then use its high byte
to choose one of three timer divisors at startup. There is no rate-dependent
per-sample branch, fractional phase state or extra SRAM. One continuous FIFO
has one clock: mixed-rate stream lists are rejected before compilation.

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
