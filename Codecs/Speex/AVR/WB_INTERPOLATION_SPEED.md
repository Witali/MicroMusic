# Exact HB1 interpolation speed stage

Baseline `7ca56cf1`: ATmega328P / AVR5, 16 MHz, 2 KB SRAM, AVR GCC 7.3.0,
existing mixed Os/O2/O3 attributes, LTO, mcall-prologues and mrelax. The
production controller is portable C; arithmetic backend selection is unchanged.

Move quarter selection outside the eight-word loop, express interpolation
through a signed16 endpoint difference, and exchange pointers to share the
first/third-quarter loop. Explicitly retain the ten necessary sequential margin
repairs. The first clamp and two interior checks are unreachable in the
complete pinned HB1 codebook domain. No quantization, filter, persistent state,
packet handling or public interface changes.

The [finite-domain proof](reports/wb-interpolation-domain.json) covers all
67108864 endpoint-pair/quarter vectors. The [seven isolated AVR recipes](reports/wb-interpolation-unit.json)
retain independent separately rounded Xiph models, guards and ABI checks.
The [cookbook](../../../docs/avr-asm-cookbook/speex-hb-interpolation.md) explains
the domains and rejected alternatives.

## Complete-image screen

The [source-bound screen](reports/wb-interpolation-screen.json) compares 3769
frames before/after across all five rates, including resets. All signed16
outputs are exact. Frames bypassing interpolation retain their original cost;
other measured frames improve, with no frame regression.

| Mode | Before cycles/frame | After | Frames |
| --- | ---: | ---: | ---: |
| WB3.95 | 220026.909 | 219053.043 | 1152 |
| WB5.75 | 227210.108 | 226236.242 | 1152 |
| WB7.75 | 238755.618 | 237781.753 | 1152 |
| WB9.8 | 229080.181 | 228488.169 | 249 |
| WB12.8 | 234877.891 | 233945.125 | 64 |

All full linked ASM images grow by 192 B (25920 -> 26112), with unchanged static
SRAM and peak stack. The smaller shared-loop/ordinary-margin variant costs
only 12 B but saves less time: WB3.95 mean 219421.196 and WB9.8 mean 228712.040.
The selected finite-margin recipe follows the speed-first objective.

Another 3769 frames pass production timer/PWM IRQs at the existing per-mode
8%/3% additional work gates, exact signed16/PWM, zero underruns and 990..1010-cycle
sample intervals. This is a screen, not a refreshed complete-history admission.
Longer validation of the final optimized source is a separate stage.
Input/oracle availability and differing workloads remain those documented in
[the preceding divider stage](WB_RATIO_SPEED.md). Ready RAM does not measure
transport latency or physical hardware.

Both full AVR C controls compile/link only: 31374 -> 31566 B. The generic C11
export with 21 sources compiles/links without handwritten assembly. No complete
C decoder executes or is timed. Linux and Windows AVR toolchains reproduce
the pinned baseline firmware identically; host export checks use GCC 13.3.

The shared stage runner now accepts `--out <fresh-stage-root>` and
`--baseline-revision`, preserving its original defaults. To reproduce, prepare
`build/hb-speed` with the same retained data, build both epochs from the pinned
baseline/current codec roots, run compile-only controls, and run raw/IRQ screens:

```sh
python Codecs/Speex/AVR/tests/run_wb_ratio_stage.py --phase raw --screen --out Codecs/Speex/AVR/build/hb-speed --node node
python Codecs/Speex/AVR/tests/run_wb_ratio_stage.py --phase irq --screen --out Codecs/Speex/AVR/build/hb-speed --node node
python Codecs/Speex/AVR/tests/audit_wb_ratio_stage.py --stage interpolation --screen
```

Before artifacts are reused after source/hash verification from the admitted
post-divider stage; a fresh baseline rebuild confirms firmware identity.
Generated firmware/audio/logs remain ignored; no gallery publication is involved.
