# Exact wideband QMF acceleration

The compact Q7/16-tap filter and its PCM remain unchanged. The ASM input
transform biases signed16 to unsigned16 and rotates the exact 17th carry/
borrow bit into each half-result. Adjacent inputs share the bias constant.
The first tap initializes each signed24 accumulator instead of clearing it;
saved history is consumed before MUL overwrites r0:r1. No per-tap subroutine,
additional state, stack slot, table or platform setting is introduced.

The portable C implementation, explicit ASM opt-in, CPU checks, public API
and hardware memory-access selection stay unchanged. C performance tests
are excluded as requested. Existing C/reference evidence remains historical;
only ASM is newly executed. The source-bound admission checks that every
other runtime source, including the C fallback, matches the baseline.

## Measured exact improvement, 2026-10-30

ATmega328P at 16 MHz, AVR GCC 7.3.0, existing mixed function options with
`-Os -flto -mcall-prologues -mrelax`, avr8js 0.21.1. These decoder-only
measurements exclude output/ISR/transport, and are not a worst-case proof.

| ASM profile | Mean frame cycles, before -> after | Max, before -> after | Flash, before -> after |
| --- | ---: | ---: | ---: |
| WB9.8 | 238611.592 -> 236051.592 | 245412 -> 242852 | 17072 -> 17008 B |
| WB12.8 | 241085.577 -> 238525.577 | 246660 -> 244100 | 19870 -> 19806 B |

Every stream's minimum, maximum and mean drops exactly 2560 cycles/frame.
Whole-corpus mean cost falls 1.073% / 1.062%; CPU occupancy drops 0.8 percentage
points in either mode. The same 16 natural voices average 73.57% / 74.31%
CPU. QMF itself saves about 4.88%; all other self-symbol cycle totals remain
unchanged. Static SRAM stays 1279 / 1287 B, peak bare decoder stack 180 / 192 B.

Each new decoder checks 10563 sequential frames plus 17 reset-first frames
against its preceding independent compact-profile oracle: zero PCM changes.
The QMF unit test checks 2244 blocks / 179520 output words, exact mirrored
state, guards, alias and callee-saved/r1 at every external return.
`reports/wb-qmf-after-*.json`, `wb-qmf-profile-after-*.json` and
`wb-qmf-unit-after.json` retain the results beside the fresh baseline reports.
Continuous PWM/IRQ admission is reported separately below when completed.

## Reproduce

Use AVR GCC 7.3.0, Node with avr8js 0.21.1 and Python 3.12+. Run from the
repository/worktree root; supply paths to the installed tools. Existing
corpora and independent PCM oracles are those hash-bound by
`reports/group4-admission.json`: `build/wb-corpus` for WB9.8 and
`build/higher-corpus/wb128` for WB12.8. No recordings are embedded in reports.

```sh
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --kernels --out Codecs/Speex/AVR/build/wb-speed-kernels-final
node Codecs/Speex/AVR/tests/verify_wb_kernels.mjs --firmware Codecs/Speex/AVR/build/wb-speed-kernels-final --asm-only --qmf-only --full-inputs
python Codecs/Speex/AVR/tools/build_wb.py --avr-gcc avr-gcc --backend asm --packet-bytes 25 --out Codecs/Speex/AVR/build/wb-speed-final-98
node Codecs/Speex/AVR/tests/verify_wb.mjs --firmware Codecs/Speex/AVR/build/wb-speed-final-98 --streams INPUT_WB98/streams --oracle INPUT_WB98/oracle --profile
python Codecs/Speex/AVR/tools/build_wb_stream_test.py --avr-gcc avr-gcc --packet-bytes 25 --frame-load-cycles 25600 --out Codecs/Speex/AVR/build/wb-speed-final-stream-98
node Codecs/Speex/AVR/tests/verify_wb_stream.mjs --firmware Codecs/Speex/AVR/build/wb-speed-final-stream-98 --streams INPUT_WB98/streams --oracle INPUT_WB98/oracle
```

Repeat the last four commands with width 32, suffix `128`, and the WB12.8
corpus/oracle. Baseline is revision
`22e50e01c9595b62e78fc2b6c0e454c51bbe7dfc`, using the same current verifiers
on the baseline-built images. The fixed profiler attributes actual instruction
cycles in command intervals across all streams; startup/reset/IRQ are excluded.

The unit driver compares against independent mathematical equations, including
full-scale input, negative odd halves, Q6 rounding, saturation to +/-32767,
history, alias, guards and ABI. Existing full-decoder compact-profile PCM
oracles retain untouched Xiph decoding before the final QMF. Exact PCM means
zero quality change from the preceding compact profile, not full-Xiph quality.

See the [reusable technique](../../../docs/avr-asm-cookbook/speex-qmf-input.md)
and [work plan](WB_IMPROVEMENT_PLAN.md).
